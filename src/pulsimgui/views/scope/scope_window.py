"""Floating windows that host per-component scope viewers."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.theme_service import Theme, ThemeService
from pulsimgui.views.waveform import WaveformViewer
from pulsimgui.views.waveform.waveform_viewer import (
    MeasurementsPanel,
    SignalListPanel,
    TRACE_COLORS,
)

from .bindings import ScopeChannelBinding, ScopeSignal


class ScopeWindow(QWidget):
    """Standalone scope window wrapping a :class:`WaveformViewer`."""

    closed = Signal(str, tuple)
    DEFAULT_TRACE_WIDTH = 2.0
    STACKED_MAX_DISPLAY_POINTS = 10000
    STACKED_TOTAL_POINT_BUDGET = 24000
    STACKED_MIN_POINTS_PER_SIGNAL = 1200

    def __init__(
        self,
        component_id: str,
        component_name: str,
        scope_type: ComponentType,
        theme_service: ThemeService | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent, Qt.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumSize(900, 620)

        self._component_id = component_id
        self._component_name = component_name
        self._scope_type = scope_type
        self._theme_service = theme_service
        self._theme: Theme | None = None
        self._bindings: list[ScopeChannelBinding] = []
        self._current_result: SimulationResult | None = None
        self._plot_widgets: list[pg.PlotWidget] = []
        self._default_mode_set = False
        self._stacked_time: np.ndarray = np.array([], dtype=float)
        self._stacked_signals: dict[str, np.ndarray] = {}
        self._stacked_signal_stats: dict[str, dict[str, float]] = {}
        self._stacked_active_signal: str | None = None
        self._stacked_cursors_enabled = False
        self._stacked_grid_enabled = True
        self._stacked_cursor_lines: list[tuple[pg.InfiniteLine, pg.InfiniteLine]] = []
        self._syncing_stacked_cursor_controls = False
        self._stacked_cursor_initialized = False
        self._trace_styles: dict[str, dict[str, object]] = {}
        self._default_trace_width = self.DEFAULT_TRACE_WIDTH
        self._syncing_trace_style_controls = False

        self._viewer = WaveformViewer(theme_service=self._theme_service)
        self._viewer.setMinimumSize(760, 460)
        self._viewer.set_manual_signal_add_enabled(False)
        self._viewer.set_auto_show_all_signals(True)
        self._viewer.set_default_trace_width(self._default_trace_width)
        self._viewer.set_trace_styles(self._trace_styles)

        self._mode_combo = QComboBox()
        self._mode_combo.addItems(["Overlay", "Stacked"])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._trace_signal_combo = QComboBox()
        self._trace_signal_combo.setMinimumWidth(220)
        self._trace_signal_combo.currentTextChanged.connect(self._on_trace_style_signal_changed)
        self._trace_width_spin = QDoubleSpinBox()
        self._trace_width_spin.setRange(0.5, 8.0)
        self._trace_width_spin.setSingleStep(0.2)
        self._trace_width_spin.setDecimals(1)
        self._trace_width_spin.setMaximumWidth(76)
        self._trace_width_spin.setValue(self._default_trace_width)
        self._trace_width_spin.valueChanged.connect(self._on_trace_width_changed)
        self._trace_color_btn = QPushButton("Color")
        self._trace_color_btn.clicked.connect(self._on_trace_color_clicked)
        self._trace_reset_btn = QPushButton("Reset")
        self._trace_reset_btn.clicked.connect(self._on_trace_style_reset)

        self._view_stack = QStackedWidget()
        self._view_stack.addWidget(self._viewer)

        self._stacked_page = QWidget()
        stacked_page_layout = QVBoxLayout(self._stacked_page)
        stacked_page_layout.setContentsMargins(0, 0, 0, 0)
        stacked_page_layout.setSpacing(0)
        self._stacked_splitter = QSplitter(Qt.Orientation.Horizontal)
        stacked_page_layout.addWidget(self._stacked_splitter)

        self._stacked_scroll = QScrollArea()
        self._stacked_scroll.setWidgetResizable(True)
        self._stacked_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._stacked_content = QWidget()
        self._stacked_layout = QVBoxLayout(self._stacked_content)
        self._stacked_layout.setContentsMargins(8, 8, 8, 8)
        self._stacked_layout.setSpacing(8)
        self._stacked_layout.addStretch()
        self._stacked_scroll.setWidget(self._stacked_content)
        self._stacked_splitter.addWidget(self._stacked_scroll)

        self._stacked_sidebar = QWidget()
        stacked_sidebar_layout = QVBoxLayout(self._stacked_sidebar)
        stacked_sidebar_layout.setContentsMargins(8, 8, 8, 8)
        stacked_sidebar_layout.setSpacing(6)

        stacked_controls = QWidget()
        stacked_controls.setObjectName("scopeStackedControlBar")
        stacked_controls_layout = QHBoxLayout(stacked_controls)
        stacked_controls_layout.setContentsMargins(0, 0, 0, 0)
        stacked_controls_layout.setSpacing(4)

        self._stacked_cursor_toggle = QCheckBox("Cursors")
        self._stacked_cursor_toggle.setChecked(self._stacked_cursors_enabled)
        self._stacked_cursor_toggle.toggled.connect(self._on_stacked_cursor_toggled)
        stacked_controls_layout.addWidget(self._stacked_cursor_toggle)

        self._stacked_grid_toggle = QCheckBox("Grid")
        self._stacked_grid_toggle.setChecked(self._stacked_grid_enabled)
        self._stacked_grid_toggle.toggled.connect(self._on_stacked_grid_toggled)
        stacked_controls_layout.addWidget(self._stacked_grid_toggle)

        self._c1_label = QLabel("C1")
        stacked_controls_layout.addWidget(self._c1_label)
        self._c1_spin = QDoubleSpinBox()
        self._c1_spin.setKeyboardTracking(False)
        self._c1_spin.setDecimals(8)
        self._c1_spin.setSingleStep(1e-6)
        self._c1_spin.setMaximumWidth(92)
        self._c1_spin.valueChanged.connect(self._on_stacked_cursor_changed)
        stacked_controls_layout.addWidget(self._c1_spin)

        self._c2_label = QLabel("C2")
        stacked_controls_layout.addWidget(self._c2_label)
        self._c2_spin = QDoubleSpinBox()
        self._c2_spin.setKeyboardTracking(False)
        self._c2_spin.setDecimals(8)
        self._c2_spin.setSingleStep(1e-6)
        self._c2_spin.setMaximumWidth(92)
        self._c2_spin.valueChanged.connect(self._on_stacked_cursor_changed)
        stacked_controls_layout.addWidget(self._c2_spin)

        stacked_controls_layout.addStretch()

        self._stacked_fit_btn = QPushButton("Fit")
        self._stacked_fit_btn.clicked.connect(self._auto_range_stacked)
        stacked_controls_layout.addWidget(self._stacked_fit_btn)

        stacked_sidebar_layout.addWidget(stacked_controls, stretch=0)

        self._stacked_signal_list = SignalListPanel()
        self._stacked_signal_list.setMinimumWidth(200)
        self._stacked_signal_list.setMaximumWidth(320)
        self._stacked_signal_list.signal_visibility_changed.connect(
            self._on_stacked_signal_visibility_changed
        )
        self._stacked_signal_list.signal_selected.connect(self._on_stacked_signal_selected)
        self._stacked_signal_list.signal_double_clicked.connect(self._on_stacked_signal_selected)
        stacked_sidebar_layout.addWidget(self._stacked_signal_list, stretch=1)

        self._stacked_measurements = MeasurementsPanel()
        self._stacked_measurements.setMinimumWidth(260)
        self._stacked_measurements.setMaximumWidth(460)
        stacked_sidebar_layout.addWidget(self._stacked_measurements, stretch=2)

        self._stacked_splitter.addWidget(self._stacked_sidebar)
        self._stacked_splitter.setCollapsible(0, False)
        self._stacked_splitter.setCollapsible(1, False)
        self._stacked_splitter.setStretchFactor(0, 4)
        self._stacked_splitter.setStretchFactor(1, 2)
        self._stacked_splitter.setSizes([840, 360])

        self._view_stack.addWidget(self._stacked_page)

        self._mapping_label = QLabel()
        self._mapping_label.setWordWrap(False)
        self._mapping_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._mapping_label.setObjectName("scopeMappingLabel")

        self._message_label = QLabel("Waiting for simulation results...")
        self._message_label.setWordWrap(False)
        self._message_label.setObjectName("scopeMessageLabel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._view_stack, stretch=1)

        info_container = QWidget()
        info_layout = QVBoxLayout(info_container)
        info_layout.setContentsMargins(8, 4, 8, 6)
        info_layout.setSpacing(2)
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.setSpacing(6)
        mode_layout.addWidget(QLabel("Display:"))
        mode_layout.addWidget(self._mode_combo, stretch=0)
        mode_layout.addSpacing(12)
        mode_layout.addWidget(QLabel("Trace:"))
        mode_layout.addWidget(self._trace_signal_combo, stretch=0)
        mode_layout.addWidget(QLabel("Width:"))
        mode_layout.addWidget(self._trace_width_spin, stretch=0)
        mode_layout.addWidget(self._trace_color_btn, stretch=0)
        mode_layout.addWidget(self._trace_reset_btn, stretch=0)
        mode_layout.addStretch(1)
        info_layout.addWidget(mode_row)
        info_layout.addWidget(self._mapping_label)
        info_layout.addWidget(self._message_label)
        layout.addWidget(info_container, stretch=0)

        self._set_stacked_cursor_enabled(False)
        self._apply_stacked_trace_colors()
        self._sync_trace_style_controls()

        self._refresh_title()
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def component_id(self) -> str:
        return self._component_id

    def set_component_name(self, name: str) -> None:
        self._component_name = name
        self._refresh_title()

    def set_bindings(self, bindings: list[ScopeChannelBinding]) -> None:
        self._bindings = bindings
        if not bindings:
            self._mapping_label.setText("Channels: none")
            return

        if not self._default_mode_set:
            overlay_default = all(binding.overlay for binding in bindings)
            mode_index = 0 if overlay_default else 1
            self._mode_combo.blockSignals(True)
            self._mode_combo.setCurrentIndex(mode_index)
            self._mode_combo.blockSignals(False)
            self._view_stack.setCurrentIndex(mode_index)
            self._default_mode_set = True

        entries = []
        for binding in bindings:
            if binding.signals:
                targets = ", ".join(signal.label or signal.signal_key or "(unlabeled)" for signal in binding.signals)
            else:
                targets = "(unconnected)"
            entries.append(f"{binding.channel_label}={targets}")
        self._mapping_label.setText(f"Channels: {' | '.join(entries)}")

    def apply_simulation_result(self, result: SimulationResult | None) -> None:
        """Filter the supplied result down to the window's bindings."""

        if not result or not result.time:
            self._current_result = SimulationResult()
            self._viewer.set_result(self._current_result)
            if self._mode_combo.currentIndex() == 1:
                self._refresh_stacked_sidebar(self._current_result)
                self._rebuild_stacked_plots(self._current_result)
            else:
                self._sync_trace_style_controls()
            self._message_label.setText("No simulation data available yet.")
            return

        subset = SimulationResult()
        subset.time = list(result.time)
        subset.signals = {}
        subset.statistics = dict(result.statistics)

        found_channels: list[str] = []
        missing_channels: list[str] = []

        for binding in self._bindings:
            if not binding.signals:
                missing_channels.append(binding.display_name)
                continue

            for idx, signal in enumerate(binding.signals):
                base_label = self._format_signal_label(binding, signal, idx)
                label = self._ensure_unique_label(base_label, subset.signals)
                if not signal.signal_key:
                    missing_channels.append(label)
                    continue
                series = result.signals.get(signal.signal_key)
                if series:
                    subset.signals[label] = list(series)
                    found_channels.append(label)
                else:
                    missing_channels.append(label)

        self._current_result = subset if subset.signals else SimulationResult(time=subset.time, signals={})
        self._viewer.set_result(self._current_result)
        if self._mode_combo.currentIndex() == 1:
            self._refresh_stacked_sidebar(self._current_result)
            self._rebuild_stacked_plots(self._current_result)
        else:
            self._sync_trace_style_controls()

        self._message_label.setText(self._format_status(found_channels, missing_channels))

    def apply_geometry_state(self, geometry: list[int] | None) -> None:
        if geometry and len(geometry) == 4:
            x, y, w, h = geometry
            self.setGeometry(
                x,
                y,
                max(w, self.minimumWidth()),
                max(h, self.minimumHeight()),
            )
        else:
            self.resize(max(1040, self.minimumWidth()), max(700, self.minimumHeight()))

    def capture_geometry_state(self) -> tuple[int, int, int, int]:
        rect = self.geometry()
        return rect.x(), rect.y(), rect.width(), rect.height()

    # ------------------------------------------------------------------
    # QWidget overrides
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: D401 - Qt override
        self.closed.emit(self._component_id, self.capture_geometry_state())
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _refresh_title(self) -> None:
        label = "Scope" if self._scope_type == ComponentType.ELECTRICAL_SCOPE else "Thermal Scope"
        self.setWindowTitle(f"{self._component_name or 'Unnamed'} - {label}")

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to scope chrome and both display modes."""
        self._theme = theme
        c = theme.colors
        self._viewer.apply_theme(theme)
        self._apply_stacked_trace_colors()
        self._stacked_signal_list.apply_theme(theme)
        self._stacked_measurements.apply_theme(theme, cursor_palette=self._cursor_palette())
        self.setStyleSheet(f"""
            QLabel#scopeMappingLabel {{
                color: {c.foreground_muted};
                font-size: 11px;
            }}
            QLabel#scopeMessageLabel {{
                color: {c.foreground};
                font-weight: 500;
                font-size: 11px;
            }}
            QComboBox, QDoubleSpinBox {{
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 4px;
                padding: 2px 5px;
                min-height: 20px;
            }}
            QPushButton {{
                background-color: {c.panel_background};
                color: {c.foreground};
                border: 1px solid {c.panel_border};
                border-radius: 4px;
                padding: 2px 8px;
                min-height: 20px;
            }}
            QWidget#scopeStackedControlBar QCheckBox {{
                spacing: 4px;
                padding: 0;
            }}
        """)
        self._sync_trace_style_controls()
        if self._mode_combo.currentIndex() == 1:
            self._rebuild_stacked_plots(self._current_result)

    def _on_mode_changed(self, index: int) -> None:
        if index == 1:
            self._refresh_stacked_sidebar(self._current_result)
            self._sync_stacked_cursors_from_overlay()
            self._rebuild_stacked_plots(self._current_result)
            self._sync_stacked_cursor_lines()
            self._update_stacked_measurements()
            self._view_stack.setCurrentIndex(index)
            return

        self._sync_overlay_cursors_from_stacked()
        self._view_stack.setCurrentIndex(index)

    def _sync_stacked_cursors_from_overlay(self) -> None:
        enabled, c1, c2 = self._viewer.cursor_state()
        self._stacked_cursors_enabled = enabled

        self._stacked_cursor_toggle.blockSignals(True)
        self._stacked_cursor_toggle.setChecked(enabled)
        self._stacked_cursor_toggle.blockSignals(False)
        self._set_stacked_cursor_enabled(len(self._stacked_time) > 0)

        if c1 is None or c2 is None or len(self._stacked_time) == 0:
            return

        self._apply_stacked_cursor_positions(c1, c2)

    def _sync_overlay_cursors_from_stacked(self) -> None:
        c1 = self._c1_spin.value() if self._stacked_cursor_initialized else None
        c2 = self._c2_spin.value() if self._stacked_cursor_initialized else None
        self._viewer.set_cursor_state(self._stacked_cursors_enabled, c1=c1, c2=c2)

    def _apply_stacked_cursor_positions(self, c1: float, c2: float) -> None:
        if len(self._stacked_time) == 0:
            return

        c1_clamped = self._clamp_stacked_cursor_time(c1)
        c2_clamped = self._clamp_stacked_cursor_time(c2)

        self._syncing_stacked_cursor_controls = True
        self._c1_spin.blockSignals(True)
        self._c2_spin.blockSignals(True)
        try:
            self._c1_spin.setValue(c1_clamped)
            self._c2_spin.setValue(c2_clamped)
        finally:
            self._c1_spin.blockSignals(False)
            self._c2_spin.blockSignals(False)
            self._syncing_stacked_cursor_controls = False

        self._stacked_cursor_initialized = True

    def _clamp_stacked_cursor_time(self, value: float) -> float:
        if len(self._stacked_time) == 0:
            return float(value)
        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        if t_max < t_min:
            t_min, t_max = t_max, t_min
        return float(min(max(value, t_min), t_max))

    def _clear_stacked_plots(self) -> None:
        while self._stacked_layout.count():
            item = self._stacked_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._plot_widgets.clear()
        self._stacked_cursor_lines.clear()

    def _trace_palette(self) -> list[tuple[int, int, int]]:
        if (
            self._theme_service is not None
            and self._theme is not None
            and hasattr(self._theme_service, "get_trace_palette")
        ):
            return self._theme_service.get_trace_palette(self._theme)
        return TRACE_COLORS

    def _cursor_palette(self) -> list[tuple[int, int, int]] | None:
        if (
            self._theme_service is not None
            and self._theme is not None
            and hasattr(self._theme_service, "get_cursor_palette")
        ):
            return self._theme_service.get_cursor_palette(self._theme)
        return None

    def _trace_style_color(self, signal_name: str) -> tuple[int, int, int] | None:
        style = self._trace_styles.get(signal_name, {})
        color = style.get("color")
        if isinstance(color, tuple) and len(color) == 3:
            return color
        return None

    def _trace_signal_names(self) -> list[str]:
        if self._current_result and self._current_result.signals:
            return list(self._current_result.signals.keys())
        return list(self._stacked_signals.keys())

    def _default_trace_color(self, signal_name: str) -> tuple[int, int, int]:
        palette = self._trace_palette()
        signal_names = self._trace_signal_names()
        if signal_name in signal_names:
            index = signal_names.index(signal_name)
            return palette[index % len(palette)]
        return palette[0]

    def _trace_style_width(self, signal_name: str) -> float:
        style = self._trace_styles.get(signal_name, {})
        width = style.get("width")
        if isinstance(width, (int, float)):
            return max(0.5, float(width))
        return self._default_trace_width

    @staticmethod
    def _rgb_to_hex(color: tuple[int, int, int]) -> str:
        return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"

    def _apply_trace_styles_to_viewer(self) -> None:
        self._viewer.set_trace_styles(self._trace_styles)

    def _apply_stacked_trace_colors(self) -> None:
        self._stacked_signal_list.set_trace_palette(self._trace_palette())
        for signal_name in self._stacked_signals:
            override = self._trace_style_color(signal_name)
            if override is not None:
                self._stacked_signal_list.set_signal_color(signal_name, override)

    def _selected_trace_signal(self) -> str | None:
        signal_name = self._trace_signal_combo.currentText().strip()
        if signal_name and signal_name in self._trace_signal_names():
            return signal_name
        return None

    def _update_trace_color_button(self, signal_name: str | None) -> None:
        if signal_name is None:
            self._trace_color_btn.setText("Color")
            return
        color = self._trace_style_color(signal_name)
        if color is None:
            color = self._stacked_signal_list.get_signal_color(signal_name)
        if color is None:
            color = self._default_trace_color(signal_name)
        self._trace_color_btn.setText(self._rgb_to_hex(color).upper())

    def _set_trace_controls_for_signal(self, signal_name: str | None) -> None:
        width = self._default_trace_width
        if signal_name is not None:
            width = self._trace_style_width(signal_name)

        self._syncing_trace_style_controls = True
        self._trace_width_spin.blockSignals(True)
        try:
            self._trace_width_spin.setValue(width)
        finally:
            self._trace_width_spin.blockSignals(False)
            self._syncing_trace_style_controls = False

        self._update_trace_color_button(signal_name)

    def _sync_trace_style_controls(self) -> None:
        signal_names = self._trace_signal_names()
        current = self._trace_signal_combo.currentText()
        if current in signal_names:
            selected = current
        elif self._stacked_active_signal in signal_names:
            selected = self._stacked_active_signal
        elif signal_names:
            selected = signal_names[0]
        else:
            selected = ""

        self._syncing_trace_style_controls = True
        self._trace_signal_combo.blockSignals(True)
        try:
            self._trace_signal_combo.clear()
            self._trace_signal_combo.addItems(signal_names)
            if selected:
                index = self._trace_signal_combo.findText(selected)
                if index >= 0:
                    self._trace_signal_combo.setCurrentIndex(index)
        finally:
            self._trace_signal_combo.blockSignals(False)
            self._syncing_trace_style_controls = False

        controls_enabled = bool(signal_names)
        self._trace_signal_combo.setEnabled(controls_enabled)
        self._trace_width_spin.setEnabled(controls_enabled)
        self._trace_color_btn.setEnabled(controls_enabled)
        self._trace_reset_btn.setEnabled(controls_enabled)
        self._set_trace_controls_for_signal(selected or None)

    def _prune_trace_style(self, signal_name: str) -> None:
        style = self._trace_styles.get(signal_name)
        if not style:
            return

        width = style.get("width")
        if isinstance(width, (int, float)) and abs(float(width) - self._default_trace_width) < 1e-9:
            style.pop("width", None)

        color = style.get("color")
        if not (isinstance(color, tuple) and len(color) == 3):
            style.pop("color", None)

        if not style:
            self._trace_styles.pop(signal_name, None)

    def _on_trace_style_signal_changed(self, signal_name: str) -> None:
        if self._syncing_trace_style_controls:
            return
        self._set_trace_controls_for_signal(signal_name or None)

    def _on_trace_width_changed(self, value: float) -> None:
        if self._syncing_trace_style_controls:
            return
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return

        style = self._trace_styles.setdefault(signal_name, {})
        style["width"] = max(0.5, float(value))
        self._prune_trace_style(signal_name)
        self._apply_trace_styles_to_viewer()
        if self._mode_combo.currentIndex() == 1:
            self._rebuild_stacked_plots(self._current_result)

    def _on_trace_color_clicked(self) -> None:
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return

        base_color = self._trace_style_color(signal_name)
        if base_color is None:
            base_color = self._stacked_signal_list.get_signal_color(signal_name)
        if base_color is None:
            base_color = self._default_trace_color(signal_name)

        picked = QColorDialog.getColor(
            QColor(*base_color),
            self,
            f"Trace color - {signal_name}",
        )
        if not picked.isValid():
            return

        style = self._trace_styles.setdefault(signal_name, {})
        style["color"] = (picked.red(), picked.green(), picked.blue())
        self._prune_trace_style(signal_name)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        if self._mode_combo.currentIndex() == 1:
            self._rebuild_stacked_plots(self._current_result)

    def _on_trace_style_reset(self) -> None:
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return

        self._trace_styles.pop(signal_name, None)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        if self._mode_combo.currentIndex() == 1:
            self._rebuild_stacked_plots(self._current_result)

    @staticmethod
    def _decimate_stacked_for_display(
        time: np.ndarray,
        values: np.ndarray,
        max_points: int,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Downsample preserving waveform shape by min/max bucketing."""
        n_points = len(time)
        if n_points <= max_points or max_points < 4:
            return time, values

        n_buckets = max(1, max_points // 2)
        bucket_size = max(1, n_points // n_buckets)

        max_output_size = (n_buckets * 2) + 2
        decimated_time = np.empty(max_output_size, dtype=time.dtype)
        decimated_values = np.empty(max_output_size, dtype=values.dtype)

        out_idx = 0
        last_global_idx = -1

        # Keep signal boundaries for stable cursor/readout behavior.
        decimated_time[out_idx] = time[0]
        decimated_values[out_idx] = values[0]
        out_idx += 1
        last_global_idx = 0

        for bucket in range(n_buckets):
            start = bucket * bucket_size
            if start >= n_points:
                break
            end = n_points if bucket == n_buckets - 1 else min(start + bucket_size, n_points)
            if end <= start:
                continue

            bucket_values = values[start:end]
            if len(bucket_values) == 0:
                continue

            min_local = int(np.argmin(bucket_values))
            max_local = int(np.argmax(bucket_values))
            first_local, second_local = (
                (min_local, max_local)
                if min_local <= max_local
                else (max_local, min_local)
            )

            for local_idx in (first_local, second_local):
                global_idx = start + local_idx
                if global_idx == last_global_idx:
                    continue
                decimated_time[out_idx] = time[global_idx]
                decimated_values[out_idx] = values[global_idx]
                out_idx += 1
                last_global_idx = global_idx
                if out_idx >= max_output_size:
                    break

            if out_idx >= max_output_size:
                break

        if last_global_idx != n_points - 1 and out_idx < max_output_size:
            decimated_time[out_idx] = time[-1]
            decimated_values[out_idx] = values[-1]
            out_idx += 1

        return decimated_time[:out_idx], decimated_values[:out_idx]

    @staticmethod
    def _configure_stacked_trace_performance(trace: pg.PlotDataItem, point_count: int) -> None:
        if point_count < 5000:
            return
        trace.setClipToView(True)
        trace.setDownsampling(auto=True, method="peak")

    def _stacked_target_points_per_signal(self, visible_count: int) -> int:
        if visible_count <= 0:
            return self.STACKED_MAX_DISPLAY_POINTS
        budget = self.STACKED_TOTAL_POINT_BUDGET // visible_count
        bounded = min(self.STACKED_MAX_DISPLAY_POINTS, budget)
        return max(self.STACKED_MIN_POINTS_PER_SIGNAL, bounded)

    def _rebuild_stacked_statistics_cache(self) -> None:
        self._stacked_signal_stats = {}
        for signal_name, values in self._stacked_signals.items():
            if len(values) == 0:
                continue
            min_val = float(np.min(values))
            max_val = float(np.max(values))
            mean_val = float(np.mean(values))
            rms_val = float(np.sqrt(np.mean(values ** 2)))
            self._stacked_signal_stats[signal_name] = {
                "min": min_val,
                "max": max_val,
                "mean": mean_val,
                "rms": rms_val,
                "pkpk": max_val - min_val,
            }

    def _set_stacked_cursor_enabled(self, enabled: bool) -> None:
        final_enabled = bool(enabled) and self._stacked_cursors_enabled
        self._c1_label.setEnabled(final_enabled)
        self._c2_label.setEnabled(final_enabled)
        self._c1_spin.setEnabled(final_enabled)
        self._c2_spin.setEnabled(final_enabled)

    def _on_stacked_cursor_toggled(self, checked: bool) -> None:
        self._stacked_cursors_enabled = checked
        self._set_stacked_cursor_enabled(len(self._stacked_time) > 0)
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_stacked_grid_toggled(self, checked: bool) -> None:
        self._stacked_grid_enabled = checked
        self._rebuild_stacked_plots(self._current_result)

    def _auto_range_stacked(self) -> None:
        for plot in self._plot_widgets:
            plot.autoRange()

    def _sync_stacked_cursor_lines(self) -> None:
        if not self._stacked_cursors_enabled or self._syncing_stacked_cursor_controls:
            return
        if not self._stacked_cursor_lines:
            return
        c1_val = self._c1_spin.value()
        c2_val = self._c2_spin.value()
        self._syncing_stacked_cursor_controls = True
        try:
            for c1_line, c2_line in self._stacked_cursor_lines:
                c1_line.setValue(c1_val)
                c2_line.setValue(c2_val)
        finally:
            self._syncing_stacked_cursor_controls = False

    def _on_stacked_plot_cursor_moved(self, which: int, value: float) -> None:
        if self._syncing_stacked_cursor_controls:
            return
        if len(self._stacked_time) == 0:
            return
        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        clamped = min(max(value, t_min), t_max)
        self._syncing_stacked_cursor_controls = True
        try:
            if which == 1:
                self._c1_spin.setValue(clamped)
            else:
                self._c2_spin.setValue(clamped)
        finally:
            self._syncing_stacked_cursor_controls = False
        self._stacked_cursor_initialized = True
        self._sync_stacked_cursor_lines()
        self._update_stacked_measurements()

    def _refresh_stacked_sidebar(self, result: SimulationResult | None) -> None:
        if not result or not result.time or not result.signals:
            self._stacked_time = np.array([], dtype=float)
            self._stacked_signals = {}
            self._stacked_signal_stats = {}
            self._stacked_active_signal = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._sync_trace_style_controls()
            return

        time = np.asarray(result.time, dtype=float)
        valid_signals: dict[str, np.ndarray] = {}
        for name, values_raw in result.signals.items():
            values = np.asarray(values_raw, dtype=float)
            if len(values) == len(time) and len(values) > 0:
                valid_signals[name] = values

        if not valid_signals:
            self._stacked_time = np.array([], dtype=float)
            self._stacked_signals = {}
            self._stacked_signal_stats = {}
            self._stacked_active_signal = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._sync_trace_style_controls()
            return

        self._stacked_time = time
        self._stacked_signals = valid_signals
        self._rebuild_stacked_statistics_cache()

        previous_visible = set(self._stacked_signal_list.get_visible_signals())
        previous_active = self._stacked_active_signal

        self._stacked_signal_list.set_signals(list(valid_signals.keys()))
        self._apply_stacked_trace_colors()

        default_show_all = not previous_visible
        for name in valid_signals:
            self._stacked_signal_list.set_signal_visible(
                name,
                default_show_all or name in previous_visible,
            )

        visible = self._stacked_signal_list.get_visible_signals()
        if not visible:
            first = next(iter(valid_signals))
            self._stacked_signal_list.set_signal_visible(first, True)
            visible = [first]

        if previous_active in valid_signals:
            self._stacked_active_signal = previous_active
        else:
            self._stacked_active_signal = visible[0]

        self._configure_stacked_cursor_spins()
        self._update_stacked_measurements()
        self._sync_trace_style_controls()

    def _configure_stacked_cursor_spins(self) -> None:
        if len(self._stacked_time) == 0:
            self._stacked_cursor_initialized = False
            self._set_stacked_cursor_enabled(False)
            return

        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        if t_max < t_min:
            t_min, t_max = t_max, t_min

        t_span = max(t_max - t_min, 1e-12)
        step = t_span / 1000.0

        if self._stacked_cursor_initialized:
            current_c1 = self._c1_spin.value()
            current_c2 = self._c2_spin.value()
            keep_c1 = t_min <= current_c1 <= t_max
            keep_c2 = t_min <= current_c2 <= t_max
            c1 = current_c1 if keep_c1 else (t_min + t_span * 0.33)
            c2 = current_c2 if keep_c2 else (t_min + t_span * 0.67)
        else:
            c1 = t_min + t_span * 0.33
            c2 = t_min + t_span * 0.67

        self._c1_spin.blockSignals(True)
        self._c2_spin.blockSignals(True)
        self._c1_spin.setRange(t_min, t_max)
        self._c2_spin.setRange(t_min, t_max)
        self._c1_spin.setSingleStep(step)
        self._c2_spin.setSingleStep(step)
        self._c1_spin.setValue(c1)
        self._c2_spin.setValue(c2)
        self._c1_spin.blockSignals(False)
        self._c2_spin.blockSignals(False)
        self._stacked_cursor_initialized = True
        self._set_stacked_cursor_enabled(True)

    def _on_stacked_signal_visibility_changed(self, _signal_name: str, _visible: bool) -> None:
        visible = self._stacked_signal_list.get_visible_signals()
        if self._stacked_active_signal not in self._stacked_signals and self._stacked_signals:
            self._stacked_active_signal = next(iter(self._stacked_signals))
        if self._stacked_active_signal not in visible and visible:
            self._stacked_active_signal = visible[0]
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_stacked_signal_selected(self, signal_name: str) -> None:
        if signal_name in self._stacked_signals:
            self._stacked_active_signal = signal_name
            combo_index = self._trace_signal_combo.findText(signal_name)
            if combo_index >= 0:
                self._trace_signal_combo.blockSignals(True)
                self._trace_signal_combo.setCurrentIndex(combo_index)
                self._trace_signal_combo.blockSignals(False)
            self._set_trace_controls_for_signal(signal_name)
            self._update_stacked_measurements()

    def _on_stacked_cursor_changed(self, _value: float) -> None:
        self._stacked_cursor_initialized = True
        if not self._syncing_stacked_cursor_controls:
            self._sync_stacked_cursor_lines()
        self._update_stacked_measurements()

    def _update_stacked_measurements(self) -> None:
        if len(self._stacked_time) == 0 or not self._stacked_signals:
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            return

        signal_name = self._stacked_active_signal
        if signal_name not in self._stacked_signals:
            signal_name = next(iter(self._stacked_signals))
            self._stacked_active_signal = signal_name

        values = self._stacked_signals[signal_name]
        stats = self._stacked_signal_stats.get(signal_name)
        if stats is None:
            self._stacked_measurements.clear_statistics()
        else:
            self._stacked_measurements.update_statistics(
                stats["min"],
                stats["max"],
                stats["mean"],
                stats["rms"],
            )

        if self._stacked_cursors_enabled:
            t1 = self._c1_spin.value()
            t2 = self._c2_spin.value()
            v1 = self._interpolate_stacked_value(t1, values)
            v2 = self._interpolate_stacked_value(t2, values)
            self._stacked_measurements.update_cursor1(t1, v1)
            self._stacked_measurements.update_cursor2(t2, v2)
            dt = t2 - t1
            dv = v2 - v1 if v1 is not None and v2 is not None else None
            self._stacked_measurements.update_delta(dt, dv, v1, v2)
            self._stacked_measurements.set_multi_signal_measurements(
                self._build_stacked_measurements_table(t1, t2)
            )
        else:
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements(
                self._build_stacked_measurements_table(None, None)
            )

    def _build_stacked_measurements_table(
        self,
        t1: float | None,
        t2: float | None,
    ) -> dict[str, dict[str, float | None]]:
        table: dict[str, dict[str, float | None]] = {}
        for name, values in self._stacked_signals.items():
            stats = self._stacked_signal_stats.get(name)
            if stats is None:
                continue
            c1 = self._interpolate_stacked_value(t1, values) if t1 is not None else None
            c2 = self._interpolate_stacked_value(t2, values) if t2 is not None else None
            dv = c2 - c1 if c1 is not None and c2 is not None else None
            table[name] = {
                "c1": c1,
                "c2": c2,
                "dv": dv,
                "min": stats["min"],
                "max": stats["max"],
                "mean": stats["mean"],
                "rms": stats["rms"],
                "pkpk": stats["pkpk"],
            }
        return table

    def _interpolate_stacked_value(self, t: float, values: np.ndarray) -> float | None:
        if len(self._stacked_time) == 0:
            return None
        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        if t < t_min or t > t_max:
            return None
        return float(np.interp(t, self._stacked_time, values))

    def _rebuild_stacked_plots(self, result: SimulationResult | None) -> None:
        self._clear_stacked_plots()

        if not result or len(self._stacked_time) == 0 or not self._stacked_signals:
            empty = QLabel("No signals to plot. Connect scope channels and run simulation.")
            empty.setWordWrap(True)
            self._stacked_layout.addWidget(empty)
            self._stacked_layout.addStretch()
            return

        time = self._stacked_time
        palette = self._trace_palette()
        first_plot: pg.PlotWidget | None = None
        visible = set(self._stacked_signal_list.get_visible_signals())
        signal_items = [
            (name, values)
            for name, values in self._stacked_signals.items()
            if not visible or name in visible
        ]

        if not signal_items:
            empty = QLabel("No visible signals. Enable at least one signal in the list.")
            empty.setWordWrap(True)
            self._stacked_layout.addWidget(empty)
            self._stacked_layout.addStretch()
            return

        points_per_signal = self._stacked_target_points_per_signal(len(signal_items))

        for idx, (name, values) in enumerate(signal_items):
            t, plot_values = self._decimate_stacked_for_display(
                time,
                values,
                max_points=points_per_signal,
            )

            panel = QFrame()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(2)

            title = QLabel(name)
            if name == self._stacked_active_signal:
                title.setText(f"{name} (active)")
            panel_layout.addWidget(title)

            plot = pg.PlotWidget()
            plot.setMinimumHeight(200)
            grid_alpha = 0.25 if self._stacked_grid_enabled else 0.0
            plot.showGrid(x=self._stacked_grid_enabled, y=self._stacked_grid_enabled, alpha=grid_alpha)
            color = self._stacked_signal_list.get_signal_color(name)
            if color is None:
                color = palette[idx % len(palette)]
            color_override = self._trace_style_color(name)
            line_color = color_override if color_override is not None else color
            line_width = self._trace_style_width(name)
            trace = plot.plot(
                t,
                plot_values,
                pen=pg.mkPen(color=line_color, width=line_width),
                skipFiniteCheck=True,
            )
            self._configure_stacked_trace_performance(trace, len(t))

            item = plot.getPlotItem()
            item.setLabel("left", "")
            if idx == len(signal_items) - 1:
                item.setLabel("bottom", "Time", units="s")
            else:
                item.getAxis("bottom").setStyle(showValues=False)

            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)

            if self._stacked_cursors_enabled:
                cursor_palette = self._cursor_palette() or [(255, 0, 0), (0, 0, 255)]
                c1_line = pg.InfiniteLine(
                    pos=self._c1_spin.value(),
                    angle=90,
                    movable=True,
                    pen=pg.mkPen(color=cursor_palette[0], width=1.8, style=Qt.PenStyle.DashLine),
                )
                c2_line = pg.InfiniteLine(
                    pos=self._c2_spin.value(),
                    angle=90,
                    movable=True,
                    pen=pg.mkPen(color=cursor_palette[1], width=1.8, style=Qt.PenStyle.DashLine),
                )
                c1_line.sigPositionChanged.connect(
                    lambda *_args, line=c1_line: self._on_stacked_plot_cursor_moved(1, float(line.value()))
                )
                c2_line.sigPositionChanged.connect(
                    lambda *_args, line=c2_line: self._on_stacked_plot_cursor_moved(2, float(line.value()))
                )
                plot.addItem(c1_line)
                plot.addItem(c2_line)
                self._stacked_cursor_lines.append((c1_line, c2_line))

            if self._theme is not None:
                c = self._theme.colors
                plot.setBackground(c.plot_background)
                for axis_name in ("left", "bottom"):
                    axis = item.getAxis(axis_name)
                    axis.setPen(pg.mkPen(c.plot_axis))
                    axis.setTickPen(pg.mkPen(c.plot_axis))
                    axis.setTextPen(pg.mkPen(c.plot_text))
                title.setStyleSheet(f"color: {c.foreground}; font-weight: 600;")
                panel.setStyleSheet(
                    f"background-color: {c.background}; border: 1px solid {c.panel_border}; border-radius: 6px;"
                )
            else:
                title.setStyleSheet("font-weight: 600;")

            panel_layout.addWidget(plot)
            self._stacked_layout.addWidget(panel)
            self._plot_widgets.append(plot)

        self._stacked_layout.addStretch()

    def _format_status(self, found: list[str], missing: list[str]) -> str:
        found_count = len(found)
        missing_count = len(missing)
        if found_count and missing_count:
            return f"Loaded {found_count} signal(s); missing {missing_count} channel target(s)."
        if found_count:
            return f"Loaded {found_count} signal(s)."
        if missing_count:
            return f"No matching data; missing {missing_count} channel target(s)."
        return "Waiting for matching signals..."

    def _format_signal_label(self, binding: ScopeChannelBinding, signal: ScopeSignal, index: int) -> str:
        if len(binding.signals) == 1:
            signal_label = signal.label or signal.signal_key or binding.display_name
            return f"{binding.channel_label}: {signal_label}"
        suffix = signal.label or f"Signal {index + 1}"
        return f"{binding.display_name}/{suffix}"

    @staticmethod
    def _ensure_unique_label(label: str, existing: dict[str, list[float]]) -> str:
        if label not in existing:
            return label
        idx = 2
        candidate = f"{label} [{idx}]"
        while candidate in existing:
            idx += 1
            candidate = f"{label} [{idx}]"
        return candidate
