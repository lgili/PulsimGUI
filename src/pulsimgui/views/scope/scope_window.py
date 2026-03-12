"""Floating windows that host per-component scope viewers."""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QGuiApplication,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPen,
    QShortcut,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.component import ComponentType
from pulsimgui.resources.icons import IconService
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.theme_service import Theme, ThemeService
from pulsimgui.views.waveform import WaveformViewer
from pulsimgui.views.waveform.waveform_viewer import (
    TRACE_COLORS,
    MeasurementsPanel,
    SignalListPanel,
)

from .bindings import ScopeChannelBinding, ScopeSignal


class MathSignalDialog(QDialog):
    """Dialog that encapsulates math signal interactions."""
    def __init__(
        self,
        parent: QWidget,
        signal_names: list[str],
        default_signal: str,
        theme: Theme | None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Math Signal")
        self.setModal(True)
        self.setMinimumWidth(500)
        self._signal_names = signal_names

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Math Signal")
        title.setObjectName("mathSignalDialogTitle")
        subtitle = QLabel("Create derived traces from one or two signals")
        subtitle.setObjectName("mathSignalDialogSubtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        inputs_section = QLabel("Inputs")
        inputs_section.setObjectName("mathSignalSection")
        layout.addWidget(inputs_section)
        inputs_form = QFormLayout()
        inputs_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        inputs_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        inputs_form.setHorizontalSpacing(10)
        inputs_form.setVerticalSpacing(8)
        self._source_a_combo = QComboBox()
        self._source_a_combo.addItems(signal_names)
        idx = self._source_a_combo.findText(default_signal)
        if idx >= 0:
            self._source_a_combo.setCurrentIndex(idx)
        inputs_form.addRow("Signal A", self._source_a_combo)

        self._source_b_label = QLabel("Signal B")
        self._source_b_combo = QComboBox()
        self._source_b_combo.addItems(signal_names)
        if idx >= 0:
            self._source_b_combo.setCurrentIndex(idx)
        inputs_form.addRow(self._source_b_label, self._source_b_combo)

        self._swap_sources_btn = QPushButton("Swap A ↔ B")
        self._swap_sources_btn.setObjectName("mathSignalSwapBtn")
        self._swap_sources_btn.clicked.connect(self._on_swap_sources_clicked)
        inputs_form.addRow("", self._swap_sources_btn)
        layout.addLayout(inputs_form)

        transform_section = QLabel("Transform")
        transform_section.setObjectName("mathSignalSection")
        layout.addWidget(transform_section)
        transform_form = QFormLayout()
        transform_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        transform_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        transform_form.setHorizontalSpacing(10)
        transform_form.setVerticalSpacing(8)

        self._operation_combo = QComboBox()
        self._operation_combo.addItem("Add (A + B)", "ADD")
        self._operation_combo.addItem("Subtract (A - B)", "SUB")
        self._operation_combo.addItem("Multiply (A × B)", "MUL")
        self._operation_combo.addItem("Divide (A / B)", "DIV")
        self._operation_combo.addItem("Moving Average", "AVG")
        self._operation_combo.addItem("Negate (-A)", "NEG")
        self._operation_combo.addItem("Absolute (|A|)", "ABS")
        self._operation_combo.addItem("Square (A²)", "SQR")
        self._operation_combo.addItem("Derivative (dA/dt)", "DER")
        self._operation_combo.addItem("Integral (∫A dt)", "INT")
        transform_form.addRow("Operation", self._operation_combo)

        self._window_label = QLabel("Window")
        self._window_spin = QSpinBox()
        self._window_spin.setRange(2, 5000)
        self._window_spin.setValue(16)
        self._window_spin.setSingleStep(2)
        transform_form.addRow(self._window_label, self._window_spin)

        self._gain_spin = QDoubleSpinBox()
        self._gain_spin.setDecimals(4)
        self._gain_spin.setRange(-1e6, 1e6)
        self._gain_spin.setValue(1.0)
        self._gain_spin.setSingleStep(0.1)
        transform_form.addRow("Gain", self._gain_spin)

        self._offset_spin = QDoubleSpinBox()
        self._offset_spin.setDecimals(6)
        self._offset_spin.setRange(-1e12, 1e12)
        self._offset_spin.setValue(0.0)
        self._offset_spin.setSingleStep(0.1)
        transform_form.addRow("Offset", self._offset_spin)
        layout.addLayout(transform_form)

        output_section = QLabel("Output")
        output_section.setObjectName("mathSignalSection")
        layout.addWidget(output_section)
        output_form = QFormLayout()
        output_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        output_form.setFormAlignment(Qt.AlignmentFlag.AlignTop)
        output_form.setHorizontalSpacing(10)
        output_form.setVerticalSpacing(8)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Auto")
        output_form.addRow("Result Name", self._name_edit)

        self._preview_label = QLabel("Preview: --")
        self._preview_label.setObjectName("mathSignalPreview")

        layout.addLayout(output_form)
        layout.addWidget(self._preview_label)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("Create")
        cancel_btn = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn is not None:
            cancel_btn.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._operation_combo.currentIndexChanged.connect(self._update_state)
        self._source_a_combo.currentIndexChanged.connect(self._update_state)
        self._source_b_combo.currentIndexChanged.connect(self._update_state)
        self._gain_spin.valueChanged.connect(self._update_state)
        self._offset_spin.valueChanged.connect(self._update_state)
        self._window_spin.valueChanged.connect(self._update_state)

        if theme is not None:
            c = theme.colors
            self.setStyleSheet(f"""
                QDialog {{
                    background-color: {c.panel_background};
                    border: 1px solid {c.panel_border};
                    border-radius: 12px;
                }}
                QLabel#mathSignalDialogTitle {{
                    font-size: 18px;
                    font-weight: 700;
                    color: {c.foreground};
                }}
                QLabel#mathSignalDialogSubtitle {{
                    font-size: 12px;
                    color: {c.foreground_muted};
                }}
                QLabel#mathSignalSection {{
                    font-size: 11px;
                    font-weight: 700;
                    color: {c.foreground};
                    margin-top: 4px;
                }}
                QLabel#mathSignalPreview {{
                    font-size: 11px;
                    font-weight: 600;
                    color: {c.primary};
                    background-color: {c.background_alt};
                    border: 1px solid {c.panel_border};
                    border-radius: 10px;
                    padding: 7px 10px;
                }}
                QComboBox, QDoubleSpinBox, QLineEdit {{
                    background-color: {c.input_background};
                    color: {c.foreground};
                    border: 1px solid {c.input_border};
                    border-radius: 10px;
                    padding: 5px 9px;
                    min-height: 28px;
                }}
                QPushButton {{
                    background-color: {c.secondary};
                    color: {c.foreground};
                    border: 1px solid {c.border};
                    border-radius: 10px;
                    padding: 6px 12px;
                    min-height: 28px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: {c.secondary_hover};
                    border-color: {c.primary};
                }}
                QPushButton#mathSignalSwapBtn {{
                    min-width: 108px;
                }}
                QDialogButtonBox QPushButton {{
                    min-width: 94px;
                }}
            """)

        self._update_state()

    def _current_operation(self) -> str:
        data = self._operation_combo.currentData()
        return str(data) if data is not None else "ADD"

    def _operation_needs_b(self, op_code: str) -> bool:
        return op_code in {"ADD", "SUB", "MUL", "DIV"}

    def _operation_needs_window(self, op_code: str) -> bool:
        return op_code == "AVG"

    def _on_swap_sources_clicked(self) -> None:
        idx_a = self._source_a_combo.currentIndex()
        idx_b = self._source_b_combo.currentIndex()
        self._source_a_combo.setCurrentIndex(idx_b)
        self._source_b_combo.setCurrentIndex(idx_a)
        self._update_state()

    def _update_state(self) -> None:
        op_code = self._current_operation()
        needs_b = self._operation_needs_b(op_code)
        needs_window = self._operation_needs_window(op_code)
        self._source_b_label.setVisible(needs_b)
        self._source_b_combo.setVisible(needs_b)
        self._swap_sources_btn.setVisible(needs_b)
        self._window_label.setVisible(needs_window)
        self._window_spin.setVisible(needs_window)

        source_a = self._source_a_combo.currentText().strip()
        source_b = self._source_b_combo.currentText().strip()
        gain = self._gain_spin.value()
        offset = self._offset_spin.value()

        if needs_b:
            expr = f"{source_a} {op_code} {source_b}"
        elif needs_window:
            expr = f"AVG({source_a}, N={self._window_spin.value()})"
        else:
            expr = f"{op_code}({source_a})"

        extras = []
        if abs(gain - 1.0) > 1e-12:
            extras.append(f"×{gain:.4g}")
        if abs(offset) > 1e-12:
            extras.append(f"+{offset:.4g}")
        if extras:
            expr = f"{expr} {' '.join(extras)}"

        self._preview_label.setText(f"Preview: {expr}")

    def selected_config(self) -> dict[str, object]:
        """Return the currently selected math-signal configuration."""
        op_code = self._current_operation()
        source_a = self._source_a_combo.currentText().strip()
        source_b = self._source_b_combo.currentText().strip()
        custom_name = self._name_edit.text().strip()
        return {
            "operation": op_code,
            "source_a": source_a,
            "source_b": source_b,
            "gain": float(self._gain_spin.value()),
            "offset": float(self._offset_spin.value()),
            "window": int(self._window_spin.value()),
            "custom_name": custom_name,
            "needs_b": self._operation_needs_b(op_code),
            "needs_window": self._operation_needs_window(op_code),
        }


class TimeRangeSlider(QWidget):
    """Custom slider widget used by time range workflows."""
    rangeChanged = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scopeTimelineSlider")
        self.setMinimumHeight(28)
        self._minimum = 0
        self._maximum = 1000
        self._low = 0
        self._high = 1000
        self._drag_target: str | None = None
        self._handle_radius = 7
        self._track_height = 6

        self._track_bg = QColor("#3a3f4b")
        self._track_border = QColor("#5a6272")
        self._selected_fill = QColor("#4b8bff")
        self._handle_fill = QColor("#d8deea")
        self._handle_border = QColor("#6a7386")

    def set_theme_colors(
        self,
        *,
        track_bg: QColor,
        track_border: QColor,
        selected_fill: QColor,
        handle_fill: QColor,
        handle_border: QColor,
    ) -> None:
        """Update theme_colors for this widget."""
        self._track_bg = track_bg
        self._track_border = track_border
        self._selected_fill = selected_fill
        self._handle_fill = handle_fill
        self._handle_border = handle_border
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        """Update the slider numeric range."""
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum + 1)
        self.setValues(self._low, self._high)

    def setValues(self, low: int, high: int) -> None:
        """Update the low/high slider values."""
        low_clamped = max(self._minimum, min(int(low), self._maximum - 1))
        high_clamped = max(low_clamped + 1, min(int(high), self._maximum))
        changed = (low_clamped != self._low) or (high_clamped != self._high)
        self._low = low_clamped
        self._high = high_clamped
        if changed:
            self.rangeChanged.emit(self._low, self._high)
        self.update()

    def lowValue(self) -> int:
        """Return the current low value value."""
        return self._low

    def highValue(self) -> int:
        """Return the current high value value."""
        return self._high

    def minimum(self) -> int:
        """Return the current minimum value."""
        return self._minimum

    def maximum(self) -> int:
        """Return the current maximum value."""
        return self._maximum

    def _track_geometry(self) -> tuple[int, int, int, int]:
        left = self._handle_radius + 4
        right = max(left + 20, self.width() - self._handle_radius - 4)
        y = (self.height() - self._track_height) // 2
        return left, right, y, self._track_height

    def _value_to_x(self, value: int) -> int:
        left, right, _, _ = self._track_geometry()
        span = max(1, self._maximum - self._minimum)
        ratio = (value - self._minimum) / span
        return int(round(left + ratio * (right - left)))

    def _x_to_value(self, x: int) -> int:
        left, right, _, _ = self._track_geometry()
        clamped_x = min(max(x, left), right)
        span_px = max(1, right - left)
        ratio = (clamped_x - left) / span_px
        value = self._minimum + ratio * (self._maximum - self._minimum)
        return int(round(value))

    def paintEvent(self, _event) -> None:
        """Render the widget contents for the current frame."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        left, right, y, h = self._track_geometry()
        low_x = self._value_to_x(self._low)
        high_x = self._value_to_x(self._high)

        painter.setPen(QPen(self._track_border, 1))
        painter.setBrush(QBrush(self._track_bg))
        painter.drawRoundedRect(left, y, max(1, right - left), h, 3, 3)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._selected_fill))
        painter.drawRoundedRect(low_x, y, max(1, high_x - low_x), h, 3, 3)

        for x in (low_x, high_x):
            painter.setPen(QPen(self._handle_border, 1.2))
            painter.setBrush(QBrush(self._handle_fill))
            painter.drawEllipse(x - self._handle_radius, (self.height() // 2) - self._handle_radius, self._handle_radius * 2, self._handle_radius * 2)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle the Qt mousePressEvent callback."""
        if not self.isEnabled() or event.button() != Qt.MouseButton.LeftButton:
            return
        low_x = self._value_to_x(self._low)
        high_x = self._value_to_x(self._high)
        click_x = int(event.position().x())

        if abs(click_x - low_x) <= abs(click_x - high_x):
            self._drag_target = "low"
        else:
            self._drag_target = "high"
        self._update_from_mouse(click_x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle the Qt mouseMoveEvent callback."""
        if not self.isEnabled() or self._drag_target is None:
            return
        self._update_from_mouse(int(event.position().x()))

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        """Handle the Qt mouseReleaseEvent callback."""
        self._drag_target = None

    def _update_from_mouse(self, x: int) -> None:
        value = self._x_to_value(x)
        if self._drag_target == "low":
            self.setValues(value, self._high)
        elif self._drag_target == "high":
            self.setValues(self._low, value)


class ScopePlotViewBox(pg.ViewBox):
    """Custom ViewBox to handle scope-oriented wheel zoom and plot selection."""

    def __init__(
        self,
        *,
        group_leader: str,
        wheel_handler: Callable[[pg.ViewBox, object, str], bool] | None = None,
        select_handler: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(enableMenu=False)
        self._group_leader = group_leader
        self._wheel_handler = wheel_handler
        self._select_handler = select_handler

    def wheelEvent(self, ev, axis=None):
        if self._wheel_handler is not None and self._wheel_handler(self, ev, self._group_leader):
            return
        super().wheelEvent(ev, axis=axis)

    def mouseClickEvent(self, ev) -> None:
        if (
            self._select_handler is not None
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            self._select_handler(self._group_leader)
        super().mouseClickEvent(ev)


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
        self.setMinimumSize(960, 660)

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
        self._math_signal_counter = 0
        self._stacked_cursors_enabled = False
        self._left_panel_visible = True
        self._right_panel_visible = True
        self._left_panel_width = 300
        self._right_panel_width = 300
        self._collapsed_panel_width = 64
        self._stacked_grid_enabled = True
        self._stacked_cursor_lines: list[tuple[pg.InfiniteLine, pg.InfiniteLine]] = []
        self._stacked_hover_items: list[tuple[pg.InfiniteLine, pg.InfiniteLine, pg.TextItem]] = []
        self._stacked_plot_interaction_refs: list[tuple[object, object]] = []
        self._syncing_stacked_cursor_controls = False
        self._stacked_cursor_initialized = False
        self._trace_styles: dict[str, dict[str, object]] = {}
        self._stacked_plot_groups: dict[str, str] = {}
        self._selected_plot_group_leader: str | None = None
        self._default_trace_width = self.DEFAULT_TRACE_WIDTH
        self._syncing_trace_style_controls = False
        self._syncing_bottom_sliders = False

        self._viewer = WaveformViewer(theme_service=self._theme_service)
        self._viewer.setMinimumSize(820, 500)
        self._viewer.set_manual_signal_add_enabled(False)
        self._viewer.set_auto_show_all_signals(True)
        self._viewer.set_default_trace_width(self._default_trace_width)
        self._viewer.set_trace_styles(self._trace_styles)

        self._trace_signal_combo = QComboBox()
        self._trace_signal_combo.setMinimumWidth(260)
        self._trace_signal_combo.currentTextChanged.connect(self._on_trace_style_signal_changed)
        self._trace_width_spin = QDoubleSpinBox()
        self._trace_width_spin.setRange(0.5, 8.0)
        self._trace_width_spin.setSingleStep(0.2)
        self._trace_width_spin.setDecimals(1)
        self._trace_width_spin.setMaximumWidth(86)
        self._trace_width_spin.setValue(self._default_trace_width)
        self._trace_width_spin.valueChanged.connect(self._on_trace_width_changed)
        self._trace_color_btn = QPushButton("Color")
        self._trace_color_btn.clicked.connect(self._on_trace_color_clicked)
        self._trace_reset_btn = QPushButton("Reset")
        self._trace_reset_btn.clicked.connect(self._on_trace_style_reset)

        self._stacked_page = QWidget()
        self._stacked_page.setObjectName("scopePlotSurface")
        stacked_page_layout = QVBoxLayout(self._stacked_page)
        stacked_page_layout.setContentsMargins(0, 0, 0, 0)
        stacked_page_layout.setSpacing(0)
        self._stacked_splitter = QSplitter(Qt.Orientation.Horizontal)
        stacked_page_layout.addWidget(self._stacked_splitter)

        self._stacked_sidebar = QWidget()
        self._stacked_sidebar.setObjectName("scopeLeftPanel")
        self._stacked_sidebar.setMinimumWidth(270)
        self._stacked_sidebar.setMaximumWidth(380)
        stacked_sidebar_layout = QVBoxLayout(self._stacked_sidebar)
        stacked_sidebar_layout.setContentsMargins(8, 8, 8, 8)
        stacked_sidebar_layout.setSpacing(6)

        sidebar_top = QWidget()
        self._left_sidebar_top_row = sidebar_top
        sidebar_top_layout = QHBoxLayout(sidebar_top)
        sidebar_top_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_top_layout.setSpacing(8)
        self._left_scope_label = QLabel("Scope:")
        sidebar_top_layout.addWidget(self._left_scope_label)
        self._scope_selector_combo = QComboBox()
        self._scope_selector_combo.setMinimumWidth(130)
        self._scope_selector_combo.currentTextChanged.connect(self._on_scope_selector_changed)
        sidebar_top_layout.addWidget(self._scope_selector_combo, stretch=1)
        self._left_panel_toggle_btn = QPushButton("◀")
        self._left_panel_toggle_btn.setObjectName("scopePanelToggleBtn")
        self._left_panel_toggle_btn.setCheckable(True)
        self._left_panel_toggle_btn.setChecked(True)
        self._left_panel_toggle_btn.setFixedWidth(28)
        self._left_panel_toggle_btn.setToolTip("Collapse left panel")
        self._left_panel_toggle_btn.clicked.connect(self._on_toggle_left_panel_clicked)
        self._toggle_sidebar_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self._toggle_sidebar_shortcut.activated.connect(self._on_toggle_sidebar_shortcut)
        sidebar_top_layout.addWidget(self._left_panel_toggle_btn, stretch=0)

        sidebar_actions = QWidget()
        self._left_sidebar_actions_row = sidebar_actions
        sidebar_actions_layout = QHBoxLayout(sidebar_actions)
        sidebar_actions_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_actions_layout.setSpacing(8)
        self._create_math_signal_btn = QPushButton("Math Signal")
        self._create_math_signal_btn.setObjectName("scopeMathSignalBtn")
        self._create_math_signal_btn.setMinimumWidth(112)
        self._create_math_signal_btn.clicked.connect(self._on_create_math_signal_clicked)
        sidebar_actions_layout.addWidget(self._create_math_signal_btn, stretch=1)
        stacked_sidebar_layout.addWidget(sidebar_top, stretch=0)
        stacked_sidebar_layout.addWidget(sidebar_actions, stretch=0)

        self._stacked_cursor_toggle = QCheckBox("Cursors")
        self._stacked_cursor_toggle.setChecked(self._stacked_cursors_enabled)
        self._stacked_cursor_toggle.toggled.connect(self._on_stacked_cursor_toggled)

        self._stacked_grid_toggle = QCheckBox("Grid")
        self._stacked_grid_toggle.setChecked(self._stacked_grid_enabled)
        self._stacked_grid_toggle.toggled.connect(self._on_stacked_grid_toggled)

        self._c1_label = QLabel("C1")
        self._c1_spin = QDoubleSpinBox()
        self._c1_spin.setKeyboardTracking(False)
        self._c1_spin.setDecimals(8)
        self._c1_spin.setSingleStep(1e-6)
        self._c1_spin.setMaximumWidth(92)
        self._c1_spin.valueChanged.connect(self._on_stacked_cursor_changed)

        self._c2_label = QLabel("C2")
        self._c2_spin = QDoubleSpinBox()
        self._c2_spin.setKeyboardTracking(False)
        self._c2_spin.setDecimals(8)
        self._c2_spin.setSingleStep(1e-6)
        self._c2_spin.setMaximumWidth(92)
        self._c2_spin.valueChanged.connect(self._on_stacked_cursor_changed)

        self._stacked_signal_list = SignalListPanel()
        self._stacked_signal_list.setMinimumWidth(200)
        self._stacked_signal_list.setMaximumWidth(320)
        self._stacked_signal_list._compact_max_rows = 10
        self._stacked_signal_list.signal_visibility_changed.connect(
            self._on_stacked_signal_visibility_changed
        )
        self._stacked_signal_list.signal_selected.connect(self._on_stacked_signal_selected)
        self._stacked_signal_list.signal_double_clicked.connect(self._on_stacked_signal_double_clicked)
        stacked_sidebar_layout.addWidget(self._stacked_signal_list, stretch=1)

        self._stacked_measurements = MeasurementsPanel()
        self._stacked_measurements.setMinimumWidth(260)
        self._stacked_measurements.setMaximumWidth(460)

        self._stacked_right_panel = QWidget()
        self._stacked_right_panel.setObjectName("scopeRightPanel")
        self._stacked_right_panel.setMinimumWidth(280)
        self._stacked_right_panel.setMaximumWidth(420)
        right_layout = QVBoxLayout(self._stacked_right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        right_header = QWidget()
        self._right_header_row = right_header
        right_header_layout = QHBoxLayout(right_header)
        right_header_layout.setContentsMargins(0, 0, 0, 0)
        right_header_layout.setSpacing(8)
        self._right_header_label = QLabel("Measurements")
        right_header_layout.addWidget(self._right_header_label, stretch=1)
        self._trace_style_menu_btn = QToolButton()
        self._trace_style_menu_btn.setObjectName("scopeTraceMenuBtn")
        self._trace_style_menu_btn.setText("")
        self._trace_style_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._trace_style_menu = QMenu(self._trace_style_menu_btn)
        self._trace_style_menu.aboutToShow.connect(self._populate_trace_style_menu)
        self._trace_style_menu_btn.setMenu(self._trace_style_menu)
        self._right_panel_toggle_btn = QPushButton("▶")
        self._right_panel_toggle_btn.setObjectName("scopePanelToggleBtn")
        self._right_panel_toggle_btn.setCheckable(True)
        self._right_panel_toggle_btn.setChecked(True)
        self._right_panel_toggle_btn.setFixedWidth(28)
        self._right_panel_toggle_btn.setToolTip("Collapse right panel")
        self._right_panel_toggle_btn.clicked.connect(self._on_toggle_right_panel_clicked)
        right_header_layout.addWidget(self._right_panel_toggle_btn, stretch=0)
        right_layout.addWidget(right_header, stretch=0)

        right_controls = QWidget()
        self._stacked_right_controls = right_controls
        right_controls.setObjectName("scopeRightControlBar")
        right_controls_layout = QHBoxLayout(right_controls)
        right_controls_layout.setContentsMargins(0, 0, 0, 0)
        right_controls_layout.setSpacing(8)
        right_controls_layout.addWidget(self._stacked_cursor_toggle)
        right_controls_layout.addWidget(self._stacked_grid_toggle)
        right_controls_layout.addStretch(1)
        right_layout.addWidget(right_controls, stretch=0)

        right_layout.addWidget(self._stacked_measurements, stretch=1)

        self._stacked_scroll = QScrollArea()
        self._stacked_scroll.setObjectName("scopeStackedScroll")
        self._stacked_scroll.setWidgetResizable(True)
        self._stacked_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._stacked_content = QWidget()
        self._stacked_content.setObjectName("scopeStackedScrollContent")
        self._stacked_layout = QVBoxLayout(self._stacked_content)
        self._stacked_layout.setContentsMargins(8, 8, 8, 8)
        self._stacked_layout.setSpacing(8)
        self._stacked_layout.addStretch()
        self._stacked_scroll.setWidget(self._stacked_content)

        self._stacked_splitter.addWidget(self._stacked_sidebar)
        self._stacked_splitter.addWidget(self._stacked_scroll)
        self._stacked_splitter.addWidget(self._stacked_right_panel)
        self._stacked_splitter.setCollapsible(0, False)
        self._stacked_splitter.setCollapsible(1, False)
        self._stacked_splitter.setCollapsible(2, False)
        self._stacked_splitter.setStretchFactor(0, 2)
        self._stacked_splitter.setStretchFactor(1, 7)
        self._stacked_splitter.setStretchFactor(2, 2)
        self._stacked_splitter.setSizes([300, 900, 300])
        self._stacked_splitter.splitterMoved.connect(self._on_splitter_moved)

        self._mapping_label = QLabel()
        self._mapping_label.setWordWrap(False)
        self._mapping_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._mapping_label.setObjectName("scopeMappingLabel")

        self._message_label = QLabel("Waiting for simulation results...")
        self._message_label.setWordWrap(False)
        self._message_label.setObjectName("scopeMessageLabel")

        self._scope_toolbar = QWidget()
        self._scope_toolbar.setObjectName("scopeTopChrome")
        chrome_layout = QVBoxLayout(self._scope_toolbar)
        chrome_layout.setContentsMargins(0, 0, 0, 0)
        chrome_layout.setSpacing(0)

        self._scope_menu_row = QWidget()
        self._scope_menu_row.setObjectName("scopeTopMenuRow")
        menu_layout = QHBoxLayout(self._scope_menu_row)
        menu_layout.setContentsMargins(10, 5, 10, 5)
        menu_layout.setSpacing(6)

        self._scope_brand_label = QLabel("VirtuScope")
        self._scope_brand_label.setObjectName("scopeBrandLabel")
        menu_layout.addWidget(self._scope_brand_label)
        menu_layout.addSpacing(12)

        self._menu_file_btn = QToolButton()
        self._menu_file_btn.setObjectName("scopeMenuTextBtn")
        self._menu_file_btn.setText("File")
        self._menu_file_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_file_btn)

        self._menu_view_btn = QToolButton()
        self._menu_view_btn.setObjectName("scopeMenuTextBtn")
        self._menu_view_btn.setText("View")
        self._menu_view_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_view_btn)

        self._menu_sim_btn = QToolButton()
        self._menu_sim_btn.setObjectName("scopeMenuTextBtn")
        self._menu_sim_btn.setText("Simulation")
        self._menu_sim_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_sim_btn)

        self._menu_help_btn = QToolButton()
        self._menu_help_btn.setObjectName("scopeMenuTextBtn")
        self._menu_help_btn.setText("Help")
        self._menu_help_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_help_btn)

        menu_layout.addStretch(1)
        self._scope_version_label = QLabel("Scope v1.0")
        self._scope_version_label.setObjectName("scopeVersionLabel")
        menu_layout.addWidget(self._scope_version_label)
        chrome_layout.addWidget(self._scope_menu_row)

        self._scope_tool_row = QWidget()
        self._scope_tool_row.setObjectName("scopeToolbarRow")
        toolbar_layout = QHBoxLayout(self._scope_tool_row)
        toolbar_layout.setContentsMargins(10, 4, 10, 4)
        toolbar_layout.setSpacing(4)

        self._toolbar_left_btn = QToolButton()
        self._toolbar_left_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_left_btn.setCheckable(True)
        self._toolbar_left_btn.setChecked(True)
        self._toolbar_left_btn.setToolTip("Toggle signals panel (Ctrl+B)")
        self._toolbar_left_btn.toggled.connect(self._on_toolbar_left_toggled)
        toolbar_layout.addWidget(self._toolbar_left_btn)

        self._toolbar_cursor_btn = QToolButton()
        self._toolbar_cursor_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_cursor_btn.setCheckable(True)
        self._toolbar_cursor_btn.setChecked(False)
        self._toolbar_cursor_btn.setToolTip("Enable cursors")
        self._toolbar_cursor_btn.toggled.connect(self._on_toolbar_cursor_toggled)
        toolbar_layout.addWidget(self._toolbar_cursor_btn)

        self._toolbar_grid_btn = QToolButton()
        self._toolbar_grid_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_grid_btn.setCheckable(True)
        self._toolbar_grid_btn.setChecked(True)
        self._toolbar_grid_btn.setToolTip("Toggle grid")
        self._toolbar_grid_btn.toggled.connect(self._on_toolbar_grid_toggled)
        toolbar_layout.addWidget(self._toolbar_grid_btn)

        self._toolbar_separator_1 = QFrame()
        self._toolbar_separator_1.setObjectName("scopeToolbarSeparator")
        self._toolbar_separator_1.setFrameShape(QFrame.Shape.VLine)
        self._toolbar_separator_1.setFrameShadow(QFrame.Shadow.Plain)
        toolbar_layout.addWidget(self._toolbar_separator_1)

        self._toolbar_autoscale_btn = QToolButton()
        self._toolbar_autoscale_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_autoscale_btn.setToolTip("Fit view (AutoScale)")
        self._toolbar_autoscale_btn.clicked.connect(self._on_autoscale_clicked)
        toolbar_layout.addWidget(self._toolbar_autoscale_btn)

        self._toolbar_math_btn = QToolButton()
        self._toolbar_math_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_math_btn.setToolTip("Create math signal")
        self._toolbar_math_btn.clicked.connect(self._on_create_math_signal_clicked)
        toolbar_layout.addWidget(self._toolbar_math_btn)

        self._trace_style_menu_btn.setObjectName("scopeToolbarBtn")
        self._trace_style_menu_btn.setToolTip("Trace style and plot placement")
        self._trace_style_menu_btn.setAutoRaise(False)
        self._trace_style_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar_layout.addWidget(self._trace_style_menu_btn)

        self._toolbar_separator_2 = QFrame()
        self._toolbar_separator_2.setObjectName("scopeToolbarSeparator")
        self._toolbar_separator_2.setFrameShape(QFrame.Shape.VLine)
        self._toolbar_separator_2.setFrameShadow(QFrame.Shadow.Plain)
        toolbar_layout.addWidget(self._toolbar_separator_2)

        self._toolbar_right_btn = QToolButton()
        self._toolbar_right_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_right_btn.setCheckable(True)
        self._toolbar_right_btn.setChecked(True)
        self._toolbar_right_btn.setToolTip("Toggle measurements panel")
        self._toolbar_right_btn.toggled.connect(self._on_toolbar_right_toggled)
        toolbar_layout.addWidget(self._toolbar_right_btn)

        self._toolbar_copy_btn = QToolButton()
        self._toolbar_copy_btn.setObjectName("scopeToolbarBtn")
        self._toolbar_copy_btn.setToolTip("Copy active plot image")
        self._toolbar_copy_btn.clicked.connect(
            lambda _checked=False: self._copy_plot_to_clipboard(
                self._plot_widgets[0] if self._plot_widgets else None
            )
        )
        toolbar_layout.addWidget(self._toolbar_copy_btn)

        toolbar_layout.addStretch(1)
        self._toolbar_scope_label = QLabel()
        self._toolbar_scope_label.setObjectName("scopeToolbarScopeLabel")
        self._toolbar_scope_label.setText("No signal")
        toolbar_layout.addWidget(self._toolbar_scope_label)
        chrome_layout.addWidget(self._scope_tool_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        layout.addWidget(self._scope_toolbar, stretch=0)
        layout.addWidget(self._stacked_page, stretch=1)

        self._scope_bottom_controls = QWidget()
        self._scope_bottom_controls.setObjectName("scopeBottomControlBar")
        bottom_layout = QHBoxLayout(self._scope_bottom_controls)
        bottom_layout.setContentsMargins(8, 6, 8, 6)
        bottom_layout.setSpacing(8)

        bottom_layout.addWidget(QLabel("Timeline"))
        self._timeline_dec_btn = QPushButton("◀")
        self._timeline_dec_btn.setObjectName("scopeSliderStepBtn")
        self._timeline_dec_btn.setFixedWidth(24)
        self._timeline_dec_btn.clicked.connect(lambda: self._step_timeline_window(-20))
        bottom_layout.addWidget(self._timeline_dec_btn)

        self._timeline_slider = TimeRangeSlider()
        self._timeline_slider.setRange(0, 1000)
        self._timeline_slider.setValues(0, 1000)
        self._timeline_slider.rangeChanged.connect(self._on_timeline_slider_changed)
        bottom_layout.addWidget(self._timeline_slider, stretch=4)

        self._timeline_inc_btn = QPushButton("▶")
        self._timeline_inc_btn.setObjectName("scopeSliderStepBtn")
        self._timeline_inc_btn.setFixedWidth(24)
        self._timeline_inc_btn.clicked.connect(lambda: self._step_timeline_window(20))
        bottom_layout.addWidget(self._timeline_inc_btn)

        self._timeline_range_label = QLabel("-- to --")
        self._timeline_range_label.setObjectName("scopeSliderInfoLabel")
        self._timeline_range_label.setMinimumWidth(145)
        bottom_layout.addWidget(self._timeline_range_label)

        bottom_layout.addWidget(QLabel("Zoom"))
        self._zoom_dec_btn = QPushButton("−")
        self._zoom_dec_btn.setObjectName("scopeSliderStepBtn")
        self._zoom_dec_btn.setFixedWidth(24)
        self._zoom_dec_btn.clicked.connect(lambda: self._step_slider(self._zoom_slider, -5))
        bottom_layout.addWidget(self._zoom_dec_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setObjectName("scopeZoomSlider")
        self._zoom_slider.setRange(0, 100)
        self._zoom_slider.setValue(0)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        bottom_layout.addWidget(self._zoom_slider, stretch=3)

        self._zoom_inc_btn = QPushButton("+")
        self._zoom_inc_btn.setObjectName("scopeSliderStepBtn")
        self._zoom_inc_btn.setFixedWidth(24)
        self._zoom_inc_btn.clicked.connect(lambda: self._step_slider(self._zoom_slider, 5))
        bottom_layout.addWidget(self._zoom_inc_btn)

        self._zoom_percent_label = QLabel("0%")
        self._zoom_percent_label.setObjectName("scopeSliderInfoLabel")
        self._zoom_percent_label.setMinimumWidth(42)
        bottom_layout.addWidget(self._zoom_percent_label)

        self._autoscale_btn = QPushButton("AutoScale")
        self._autoscale_btn.clicked.connect(self._on_autoscale_clicked)
        bottom_layout.addWidget(self._autoscale_btn)
        self._measurement_menu_btn = QToolButton()
        self._measurement_menu_btn.setObjectName("scopeMeasurementMenuBtn")
        self._measurement_menu_btn.setText("+ Add Measurement")
        self._measurement_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._measurement_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._measurement_menu = QMenu(self._measurement_menu_btn)
        self._measurement_menu.aboutToShow.connect(self._populate_measurement_menu)
        self._measurement_menu_btn.setMenu(self._measurement_menu)
        bottom_layout.addWidget(self._measurement_menu_btn)
        layout.addWidget(self._scope_bottom_controls, stretch=0)
        self._scope_bottom_tab = self._scope_bottom_controls
        self._scope_bottom_tab.setVisible(False)

        self._mapping_label.setVisible(False)
        self._message_label.setVisible(False)

        self._set_stacked_cursor_enabled(False)
        self._apply_stacked_trace_colors()
        self._sync_trace_style_controls()
        self._apply_panel_visibility()

        self._refresh_title()
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @property
    def component_id(self) -> str:
        """Return the current component_id value."""
        return self._component_id

    def set_component_name(self, name: str) -> None:
        """Update component_name for this widget."""
        self._component_name = name
        self._refresh_title()

    def set_bindings(self, bindings: list[ScopeChannelBinding]) -> None:
        """Update bindings for this widget."""
        self._bindings = bindings
        if not bindings:
            self._mapping_label.setText("Channels: none")
            return

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
            self._refresh_stacked_sidebar(self._current_result)
            self._rebuild_stacked_plots(self._current_result)
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

            binding_found = False
            binding_missing: list[str] = []
            for idx, signal in enumerate(binding.signals):
                base_label = self._format_signal_label(binding, signal, idx)
                label = self._ensure_unique_label(base_label, subset.signals)
                if not signal.signal_key:
                    binding_missing.append(label)
                    continue
                resolved_series = self._resolve_signal_series(result, signal)
                if resolved_series:
                    subset.signals[label] = resolved_series
                    found_channels.append(label)
                    binding_found = True
                else:
                    binding_missing.append(label)

            if not binding_found and self._scope_type == ComponentType.ELECTRICAL_SCOPE:
                node_series = self._resolve_binding_node_voltage_series(result, binding)
                if node_series:
                    node_ref = str(binding.node_label or binding.node_id or "").strip()
                    node_label = f"V({node_ref})" if node_ref else "V(node)"
                    fallback_name = self._ensure_unique_label(
                        f"{binding.channel_label}: {node_label}",
                        subset.signals,
                    )
                    subset.signals[fallback_name] = node_series
                    found_channels.append(fallback_name)
                    binding_found = True

            if binding_found:
                if len(binding_missing) < len(binding.signals):
                    # Keep partial diagnostics when one of multiple mapped signals is absent.
                    missing_channels.extend(binding_missing)
            else:
                missing_channels.extend(binding_missing)

        # Thermal scopes can still render backend-native thermal traces even when
        # users have not wired dedicated TH pins yet.
        if self._scope_type == ComponentType.THERMAL_SCOPE and not subset.signals:
            subset.signals = self._collect_backend_thermal_fallback_signals(result)
            if subset.signals:
                found_channels = list(subset.signals.keys())
                missing_channels = []

        self._current_result = subset if subset.signals else SimulationResult(time=subset.time, signals={})
        self._refresh_stacked_sidebar(self._current_result)
        self._rebuild_stacked_plots(self._current_result)

        self._message_label.setText(self._format_status(found_channels, missing_channels))

    def _resolve_signal_series(
        self,
        result: SimulationResult,
        signal: ScopeSignal,
    ) -> list[float] | None:
        """Resolve a bound signal key against result channels with metadata fallback."""
        key = str(signal.signal_key or "").strip()
        if not key:
            return None

        series = result.signals.get(key)
        if series is not None:
            values = list(series)
            return values if values else None

        casefold_key = self._find_casefold_signal_key(result, key)
        if casefold_key is not None:
            values = list(result.signals.get(casefold_key, []))
            return values if values else None

        metadata_key = self._find_metadata_matched_signal_key(result, key)
        if metadata_key is not None:
            values = list(result.signals.get(metadata_key, []))
            return values if values else None

        fuzzy_key = self._find_fuzzy_signal_key(result, key)
        if fuzzy_key is not None:
            values = list(result.signals.get(fuzzy_key, []))
            return values if values else None

        return None

    @staticmethod
    def _find_casefold_signal_key(result: SimulationResult, expected_key: str) -> str | None:
        """Find a result signal key by case-insensitive exact match."""
        expected = str(expected_key or "").strip().casefold()
        if not expected:
            return None
        for raw_name in result.signals.keys():
            name = str(raw_name or "").strip()
            if name.casefold() == expected:
                return name
        return None

    @staticmethod
    def _canonical_signal_token(value: str | None) -> str:
        """Normalize a signal token for fuzzy matching."""
        token = str(value or "").strip().lower()
        if not token:
            return ""
        return "".join(ch for ch in token if ch.isalnum())

    @staticmethod
    def _split_signal_key(key: str) -> tuple[str, str]:
        """Split `component.qualifier` signal keys into source and qualifier."""
        text = str(key or "").strip()
        if not text:
            return "", ""
        if "." in text:
            source, qualifier = text.split(".", 1)
            return source.strip(), qualifier.strip()
        wrapped = re.match(r"^[A-Za-z][A-Za-z0-9_.:-]*\(([^)]+)\)$", text)
        if wrapped:
            return wrapped.group(1).strip(), ""
        return text, ""

    @staticmethod
    def _normalize_qualifier(value: str | None) -> str:
        """Normalize output qualifiers for resilient C-Block/control matching."""
        qualifier = "".join(ch for ch in str(value or "").strip().lower() if ch.isalnum())
        if qualifier == "out":
            return "out0"
        return qualifier

    @classmethod
    def _candidate_qualifier(cls, channel_name: str) -> str:
        """Infer qualifier from backend virtual channel naming."""
        _source, qualifier = cls._split_signal_key(channel_name)
        if qualifier:
            return qualifier
        match = re.search(r"(out\d+|duty)$", str(channel_name or "").strip(), re.IGNORECASE)
        return match.group(1) if match else ""

    @classmethod
    def _find_metadata_matched_signal_key(
        cls,
        result: SimulationResult,
        expected_key: str,
    ) -> str | None:
        """Match channels by virtual metadata when backend key naming differs."""
        stats = result.statistics if isinstance(result.statistics, dict) else {}
        metadata = stats.get("virtual_channel_metadata")
        if not isinstance(metadata, dict) or not metadata:
            return None

        expected_source, expected_qualifier = cls._split_signal_key(expected_key)
        expected_source_token = cls._canonical_signal_token(expected_source)
        expected_qualifier_token = cls._normalize_qualifier(expected_qualifier)
        if not expected_source_token:
            expected_source_token = cls._canonical_signal_token(expected_key)
        if not expected_source_token:
            return None

        scored: list[tuple[int, int, str]] = []
        for raw_name, metadata_entry in metadata.items():
            channel_name = str(raw_name or "").strip()
            if not channel_name or channel_name not in result.signals:
                continue

            source_component = cls._virtual_metadata_field(metadata_entry, "source_component")
            source_token = cls._canonical_signal_token(source_component)
            if not source_token:
                source_guess, _ = cls._split_signal_key(channel_name)
                source_token = cls._canonical_signal_token(source_guess)

            if source_token and source_token != expected_source_token:
                continue
            if not source_token:
                channel_token = cls._canonical_signal_token(channel_name)
                if not channel_token.startswith(expected_source_token):
                    continue

            score = 0
            if source_token == expected_source_token:
                score += 30
            domain = cls._virtual_metadata_field(metadata_entry, "domain").lower()
            if domain == "control":
                score += 3

            candidate_qualifier = cls._normalize_qualifier(cls._candidate_qualifier(channel_name))
            if expected_qualifier_token:
                if candidate_qualifier == expected_qualifier_token:
                    score += 20
                elif (
                    candidate_qualifier
                    and (
                        expected_qualifier_token in candidate_qualifier
                        or candidate_qualifier in expected_qualifier_token
                    )
                ):
                    score += 12
            elif candidate_qualifier in {"", "out0"}:
                score += 5

            scored.append((score, -len(channel_name), channel_name))

        if not scored:
            return None
        scored.sort(reverse=True)
        return scored[0][2]

    @classmethod
    def _find_fuzzy_signal_key(
        cls,
        result: SimulationResult,
        expected_key: str,
    ) -> str | None:
        """Fallback matcher for control channels when metadata is unavailable."""
        expected_source, expected_qualifier = cls._split_signal_key(expected_key)
        expected_source_token = cls._canonical_signal_token(expected_source)
        expected_qualifier_token = cls._normalize_qualifier(expected_qualifier)
        if not expected_source_token:
            expected_source_token = cls._canonical_signal_token(expected_key)
        if not expected_source_token:
            return None

        scored: list[tuple[int, int, str]] = []
        for raw_name in result.signals.keys():
            channel_name = str(raw_name or "").strip()
            if not channel_name:
                continue

            upper = channel_name.upper()
            # Skip canonical electrical/thermal channels when matching control.
            if upper.startswith(("V(", "I(", "VP(", "IP(", "PP(", "T(", "TJ(", "TEMP(")):
                continue

            source_guess, qualifier_guess = cls._split_signal_key(channel_name)
            source_token = cls._canonical_signal_token(source_guess)
            channel_token = cls._canonical_signal_token(channel_name)

            source_match = False
            if source_token:
                if source_token == expected_source_token:
                    source_match = True
                elif (
                    expected_source_token in source_token
                    or source_token in expected_source_token
                ):
                    source_match = True
            elif (
                expected_source_token in channel_token
                or channel_token in expected_source_token
            ):
                source_match = True

            if not source_match:
                continue

            score = 0
            if source_token == expected_source_token:
                score += 24
            else:
                score += 10

            candidate_qualifier = cls._normalize_qualifier(qualifier_guess)
            if not candidate_qualifier:
                candidate_qualifier = cls._normalize_qualifier(cls._candidate_qualifier(channel_name))

            if expected_qualifier_token:
                if candidate_qualifier == expected_qualifier_token:
                    score += 16
                elif (
                    candidate_qualifier
                    and (
                        expected_qualifier_token in candidate_qualifier
                        or candidate_qualifier in expected_qualifier_token
                    )
                ):
                    score += 8
                elif expected_qualifier_token == "out0" and candidate_qualifier in {"", "out"}:
                    score += 6
            elif candidate_qualifier in {"", "out0"}:
                score += 4

            scored.append((score, -len(channel_name), channel_name))

        if not scored:
            return None
        scored.sort(reverse=True)
        return scored[0][2]

    @classmethod
    def _resolve_binding_node_voltage_series(
        cls,
        result: SimulationResult,
        binding: ScopeChannelBinding,
    ) -> list[float] | None:
        """Resolve fallback V(node) series for scopes bound to control nets."""
        candidates = cls._node_voltage_signal_candidates(binding)
        if not candidates:
            return None

        for candidate in candidates:
            series = result.signals.get(candidate)
            if series is not None:
                values = list(series)
                if values:
                    return values
            matched = cls._find_casefold_signal_key(result, candidate)
            if matched is None:
                continue
            values = list(result.signals.get(matched, []))
            if values:
                return values
        return None

    @staticmethod
    def _node_voltage_signal_candidates(binding: ScopeChannelBinding) -> list[str]:
        """Build candidate signal keys for node-voltage fallback lookup."""
        tokens: list[str] = []
        for raw in (binding.node_label, binding.node_id):
            text = str(raw or "").strip()
            if not text:
                continue
            tokens.append(f"V({text})")
            tokens.append(text)

        out: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
        return out

    @staticmethod
    def _virtual_metadata_field(metadata_entry: object | None, field: str) -> str:
        if isinstance(metadata_entry, dict):
            raw = metadata_entry.get(field)
        else:
            raw = getattr(metadata_entry, field, None) if metadata_entry is not None else None
        return str(raw or "").strip()

    @classmethod
    def _is_thermal_signal_name(cls, signal_name: str, metadata_entry: object | None) -> bool:
        domain = cls._virtual_metadata_field(metadata_entry, "domain").lower()
        component_type = cls._virtual_metadata_field(metadata_entry, "component_type").lower()
        if domain == "thermal" or component_type == "thermal_trace":
            return True

        upper = str(signal_name or "").strip().upper()
        if not upper:
            return False
        if upper.startswith(("T(", "TJ(", "TEMP(", "THERMAL(")):
            return True
        if upper.startswith(("T_", "TJ_", "TEMP_")):
            return True
        return "TEMP" in upper

    def _collect_backend_thermal_fallback_signals(
        self,
        result: SimulationResult,
    ) -> dict[str, list[float]]:
        metadata = (
            result.statistics.get("virtual_channel_metadata")
            if isinstance(result.statistics, dict)
            else None
        )
        if not isinstance(metadata, dict):
            metadata = {}

        fallback: dict[str, list[float]] = {}
        for raw_name, series in result.signals.items():
            name = str(raw_name or "").strip()
            if not name:
                continue
            if not series:
                continue
            if not self._is_thermal_signal_name(name, metadata.get(name)):
                continue
            fallback[name] = list(series)
        return fallback

    @staticmethod
    def _infer_signal_categories(signal_names: list[str]) -> dict[str, str]:
        """Infer signal category from label naming conventions."""
        categories: dict[str, str] = {}
        electrical_prefixes = ("V_", "I_", "VP_", "IP_", "VP", "IP", "Vout", "Vin", "Iout")
        thermal_prefixes = ("T_", "Temp", "temp", "Tj", "TJ")
        for name in signal_names:
            upper = name.upper()
            if any(name.startswith(p) for p in electrical_prefixes) or upper.startswith(("V", "I")) and len(name) > 1 and name[1] in "_Oo":
                categories[name] = "ELECTRICAL"
            elif any(name.startswith(p) for p in thermal_prefixes) or "TEMP" in upper:
                categories[name] = "THERMAL"
            else:
                categories[name] = "CONTROL"
        return categories

    def apply_geometry_state(self, geometry: list[int] | None) -> None:
        """Apply previously captured geometry metadata to this window."""
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
        """Capture geometry metadata for window state persistence."""
        rect = self.geometry()
        return rect.x(), rect.y(), rect.width(), rect.height()

    def capture_ui_state(self) -> dict[str, object]:
        """Capture scope-specific UI state for workspace/session persistence."""
        self._sync_plot_groups()
        return {
            "left_panel_visible": bool(self._left_panel_visible),
            "right_panel_visible": bool(self._right_panel_visible),
            "measurement_keys": self._stacked_measurements.visible_measurement_keys(),
            "plot_groups": dict(self._stacked_plot_groups),
            "cursors_enabled": bool(self._stacked_cursors_enabled),
            "cursor_a": float(self._c1_spin.value()),
            "cursor_b": float(self._c2_spin.value()),
            "active_signal": str(self._stacked_active_signal or ""),
        }

    def apply_ui_state(self, state: dict[str, object] | None) -> None:
        """Apply a previously captured scope UI state."""
        if not isinstance(state, dict):
            return

        left_visible_raw = state.get("left_panel_visible")
        if isinstance(left_visible_raw, bool):
            self._left_panel_toggle_btn.blockSignals(True)
            self._left_panel_toggle_btn.setChecked(left_visible_raw)
            self._left_panel_toggle_btn.blockSignals(False)
            self._on_toggle_left_panel_clicked(left_visible_raw)

        right_visible_raw = state.get("right_panel_visible")
        if isinstance(right_visible_raw, bool):
            self._right_panel_toggle_btn.blockSignals(True)
            self._right_panel_toggle_btn.setChecked(right_visible_raw)
            self._right_panel_toggle_btn.blockSignals(False)
            self._on_toggle_right_panel_clicked(right_visible_raw)

        measurement_keys_raw = state.get("measurement_keys")
        if isinstance(measurement_keys_raw, list):
            self._stacked_measurements.set_visible_measurement_keys(
                [str(key) for key in measurement_keys_raw if str(key).strip()]
            )

        plot_groups_raw = state.get("plot_groups")
        if isinstance(plot_groups_raw, dict):
            self._stacked_plot_groups = {
                str(signal_name): str(leader_name)
                for signal_name, leader_name in plot_groups_raw.items()
                if str(signal_name).strip() and str(leader_name).strip()
            }
        else:
            self._stacked_plot_groups = {}

        active_signal_raw = state.get("active_signal")
        if isinstance(active_signal_raw, str) and active_signal_raw.strip():
            self._stacked_active_signal = active_signal_raw.strip()

        cursors_enabled_raw = state.get("cursors_enabled")
        if isinstance(cursors_enabled_raw, bool):
            self._stacked_cursor_toggle.setChecked(cursors_enabled_raw)

        cursor_a_raw = state.get("cursor_a")
        if isinstance(cursor_a_raw, (int, float)):
            self._c1_spin.setValue(float(cursor_a_raw))
        cursor_b_raw = state.get("cursor_b")
        if isinstance(cursor_b_raw, (int, float)):
            self._c2_spin.setValue(float(cursor_b_raw))

        if self._stacked_signals:
            self._sync_plot_groups()
            if self._stacked_active_signal not in self._stacked_signals:
                self._stacked_active_signal = next(iter(self._stacked_signals))
            self._sync_scope_selector()
            self._sync_trace_style_controls()
            self._rebuild_stacked_plots(self._current_result)
            self._update_stacked_measurements()

    # ------------------------------------------------------------------
    # QWidget overrides
    # ------------------------------------------------------------------
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: D401 - Qt override
        """Handle the Qt closeEvent callback."""
        self.closed.emit(self._component_id, self.capture_geometry_state())
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _refresh_title(self) -> None:
        label = "Scope" if self._scope_type == ComponentType.ELECTRICAL_SCOPE else "Thermal Scope"
        title = self._component_name or label
        self.setWindowTitle(title)
        if hasattr(self, "_scope_title_label"):
            self._scope_title_label.setText(self._component_name or "Unnamed")
        if hasattr(self, "_scope_type_badge"):
            self._scope_type_badge.setText(label)
        if hasattr(self, "_toolbar_scope_label"):
            active = str(self._stacked_active_signal or "").strip()
            self._toolbar_scope_label.setText(active or (self._component_name or label))

    @staticmethod
    def _scope_shell_palette() -> dict[str, str]:
        """Return scope-local shell colors (light chrome)."""
        return {
            "window_bg": "#eef2f7",
            "surface_bg": "#f4f7fb",
            "panel_bg": "#f8fafc",
            "panel_alt": "#eef3f9",
            "header_bg": "#e7edf6",
            "border": "#cbd5e1",
            "border_soft": "#d8e1ec",
            "text": "#1f2937",
            "muted": "#5b6472",
            "accent": "#2563eb",
            "accent_hover": "#1d4ed8",
            "accent_fg": "#ffffff",
        }

    @staticmethod
    def _scope_plot_palette() -> dict[str, str]:
        """Return dark plot colors for contrast against light shell."""
        return {
            "plot_bg": "#0b111c",
            "plot_axis": "#8ca0ba",
            "plot_text": "#a9bbd2",
            "grid_alpha": "0.23",
        }

    def _apply_toolbar_icons(self) -> None:
        base_color = "#d7deea"
        accent_color = "#8ed86b"
        cursor_color = accent_color if self._stacked_cursors_enabled else base_color
        grid_color = "#6cc7ff" if self._stacked_grid_enabled else base_color
        self._toolbar_left_btn.setIcon(IconService.get_icon("menu", base_color, 14))
        self._toolbar_right_btn.setIcon(IconService.get_icon("layers", base_color, 14))
        self._toolbar_cursor_btn.setIcon(IconService.get_icon("crosshairs", cursor_color, 14))
        self._toolbar_grid_btn.setIcon(IconService.get_icon("grid", grid_color, 14))
        self._toolbar_autoscale_btn.setIcon(IconService.get_icon("maximize", base_color, 14))
        self._toolbar_math_btn.setIcon(IconService.get_icon("plus", base_color, 14))
        self._trace_style_menu_btn.setIcon(IconService.get_icon("sliders", base_color, 14))
        self._toolbar_copy_btn.setIcon(IconService.get_icon("external-link", base_color, 14))
        self._measurement_menu_btn.setIcon(IconService.get_icon("plus", "#dbe4f5", 13))
        for btn in (
            self._toolbar_left_btn,
            self._toolbar_right_btn,
            self._toolbar_cursor_btn,
            self._toolbar_grid_btn,
            self._toolbar_autoscale_btn,
            self._toolbar_math_btn,
            self._trace_style_menu_btn,
            self._toolbar_copy_btn,
            self._measurement_menu_btn,
        ):
            btn.setIconSize(QSize(13, 13))

    def _sync_toolbar_toggles(self) -> None:
        for btn, checked in (
            (self._toolbar_left_btn, self._left_panel_visible),
            (self._toolbar_right_btn, self._right_panel_visible),
            (self._toolbar_cursor_btn, self._stacked_cursors_enabled),
            (self._toolbar_grid_btn, self._stacked_grid_enabled),
        ):
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)
        self._apply_toolbar_icons()

    def _on_toolbar_left_toggled(self, checked: bool) -> None:
        self._left_panel_toggle_btn.blockSignals(True)
        self._left_panel_toggle_btn.setChecked(bool(checked))
        self._left_panel_toggle_btn.blockSignals(False)
        self._on_toggle_left_panel_clicked(bool(checked))

    def _on_toolbar_right_toggled(self, checked: bool) -> None:
        self._right_panel_toggle_btn.blockSignals(True)
        self._right_panel_toggle_btn.setChecked(bool(checked))
        self._right_panel_toggle_btn.blockSignals(False)
        self._on_toggle_right_panel_clicked(bool(checked))

    def _on_toolbar_cursor_toggled(self, checked: bool) -> None:
        self._stacked_cursor_toggle.blockSignals(True)
        self._stacked_cursor_toggle.setChecked(bool(checked))
        self._stacked_cursor_toggle.blockSignals(False)
        self._on_stacked_cursor_toggled(bool(checked))

    def _on_toolbar_grid_toggled(self, checked: bool) -> None:
        self._stacked_grid_toggle.blockSignals(True)
        self._stacked_grid_toggle.setChecked(bool(checked))
        self._stacked_grid_toggle.blockSignals(False)
        self._on_stacked_grid_toggled(bool(checked))

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to scope chrome and stacked display."""
        self._theme = theme
        shell = self._scope_shell_palette()
        self._viewer.apply_theme(theme)
        self._apply_stacked_trace_colors()
        self._stacked_signal_list.apply_theme(theme)
        self._stacked_measurements.apply_theme(theme, cursor_palette=self._cursor_palette())
        self._apply_toolbar_icons()
        self._sync_toolbar_toggles()
        self.setStyleSheet(f"""
            ScopeWindow {{
                background-color: {shell["window_bg"]};
            }}
            QWidget#scopeTopChrome {{
                background-color: #2d3241;
                border: 1px solid #3a4254;
                border-radius: 10px;
            }}
            QWidget#scopeTopMenuRow {{
                background-color: #2f3546;
                border-bottom: 1px solid #3f495f;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                min-height: 30px;
            }}
            QLabel#scopeBrandLabel {{
                color: #ecf2ff;
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.2px;
                padding-left: 2px;
            }}
            QToolButton#scopeMenuTextBtn {{
                color: #d6deed;
                background: transparent;
                border: none;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 500;
            }}
            QToolButton#scopeMenuTextBtn:hover {{
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 4px;
            }}
            QLabel#scopeVersionLabel {{
                color: #aab6cc;
                font-size: 10px;
                font-weight: 500;
            }}
            QWidget#scopeToolbarRow {{
                background-color: #333a4c;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                min-height: 32px;
            }}
            QLabel#scopeToolbarScopeLabel {{
                color: #c6d0e2;
                font-size: 10px;
                font-weight: 600;
                padding-right: 2px;
            }}
            QFrame#scopeToolbarSeparator {{
                background-color: #4b556d;
                min-width: 1px;
                max-width: 1px;
                border: none;
                margin: 2px 5px;
            }}
            QToolButton#scopeToolbarBtn {{
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 5px;
                padding: 0px;
            }}
            QToolButton#scopeToolbarBtn:hover {{
                background-color: rgba(255, 255, 255, 0.10);
                border-color: rgba(206, 220, 242, 0.20);
            }}
            QToolButton#scopeToolbarBtn:checked {{
                background-color: rgba(93, 146, 224, 0.30);
                border-color: rgba(131, 177, 241, 0.65);
            }}
            QToolButton#scopeToolbarBtn::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QWidget#scopePlotSurface {{
                background: {shell["surface_bg"]};
                border: 1px solid {shell["border"]};
                border-radius: 12px;
            }}
            QWidget#scopeLeftPanel,
            QWidget#scopeRightPanel,
            QWidget#scopeStackedScrollContent,
            QScrollArea#scopeStackedScroll,
            QScrollArea#scopeStackedScroll > QWidget,
            QScrollArea#scopeStackedScroll > QWidget > QWidget {{
                background-color: {shell["panel_bg"]};
            }}
            QWidget#scopeBottomControlBar {{
                background-color: {shell["surface_bg"]};
                border: 1px solid {shell["border"]};
                border-radius: 12px;
            }}
            QWidget#scopeBottomControlBar QLabel {{
                color: {shell["muted"]};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#scopeSliderInfoLabel {{
                color: {shell["text"]};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#scopeSliderStepBtn {{
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                padding: 0px;
                border-radius: 8px;
                background-color: {shell["panel_bg"]};
                border: 1px solid {shell["border"]};
            }}
            QPushButton#scopeSliderStepBtn:hover {{
                border-color: {shell["accent"]};
            }}
            QSlider#scopeTimelineSlider::groove:horizontal,
            QSlider#scopeZoomSlider::groove:horizontal {{
                border: none;
                height: 6px;
                background: {shell["border_soft"]};
                border-radius: 3px;
            }}
            QSlider#scopeTimelineSlider::handle:horizontal,
            QSlider#scopeZoomSlider::handle:horizontal {{
                background: {shell["accent"]};
                border: 1px solid {shell["accent"]};
                width: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
            QLabel#scopeMappingLabel {{
                color: {shell["muted"]};
                font-size: 11px;
                font-weight: 500;
            }}
            QLabel#scopeMessageLabel {{
                color: {shell["accent"]};
                font-weight: 600;
                font-size: 12px;
            }}
            QComboBox, QDoubleSpinBox {{
                background-color: {shell["panel_bg"]};
                color: {shell["text"]};
                border: 1px solid {shell["border"]};
                border-radius: 8px;
                padding: 3px 8px;
                min-height: 24px;
            }}
            QComboBox:hover, QDoubleSpinBox:hover {{
                border-color: {shell["accent"]};
            }}
            QPushButton {{
                background-color: {shell["panel_bg"]};
                color: {shell["text"]};
                border: 1px solid {shell["border"]};
                border-radius: 8px;
                padding: 4px 10px;
                min-height: 24px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {shell["panel_alt"]};
                border-color: {shell["accent"]};
            }}
            QPushButton#scopeMathSignalBtn {{
                background-color: {shell["accent"]};
                color: {shell["accent_fg"]};
                border-color: {shell["accent"]};
            }}
            QPushButton#scopeMathSignalBtn:hover {{
                background-color: {shell["accent_hover"]};
            }}
            QToolButton#scopeMeasurementMenuBtn {{
                background-color: {shell["panel_bg"]};
                color: {shell["text"]};
                border: 1px solid {shell["border"]};
                border-radius: 8px;
                padding: 3px 9px;
                min-height: 24px;
                font-weight: 600;
            }}
            QToolButton#scopeMeasurementMenuBtn:hover {{
                background-color: {shell["panel_alt"]};
                border-color: {shell["accent"]};
            }}
            QToolButton#scopeMeasurementMenuBtn::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QToolButton#scopePlotCopyBtn {{
                background-color: rgba(12, 18, 30, 170);
                color: #d8e4f7;
                border: 1px solid #28364d;
                border-radius: 7px;
                padding: 1px 7px;
                min-height: 22px;
                font-size: 10px;
                font-weight: 600;
            }}
            QToolButton#scopePlotCopyBtn:hover {{
                background-color: {shell["accent"]};
                color: {shell["accent_fg"]};
                border-color: {shell["accent"]};
            }}
            QMenu {{
                background-color: {shell["panel_bg"]};
                color: {shell["text"]};
                border: 1px solid {shell["border"]};
                border-radius: 8px;
                padding: 6px;
            }}
            QMenu::item {{
                padding: 6px 12px;
                border-radius: 6px;
            }}
            QMenu::item:selected {{
                background-color: {shell["panel_alt"]};
                color: {shell["text"]};
            }}
            QCheckBox {{
                color: {shell["text"]};
                spacing: 6px;
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 14px;
                height: 14px;
                border-radius: 4px;
                border: 1px solid {shell["border"]};
                background-color: {shell["panel_bg"]};
            }}
            QCheckBox::indicator:checked {{
                border-color: {shell["accent"]};
                background-color: {shell["accent"]};
            }}
            QWidget#scopeRightControlBar QCheckBox {{
                spacing: 4px;
                padding: 0;
            }}
            QWidget#scopeRightControlBar {{
                background-color: {shell["panel_alt"]};
                border: 1px solid {shell["border_soft"]};
                border-radius: 10px;
            }}
            QWidget#scopeRightControlBar QLabel {{
                color: {shell["muted"]};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#scopePanelToggleBtn {{
                min-width: 28px;
                max-width: 28px;
                font-size: 12px;
                padding: 2px 2px;
            }}
            QPushButton#scopeMathSignalBtn {{
                min-width: 112px;
                font-size: 11px;
            }}
            QComboBox {{
                background-color: {shell["panel_bg"]};
                color: {shell["text"]};
                border: 1px solid {shell["border"]};
                border-radius: 7px;
                padding: 3px 8px;
                min-height: 24px;
                font-size: 11px;
            }}
        """)
        self._timeline_slider.set_theme_colors(
            track_bg=QColor(shell["panel_alt"]),
            track_border=QColor(shell["border"]),
            selected_fill=QColor(shell["accent"]),
            handle_fill=QColor(shell["panel_bg"]),
            handle_border=QColor(shell["accent"]),
        )
        self._sync_trace_style_controls()
        self._refresh_title()
        self._rebuild_stacked_plots(self._current_result)

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
        self._stacked_hover_items.clear()
        self._stacked_plot_interaction_refs.clear()

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
        all_colors = {
            name: color
            for name in self._stacked_signals
            if (color := self._stacked_signal_list.get_signal_color(name)) is not None
        }
        self._stacked_measurements.set_signal_colors(all_colors)

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
        self._trace_style_menu_btn.setEnabled(controls_enabled)
        self._set_trace_controls_for_signal(selected or None)

    def _plot_group_leader(self, signal_name: str) -> str:
        """Resolve the canonical plot-group leader for a signal."""
        if signal_name not in self._stacked_signals:
            return signal_name
        leader = self._stacked_plot_groups.get(signal_name, signal_name)
        visited = {signal_name}
        while leader in self._stacked_plot_groups:
            next_leader = self._stacked_plot_groups.get(leader, leader)
            if next_leader == leader or next_leader in visited:
                break
            visited.add(leader)
            leader = next_leader
        if leader not in self._stacked_signals:
            return signal_name
        return leader

    def _sync_plot_groups(self) -> None:
        """Prune/normalize plot-group assignments to current signals."""
        if not self._stacked_signals:
            self._stacked_plot_groups = {}
            return

        current = set(self._stacked_signals.keys())
        if not self._stacked_plot_groups:
            leader = next(iter(self._stacked_signals))
            self._stacked_plot_groups = dict.fromkeys(self._stacked_signals, leader)

        normalized: dict[str, str] = {}
        for signal_name in self._stacked_signals:
            leader = self._stacked_plot_groups.get(signal_name, signal_name)
            if leader not in current:
                leader = signal_name
            normalized[signal_name] = leader

        self._stacked_plot_groups = normalized
        for signal_name in list(self._stacked_plot_groups.keys()):
            self._stacked_plot_groups[signal_name] = self._plot_group_leader(signal_name)

    def _set_signal_plot_group(self, signal_name: str, leader_signal: str) -> None:
        """Assign a signal to a dedicated/shared plot group."""
        if signal_name not in self._stacked_signals:
            return
        if leader_signal not in self._stacked_signals:
            leader_signal = signal_name
        self._sync_plot_groups()
        if leader_signal != signal_name:
            leader_signal = self._plot_group_leader(leader_signal)
        self._stacked_plot_groups[signal_name] = leader_signal
        self._sync_plot_groups()
        self._rebuild_stacked_plots(self._current_result)

    def _split_all_plot_groups(self) -> None:
        if not self._stacked_signals:
            return
        self._stacked_plot_groups = {
            signal_name: signal_name for signal_name in self._stacked_signals
        }
        self._rebuild_stacked_plots(self._current_result)

    def _apply_dragged_signal_mapping(
        self,
        signal_name: str,
        *,
        target_group_leader: str | None,
    ) -> bool:
        """Apply drag/drop mapping of one signal into a target group or dedicated pane."""
        if signal_name not in self._stacked_signals:
            return False

        # Dragging a hidden trace into a plot always makes it visible first.
        if signal_name not in self._stacked_signal_list.get_visible_signals():
            self._stacked_signal_list.set_signal_visible(signal_name, True)

        if target_group_leader is None or target_group_leader not in self._stacked_signals:
            self._set_signal_plot_group(signal_name, signal_name)
            return True

        self._set_signal_plot_group(signal_name, target_group_leader)
        return True

    def _populate_trace_style_menu(self) -> None:
        """Build the trace-style menu with per-signal actions."""
        self._trace_style_menu.clear()
        signal_names = self._trace_signal_names()
        if not signal_names:
            action = self._trace_style_menu.addAction("No signals available")
            action.setEnabled(False)
            return

        self._sync_plot_groups()
        selected_signal = self._selected_trace_signal() or self._stacked_active_signal or signal_names[0]
        leader_order: list[str] = []
        for signal_name in signal_names:
            leader = self._plot_group_leader(signal_name)
            if leader not in leader_order:
                leader_order.append(leader)

        for signal_name in signal_names:
            signal_menu = self._trace_style_menu.addMenu(signal_name)
            if signal_name == selected_signal:
                signal_menu.setTitle(f"{signal_name}  (active)")

            color_action = signal_menu.addAction("Color...")
            color_action.triggered.connect(
                lambda _checked=False, name=signal_name: self._pick_trace_color_for_signal(name)
            )

            width_menu = signal_menu.addMenu("Thickness")
            current_width = self._trace_style_width(signal_name)
            for width in (0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0):
                width_action = width_menu.addAction(f"{width:g}px")
                width_action.setCheckable(True)
                width_action.setChecked(abs(current_width - width) < 1e-9)
                width_action.triggered.connect(
                    lambda _checked=False, name=signal_name, value=width: self._set_trace_width_for_signal(name, value)
                )

            reset_action = signal_menu.addAction("Reset style")
            reset_action.triggered.connect(
                lambda _checked=False, name=signal_name: self._reset_trace_style_for_signal(name)
            )

            signal_menu.addSeparator()
            plot_menu = signal_menu.addMenu("Plot placement")
            dedicated_action = plot_menu.addAction("Dedicated plot")
            dedicated_action.setCheckable(True)
            dedicated_action.setChecked(self._plot_group_leader(signal_name) == signal_name)
            dedicated_action.triggered.connect(
                lambda _checked=False, name=signal_name: self._set_signal_plot_group(name, name)
            )
            if selected_signal and selected_signal != signal_name:
                quick_overlay = plot_menu.addAction(f"Overlay with active ({selected_signal})")
                quick_overlay.triggered.connect(
                    lambda _checked=False, name=signal_name, leader=selected_signal: self._set_signal_plot_group(name, leader)
                )
            overlay_menu = plot_menu.addMenu("Overlay with...")
            for leader in leader_order:
                if leader == signal_name:
                    continue
                overlay_action = overlay_menu.addAction(leader)
                overlay_action.setCheckable(True)
                overlay_action.setChecked(self._plot_group_leader(signal_name) == leader)
                overlay_action.triggered.connect(
                    lambda _checked=False, name=signal_name, group_leader=leader: self._set_signal_plot_group(name, group_leader)
                )

        self._trace_style_menu.addSeparator()
        reset_all = self._trace_style_menu.addAction("Reset all trace styles")
        reset_all.triggered.connect(self._reset_all_trace_styles)
        split_plots = self._trace_style_menu.addAction("Split all into dedicated plots")
        split_plots.triggered.connect(self._split_all_plot_groups)

    def _populate_measurement_menu(self) -> None:
        """Build the contextual bottom-panel measurement-column selector menu."""
        self._measurement_menu.clear()
        available_keys = self._stacked_measurements.available_measurement_keys()
        if not available_keys:
            action = self._measurement_menu.addAction("No measurement columns available")
            action.setEnabled(False)
            return

        label_by_key = {
            "c1": "Cursor A",
            "c2": "Cursor B",
            "dv": "dV",
            "min": "Min",
            "max": "Max",
            "mean": "Mean",
            "rms": "RMS",
            "pkpk": "Pk-Pk",
        }
        visible = set(self._stacked_measurements.visible_measurement_keys())

        for key in available_keys:
            action = self._measurement_menu.addAction(label_by_key.get(key, key.upper()))
            action.setCheckable(True)
            action.setChecked(key in visible)
            action.toggled.connect(
                lambda checked, measurement_key=key: self._on_measurement_key_toggled(
                    measurement_key,
                    checked,
                )
            )

        self._measurement_menu.addSeparator()
        show_all = self._measurement_menu.addAction("Show all")
        show_all.triggered.connect(
            lambda: self._stacked_measurements.set_visible_measurement_keys(available_keys)
        )

    def _set_trace_width_for_signal(self, signal_name: str, width: float) -> None:
        if signal_name not in self._trace_signal_names():
            return
        style = self._trace_styles.setdefault(signal_name, {})
        style["width"] = max(0.5, float(width))
        self._prune_trace_style(signal_name)
        self._apply_trace_styles_to_viewer()
        self._set_trace_controls_for_signal(signal_name)
        self._rebuild_stacked_plots(self._current_result)

    def _pick_trace_color_for_signal(self, signal_name: str) -> None:
        if signal_name not in self._trace_signal_names():
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
        self._rebuild_stacked_plots(self._current_result)

    def _reset_trace_style_for_signal(self, signal_name: str) -> None:
        if signal_name not in self._trace_signal_names():
            return
        self._trace_styles.pop(signal_name, None)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        self._rebuild_stacked_plots(self._current_result)

    def _reset_all_trace_styles(self) -> None:
        if not self._trace_styles:
            return
        self._trace_styles.clear()
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._sync_trace_style_controls()
        self._rebuild_stacked_plots(self._current_result)

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
        self._set_trace_width_for_signal(signal_name, value)

    def _on_trace_color_clicked(self) -> None:
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return
        self._pick_trace_color_for_signal(signal_name)

    def _on_trace_style_reset(self) -> None:
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return
        self._reset_trace_style_for_signal(signal_name)

    def _on_toggle_left_panel_clicked(self, checked: bool) -> None:
        if not checked:
            sizes = self._stacked_splitter.sizes()
            if len(sizes) == 3 and sizes[0] > 0:
                self._left_panel_width = sizes[0]
        self._left_panel_visible = bool(checked)
        self._apply_panel_visibility()

    def _on_toggle_sidebar_shortcut(self) -> None:
        """Toggle left panel with keyboard shortcut."""
        target_state = not bool(self._left_panel_visible)
        self._left_panel_toggle_btn.blockSignals(True)
        self._left_panel_toggle_btn.setChecked(target_state)
        self._left_panel_toggle_btn.blockSignals(False)
        self._on_toggle_left_panel_clicked(target_state)

    def _on_toggle_right_panel_clicked(self, checked: bool) -> None:
        if not checked:
            sizes = self._stacked_splitter.sizes()
            if len(sizes) == 3 and sizes[2] > 0:
                self._right_panel_width = sizes[2]
        self._right_panel_visible = bool(checked)
        self._apply_panel_visibility()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self._stacked_splitter.sizes()
        if len(sizes) != 3:
            return
        if self._left_panel_visible and sizes[0] > 0:
            self._left_panel_width = sizes[0]
        if self._right_panel_visible and sizes[2] > 0:
            self._right_panel_width = sizes[2]

    def _apply_panel_visibility(self) -> None:
        if self._left_panel_visible:
            self._left_scope_label.setVisible(False)
            self._scope_selector_combo.setVisible(True)
            self._left_sidebar_top_row.setVisible(True)
            self._left_sidebar_actions_row.setVisible(True)
            self._create_math_signal_btn.setVisible(True)
            self._stacked_signal_list.setVisible(True)
            self._stacked_sidebar.setMinimumWidth(270)
            self._stacked_sidebar.setMaximumWidth(380)
            self._left_panel_toggle_btn.setText("◀")
            self._left_panel_toggle_btn.setToolTip("Collapse left panel")
            left = self._left_panel_width
        else:
            self._left_scope_label.setVisible(False)
            self._scope_selector_combo.setVisible(False)
            self._left_sidebar_top_row.setVisible(True)
            self._left_sidebar_actions_row.setVisible(True)
            self._create_math_signal_btn.setVisible(False)
            self._stacked_signal_list.setVisible(False)
            self._stacked_sidebar.setMinimumWidth(self._collapsed_panel_width)
            self._stacked_sidebar.setMaximumWidth(self._collapsed_panel_width)
            self._left_panel_toggle_btn.setText("▶")
            self._left_panel_toggle_btn.setToolTip("Expand left panel")
            left = self._collapsed_panel_width

        if self._right_panel_visible:
            self._right_header_label.setVisible(True)
            self._stacked_right_controls.setVisible(True)
            self._stacked_measurements.setVisible(True)
            self._stacked_right_panel.setMinimumWidth(280)
            self._stacked_right_panel.setMaximumWidth(420)
            self._right_panel_toggle_btn.setText("▶")
            self._right_panel_toggle_btn.setToolTip("Collapse right panel")
            right = self._right_panel_width
        else:
            self._right_header_label.setVisible(False)
            self._stacked_right_controls.setVisible(False)
            self._stacked_measurements.setVisible(False)
            self._stacked_right_panel.setMinimumWidth(self._collapsed_panel_width)
            self._stacked_right_panel.setMaximumWidth(self._collapsed_panel_width)
            self._right_panel_toggle_btn.setText("◀")
            self._right_panel_toggle_btn.setToolTip("Expand right panel")
            right = self._collapsed_panel_width

        total = max(self.width(), 1200)
        center = max(500, total - left - right - 40)
        self._stacked_splitter.setSizes([left, center, right])
        self._sync_toolbar_toggles()

    def _on_measurement_key_toggled(self, measurement_key: str, checked: bool) -> None:
        """Toggle a measurement column in the bottom panel table."""
        available = self._stacked_measurements.available_measurement_keys()
        if measurement_key not in available:
            return

        current = self._stacked_measurements.visible_measurement_keys()
        if checked:
            if measurement_key not in current:
                current.append(measurement_key)
        else:
            if measurement_key in current:
                if len(current) <= 1:
                    return
                current = [key for key in current if key != measurement_key]

        normalized = [key for key in available if key in set(current)]
        if not normalized:
            normalized = self._stacked_measurements.visible_measurement_keys()
        self._stacked_measurements.set_visible_measurement_keys(normalized)

    def _on_scope_selector_changed(self, signal_name: str) -> None:
        if not signal_name or signal_name not in self._stacked_signals:
            return
        self._stacked_active_signal = signal_name
        if hasattr(self, "_toolbar_scope_label"):
            self._toolbar_scope_label.setText(signal_name)
        self._selected_plot_group_leader = self._plot_group_leader(signal_name)
        self._stacked_signal_list.set_signal_visible(signal_name, True)
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_create_math_signal_clicked(self) -> None:
        available_signals = list(self._stacked_signals.keys())
        if not available_signals:
            QMessageBox.information(self, "Math Signal", "No signals available to derive math traces.")
            return

        preferred_signal = self._scope_selector_combo.currentText().strip()
        if preferred_signal not in self._stacked_signals:
            preferred_signal = available_signals[0]

        dialog = MathSignalDialog(
            self,
            signal_names=available_signals,
            default_signal=preferred_signal,
            theme=self._theme,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        config = dialog.selected_config()
        op_code = str(config["operation"])
        source_a = str(config["source_a"])
        source_b = str(config["source_b"])
        gain = float(config["gain"])
        offset = float(config["offset"])
        window = int(config["window"])
        needs_b = bool(config["needs_b"])
        needs_window = bool(config["needs_window"])
        custom_name = str(config["custom_name"])

        if source_a not in self._stacked_signals:
            QMessageBox.information(self, "Math Signal", "Invalid Source A signal.")
            return

        a_values = self._stacked_signals[source_a]
        if len(a_values) == 0:
            return

        if needs_b:
            if source_b not in self._stacked_signals:
                QMessageBox.information(self, "Math Signal", "Invalid Source B signal.")
                return
            b_values = self._stacked_signals[source_b]
            if len(b_values) != len(a_values):
                QMessageBox.information(
                    self,
                    "Math Signal",
                    "Source signals must have the same sample count.",
                )
                return
        else:
            b_values = None

        if op_code == "ADD":
            result = a_values + b_values
        elif op_code == "SUB":
            result = a_values - b_values
        elif op_code == "MUL":
            result = a_values * b_values
        elif op_code == "DIV":
            safe = np.abs(b_values) > 1e-15
            result = np.divide(a_values, b_values, out=np.zeros_like(a_values), where=safe)
        elif op_code == "AVG":
            if len(a_values) < 2:
                QMessageBox.information(self, "Math Signal", "Not enough samples for moving average.")
                return
            kernel_size = max(2, min(window, len(a_values)))
            kernel = np.ones(kernel_size, dtype=float) / float(kernel_size)
            result = np.convolve(a_values, kernel, mode="same")
        elif op_code == "NEG":
            result = -a_values
        elif op_code == "ABS":
            result = np.abs(a_values)
        elif op_code == "SQR":
            result = np.square(a_values)
        elif op_code == "DER":
            if len(self._stacked_time) < 2:
                QMessageBox.information(self, "Math Signal", "Not enough samples for derivative.")
                return
            result = np.gradient(a_values, self._stacked_time)
        elif op_code == "INT":
            if len(self._stacked_time) < 2:
                QMessageBox.information(self, "Math Signal", "Not enough samples for integral.")
                return
            dt = np.diff(self._stacked_time, prepend=self._stacked_time[0])
            result = np.cumsum(a_values * dt)
        else:
            QMessageBox.information(self, "Math Signal", "Unsupported operation.")
            return

        result = (result * gain) + offset

        self._math_signal_counter += 1
        if custom_name:
            name = f"MATH_{self._math_signal_counter}:{custom_name}"
        elif needs_b:
            name = f"MATH_{self._math_signal_counter}:{op_code}({source_a},{source_b})"
        elif needs_window:
            name = f"MATH_{self._math_signal_counter}:{op_code}({source_a},N={window})"
        else:
            name = f"MATH_{self._math_signal_counter}:{op_code}({source_a})"
        self._stacked_signals[name] = np.asarray(result, dtype=float)
        self._rebuild_stacked_statistics_cache()

        if self._current_result is None:
            self._current_result = SimulationResult()
            self._current_result.time = list(self._stacked_time)
            self._current_result.signals = {}
        self._current_result.signals[name] = list(self._stacked_signals[name])

        visible = set(self._stacked_signal_list.get_visible_signals())
        visible.add(name)
        self._stacked_signal_list.set_signals(list(self._stacked_signals.keys()))
        self._apply_stacked_trace_colors()
        for signal in self._stacked_signals:
            self._stacked_signal_list.set_signal_visible(signal, signal in visible)

        self._stacked_active_signal = name
        self._sync_scope_selector()
        self._sync_trace_style_controls()
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _zoom_window_fraction(self) -> float:
        if not hasattr(self, "_zoom_slider"):
            return 1.0
        value = self._zoom_slider.value() / 100.0
        return max(0.05, 1.0 - (0.95 * value))

    @staticmethod
    def _wheel_zoom_mask(modifiers) -> tuple[bool, bool]:
        """Return (zoom_x, zoom_y) mask from keyboard modifiers."""
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            return True, True
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            return True, False
        return False, True

    @staticmethod
    def _format_time_display(value: float) -> str:
        abs_value = abs(value)
        if abs_value >= 1.0:
            return f"{value:.3f}s"
        if abs_value >= 1e-3:
            return f"{value * 1e3:.3f}ms"
        if abs_value >= 1e-6:
            return f"{value * 1e6:.3f}µs"
        return f"{value:.3e}s"

    def _step_slider(self, slider: QSlider, delta: int) -> None:
        if not slider.isEnabled():
            return
        slider.setValue(max(slider.minimum(), min(slider.maximum(), slider.value() + delta)))

    def _on_timeline_slider_changed(self, _low: int, _high: int) -> None:
        if self._syncing_bottom_sliders:
            return
        self._apply_bottom_viewport_controls()

    def _on_zoom_slider_changed(self, _value: int) -> None:
        if self._syncing_bottom_sliders:
            return
        if len(self._stacked_time) < 2:
            return

        center = (self._timeline_slider.lowValue() + self._timeline_slider.highValue()) / 2.0
        fraction = self._zoom_window_fraction()
        width = max(1, int(round(1000 * fraction)))
        low = int(round(center - (width / 2.0)))
        high = low + width
        if low < 0:
            high -= low
            low = 0
        if high > 1000:
            low -= high - 1000
            high = 1000
        low = max(0, low)
        high = min(1000, max(low + 1, high))

        self._syncing_bottom_sliders = True
        try:
            self._timeline_slider.setValues(low, high)
        finally:
            self._syncing_bottom_sliders = False
        self._apply_bottom_viewport_controls()

    def _sync_bottom_controls_from_view_range(self) -> None:
        """Update timeline/zoom sliders from current plot x-range after mouse zoom."""
        if not self._plot_widgets or len(self._stacked_time) < 2:
            return
        x_range = self._plot_widgets[0].getPlotItem().getViewBox().viewRange()[0]
        start = float(x_range[0])
        end = float(x_range[1])
        if end < start:
            start, end = end, start

        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        span = max(t_max - t_min, 1e-15)
        start = min(max(start, t_min), t_max)
        end = min(max(end, t_min), t_max)
        if end <= start:
            end = min(t_max, start + (span / 1000.0))

        low = int(round(((start - t_min) / span) * 1000.0))
        high = int(round(((end - t_min) / span) * 1000.0))
        low = min(999, max(0, low))
        high = min(1000, max(low + 1, high))

        window_fraction = max(0.05, min(1.0, (end - start) / span))
        zoom_percent = int(round(((1.0 - window_fraction) / 0.95) * 100.0))
        zoom_percent = min(100, max(0, zoom_percent))

        self._syncing_bottom_sliders = True
        try:
            self._timeline_slider.setValues(low, high)
            self._zoom_slider.setValue(zoom_percent)
        finally:
            self._syncing_bottom_sliders = False
        self._apply_bottom_viewport_controls()

    def _on_group_plot_selected(self, group_leader: str, *, rebuild: bool = True) -> None:
        """Set the active context to the clicked plot group."""
        self._selected_plot_group_leader = group_leader
        group_signals = [
            signal_name
            for signal_name in self._stacked_signals
            if self._plot_group_leader(signal_name) == group_leader
        ]
        if not group_signals:
            return
        if self._stacked_active_signal in group_signals:
            return
        self._stacked_active_signal = group_signals[0]
        self._sync_scope_selector()
        self._sync_trace_style_controls()
        if rebuild:
            self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_group_plot_wheel(self, view_box: pg.ViewBox, ev, group_leader: str) -> bool:
        """Handle wheel zoom with axis selection on the hovered/selected plot."""
        delta = int(ev.delta()) if hasattr(ev, "delta") else 0
        if delta == 0:
            ev.ignore()
            return True

        self._selected_plot_group_leader = group_leader
        self._on_group_plot_selected(group_leader, rebuild=False)
        modifiers = ev.modifiers() if hasattr(ev, "modifiers") else Qt.KeyboardModifier.NoModifier
        zoom_x, zoom_y = self._wheel_zoom_mask(modifiers)
        mask = [zoom_x, zoom_y]
        if not any(mask):
            ev.ignore()
            return True

        scale = 1.02 ** (delta * view_box.state["wheelScaleFactor"])
        factors = [scale if zoom_x else None, scale if zoom_y else None]
        center = view_box.mapToView(ev.pos())
        view_box._resetTarget()
        view_box.scaleBy(factors, center)
        ev.accept()
        view_box.sigRangeChangedManually.emit(mask)

        if zoom_x:
            self._sync_bottom_controls_from_view_range()
        return True

    def _on_autoscale_clicked(self) -> None:
        self._syncing_bottom_sliders = True
        try:
            self._timeline_slider.setValues(0, 1000)
            self._zoom_slider.setValue(0)
        finally:
            self._syncing_bottom_sliders = False
        self._auto_range_stacked()
        self._apply_bottom_viewport_controls()

    def _step_timeline_window(self, delta: int) -> None:
        if not self._timeline_slider.isEnabled():
            return
        low = self._timeline_slider.lowValue()
        high = self._timeline_slider.highValue()
        width = max(1, high - low)

        new_low = low + delta
        new_high = high + delta
        if new_low < 0:
            new_low = 0
            new_high = width
        if new_high > 1000:
            new_high = 1000
            new_low = 1000 - width

        self._timeline_slider.setValues(new_low, new_high)

    def _apply_bottom_viewport_controls(self) -> None:
        if not self._plot_widgets or len(self._stacked_time) < 2:
            self._timeline_slider.setEnabled(False)
            self._zoom_slider.setEnabled(False)
            self._autoscale_btn.setEnabled(False)
            self._measurement_menu_btn.setEnabled(False)
            self._timeline_dec_btn.setEnabled(False)
            self._timeline_inc_btn.setEnabled(False)
            self._zoom_dec_btn.setEnabled(False)
            self._zoom_inc_btn.setEnabled(False)
            self._timeline_range_label.setText("-- to --")
            self._zoom_percent_label.setText("0%")
            return

        self._timeline_slider.setEnabled(True)
        self._zoom_slider.setEnabled(True)
        self._autoscale_btn.setEnabled(True)
        self._measurement_menu_btn.setEnabled(True)
        self._timeline_dec_btn.setEnabled(True)
        self._timeline_inc_btn.setEnabled(True)
        self._zoom_dec_btn.setEnabled(True)
        self._zoom_inc_btn.setEnabled(True)

        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        span = max(t_max - t_min, 1e-15)

        low_unit = self._timeline_slider.lowValue()
        high_unit = self._timeline_slider.highValue()
        if high_unit <= low_unit:
            high_unit = min(1000, low_unit + 1)
            self._timeline_slider.setValues(low_unit, high_unit)

        start = t_min + span * (low_unit / 1000.0)
        end = t_min + span * (high_unit / 1000.0)
        if end <= start:
            end = min(t_max, start + (span / 1000.0))

        first = self._plot_widgets[0]
        first.setXRange(start, end, padding=0)
        self._timeline_range_label.setText(
            f"{self._format_time_display(start)} to {self._format_time_display(end)}"
        )

        window_fraction = max(0.05, min(1.0, (end - start) / span))
        zoom_percent = int(round(((1.0 - window_fraction) / 0.95) * 100.0))
        zoom_percent = min(100, max(0, zoom_percent))
        self._zoom_percent_label.setText(f"{zoom_percent}%")

        slider_zoom_value = self._zoom_slider.value()
        if slider_zoom_value != zoom_percent:
            self._syncing_bottom_sliders = True
            try:
                self._zoom_slider.setValue(zoom_percent)
            finally:
                self._syncing_bottom_sliders = False

    def _refresh_bottom_controls_enabled(self) -> None:
        has_data = len(self._stacked_time) > 1 and bool(self._plot_widgets)
        self._timeline_slider.setEnabled(has_data)
        self._zoom_slider.setEnabled(has_data)
        self._autoscale_btn.setEnabled(has_data)
        self._measurement_menu_btn.setEnabled(has_data)

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
        self._scope_bottom_tab.setVisible(bool(checked))
        self._sync_toolbar_toggles()
        self._set_stacked_cursor_enabled(len(self._stacked_time) > 0)
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_stacked_grid_toggled(self, checked: bool) -> None:
        self._stacked_grid_enabled = checked
        self._sync_toolbar_toggles()
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
            self._stacked_plot_groups = {}
            self._stacked_active_signal = None
            self._selected_plot_group_leader = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._scope_selector_combo.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._sync_trace_style_controls()
            self._refresh_bottom_controls_enabled()
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
            self._stacked_plot_groups = {}
            self._stacked_active_signal = None
            self._selected_plot_group_leader = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._scope_selector_combo.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._sync_trace_style_controls()
            self._refresh_bottom_controls_enabled()
            return

        self._stacked_time = time
        self._stacked_signals = valid_signals
        self._sync_plot_groups()
        self._rebuild_stacked_statistics_cache()

        previous_visible = set(self._stacked_signal_list.get_visible_signals())
        previous_active = self._stacked_active_signal

        groups: dict[str, list[str]] = {}
        for name in valid_signals:
            leader = self._stacked_plot_groups.get(name, name)
            groups.setdefault(leader, []).append(name)
        self._stacked_signal_list.set_signals_with_groups(groups)
        self._apply_stacked_trace_colors()

        if previous_visible:
            default_visible = {name for name in previous_visible if name in valid_signals}
        else:
            default_visible = set(valid_signals.keys())
        for name in valid_signals:
            self._stacked_signal_list.set_signal_visible(name, name in default_visible)

        visible = self._stacked_signal_list.get_visible_signals()
        if not visible:
            first = next(iter(valid_signals))
            self._stacked_signal_list.set_signal_visible(first, True)
            visible = [first]

        if previous_active in valid_signals:
            self._stacked_active_signal = previous_active
        else:
            self._stacked_active_signal = visible[0]
        if self._stacked_active_signal in self._stacked_signals:
            self._selected_plot_group_leader = self._plot_group_leader(self._stacked_active_signal)
        else:
            self._selected_plot_group_leader = None

        self._sync_scope_selector()
        self._configure_stacked_cursor_spins()
        self._update_stacked_measurements()
        self._sync_trace_style_controls()
        self._refresh_bottom_controls_enabled()

    def _sync_scope_selector(self) -> None:
        names = list(self._stacked_signals.keys())
        current = self._stacked_active_signal if self._stacked_active_signal in names else (names[0] if names else "")
        self._scope_selector_combo.blockSignals(True)
        try:
            self._scope_selector_combo.clear()
            self._scope_selector_combo.addItems(names)
            if current:
                idx = self._scope_selector_combo.findText(current)
                if idx >= 0:
                    self._scope_selector_combo.setCurrentIndex(idx)
        finally:
            self._scope_selector_combo.blockSignals(False)
        self._create_math_signal_btn.setEnabled(bool(names))
        if hasattr(self, "_toolbar_scope_label"):
            self._toolbar_scope_label.setText(current or (self._component_name or "No signal"))

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
        if self._stacked_active_signal in self._stacked_signals:
            self._selected_plot_group_leader = self._plot_group_leader(self._stacked_active_signal)
        else:
            self._selected_plot_group_leader = None
        self._sync_scope_selector()
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_stacked_signal_selected(self, signal_name: str) -> None:
        if signal_name in self._stacked_signals:
            self._stacked_active_signal = signal_name
            self._selected_plot_group_leader = self._plot_group_leader(signal_name)
            self._sync_scope_selector()
            combo_index = self._trace_signal_combo.findText(signal_name)
            if combo_index >= 0:
                self._trace_signal_combo.blockSignals(True)
                self._trace_signal_combo.setCurrentIndex(combo_index)
                self._trace_signal_combo.blockSignals(False)
            self._set_trace_controls_for_signal(signal_name)
            self._update_stacked_measurements()

    def _on_stacked_signal_double_clicked(self, signal_name: str) -> None:
        if signal_name not in self._stacked_signals:
            return

        self._on_stacked_signal_selected(signal_name)

        current_width = self._trace_style_width(signal_name)
        new_width, width_ok = QInputDialog.getDouble(
            self,
            "Trace Style",
            f"{signal_name} width:",
            current_width,
            0.5,
            20.0,
            2,
        )
        if width_ok:
            style = self._trace_styles.setdefault(signal_name, {})
            style["width"] = max(0.5, float(new_width))

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
        if picked.isValid():
            style = self._trace_styles.setdefault(signal_name, {})
            style["color"] = (picked.red(), picked.green(), picked.blue())

        self._prune_trace_style(signal_name)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        self._rebuild_stacked_plots(self._current_result)
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

    @staticmethod
    def _format_trace_value(value: float) -> str:
        abs_val = abs(value)
        if abs_val >= 1e3 or (0 < abs_val < 1e-3):
            return f"{value:.3e}"
        return f"{value:.6g}"

    def _build_hover_tooltip_html(
        self,
        cursor_time: float,
        sample_rows: list[tuple[str, float, tuple[int, int, int]]],
        *,
        primary_signal_name: str | None = None,
    ) -> str:
        """Build hover tooltip HTML for one or multiple traces in the same plot."""
        rows: list[str] = [
            (
                "<span style='color:#9ca3af;'>t</span> = "
                f"<span style='font-weight:600'>{self._format_time_display(cursor_time)}</span>"
            )
        ]
        for signal_name, value, color in sample_rows:
            color_hex = self._rgb_to_hex(color)
            name_html = f"<b>{signal_name}</b>" if signal_name == primary_signal_name else signal_name
            rows.append(

                    f"<span style='color:{color_hex};'>●</span> "
                    f"{name_html}: <span style='font-family:monospace;'>{self._format_trace_value(value)}</span>"

            )
        return (
            "<div style='padding:4px 6px; border-radius:6px; "
            "background:rgba(20,20,20,0.78); color:#f4f4f4; font-size:10px;'>"
            + "<br/>".join(rows)
            + "</div>"
        )

    def _style_stacked_axes(self, plot_item: pg.PlotItem) -> None:
        tick_font = QFont()
        tick_font.setPointSize(9)
        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setStyle(
                tickFont=tick_font,
                autoExpandTextSpace=False,
                tickTextOffset=6,
            )

    def _attach_plot_interactions(
        self,
        plot: pg.PlotWidget,
        time: np.ndarray,
        line_color: tuple[int, int, int],
        hover_series: list[tuple[str, np.ndarray, tuple[int, int, int]]],
        primary_signal_name: str,
    ) -> None:
        if len(time) == 0 or not hover_series:
            return

        plot_item = plot.getPlotItem()
        view_box = plot_item.getViewBox()
        hover_line_color = (
            line_color[0],
            line_color[1],
            line_color[2],
            170,
        )
        vline = pg.InfiniteLine(
            angle=90,
            movable=False,
            pen=pg.mkPen(color=hover_line_color, width=1.2, style=Qt.PenStyle.DotLine),
        )
        hline = pg.InfiniteLine(
            angle=0,
            movable=False,
            pen=pg.mkPen(color=hover_line_color, width=1.0, style=Qt.PenStyle.DotLine),
        )
        tooltip = pg.TextItem(anchor=(0, 1))
        vline.hide()
        hline.hide()
        tooltip.hide()
        plot_item.addItem(vline, ignoreBounds=True)
        plot_item.addItem(hline, ignoreBounds=True)
        plot_item.addItem(tooltip, ignoreBounds=True)
        self._stacked_hover_items.append((vline, hline, tooltip))

        def on_mouse_moved(pos) -> None:
            if not plot.sceneBoundingRect().contains(pos):
                vline.hide()
                hline.hide()
                tooltip.hide()
                return
            mapped = view_box.mapSceneToView(pos)
            x_val = float(mapped.x())
            t_start = float(time[0])
            t_end = float(time[-1])
            if t_end < t_start:
                t_start, t_end = t_end, t_start
            x_clamped = min(max(x_val, t_start), t_end)

            sample_rows: list[tuple[str, float, tuple[int, int, int]]] = []
            for row_signal_name, row_values, row_color in hover_series:
                if len(row_values) == 0:
                    continue
                y_val = float(np.interp(x_clamped, time, row_values))
                sample_rows.append((row_signal_name, y_val, row_color))
            if not sample_rows:
                vline.hide()
                hline.hide()
                tooltip.hide()
                return

            primary_row = next(
                (row for row in sample_rows if row[0] == primary_signal_name),
                sample_rows[0],
            )
            y_clamped = primary_row[1]

            vline.setPos(x_clamped)
            hline.setPos(y_clamped)
            vline.show()
            hline.show()

            tooltip.setHtml(
                self._build_hover_tooltip_html(
                    x_clamped,
                    sample_rows,
                    primary_signal_name=primary_signal_name,
                )
            )
            x_range, y_range = view_box.viewRange()
            x_span = max(1e-15, float(x_range[1]) - float(x_range[0]))
            y_span = max(1e-15, float(y_range[1]) - float(y_range[0]))
            tooltip.setPos(x_clamped + (0.01 * x_span), y_clamped + (0.045 * y_span))
            tooltip.show()

        def on_mouse_clicked(ev) -> None:
            if not ev.double():
                return
            if ev.button() != Qt.MouseButton.LeftButton:
                return
            if not plot.sceneBoundingRect().contains(ev.scenePos()):
                return
            self._on_autoscale_clicked()
            ev.accept()

        scene = plot.scene()
        scene.sigMouseMoved.connect(on_mouse_moved)
        scene.sigMouseClicked.connect(on_mouse_clicked)
        self._stacked_plot_interaction_refs.append((on_mouse_moved, on_mouse_clicked))

    def _copy_plot_to_clipboard(self, plot: pg.PlotWidget | None) -> None:
        """Copy one plot panel image to the system clipboard."""
        if plot is None:
            return
        pixmap = plot.grab()
        if pixmap.isNull():
            return
        QGuiApplication.clipboard().setPixmap(pixmap)
        self._message_label.setText("Plot image copied to clipboard.")

    def _rebuild_stacked_plots(self, result: SimulationResult | None) -> None:
        self._clear_stacked_plots()

        if not result or len(self._stacked_time) == 0 or not self._stacked_signals:
            empty = QLabel("No signals to plot. Connect scope channels and run simulation.")
            empty.setWordWrap(True)
            self._stacked_layout.addWidget(empty)
            self._stacked_layout.addStretch()
            self._refresh_bottom_controls_enabled()
            return

        time = self._stacked_time
        palette = self._trace_palette()
        first_plot: pg.PlotWidget | None = None
        visible = set(self._stacked_signal_list.get_visible_signals())
        visible_signal_names = [
            name for name in self._stacked_signals if (not visible or name in visible)
        ]

        if not visible_signal_names:
            empty = QLabel("No visible signals. Enable at least one signal in the list.")
            empty.setWordWrap(True)
            self._stacked_layout.addWidget(empty)
            self._stacked_layout.addStretch()
            self._refresh_bottom_controls_enabled()
            return

        self._sync_plot_groups()
        grouped_signals: dict[str, list[str]] = {}
        for signal_name in visible_signal_names:
            leader = self._plot_group_leader(signal_name)
            grouped_signals.setdefault(leader, []).append(signal_name)
        group_items = list(grouped_signals.items())
        visible_leaders = [leader for leader, _group_signals in group_items]
        if self._selected_plot_group_leader not in visible_leaders:
            active_leader = (
                self._plot_group_leader(self._stacked_active_signal)
                if self._stacked_active_signal in self._stacked_signals
                else None
            )
            if active_leader in visible_leaders:
                self._selected_plot_group_leader = active_leader
            else:
                self._selected_plot_group_leader = visible_leaders[0] if visible_leaders else None
        if self._selected_plot_group_leader in grouped_signals:
            selected_group = grouped_signals[self._selected_plot_group_leader]
            if self._stacked_active_signal not in selected_group:
                self._stacked_active_signal = selected_group[0]
        signal_order = list(self._stacked_signals.keys())
        points_per_signal = self._stacked_target_points_per_signal(len(visible_signal_names))

        for idx, (group_leader, group_signal_names) in enumerate(group_items):
            if self._stacked_active_signal in group_signal_names:
                primary_signal_name = str(self._stacked_active_signal)
            else:
                primary_signal_name = group_signal_names[0]

            primary_color = self._trace_style_color(primary_signal_name)
            if primary_color is None:
                primary_color = self._stacked_signal_list.get_signal_color(primary_signal_name)
            if primary_color is None:
                color_index = signal_order.index(primary_signal_name)
                primary_color = palette[color_index % len(palette)]
            r, g, b = primary_color
            hex_color = f"#{r:02x}{g:02x}{b:02x}"

            sig_stats = self._stacked_signal_stats.get(primary_signal_name, {})
            is_active = self._stacked_active_signal in group_signal_names

            panel = QFrame()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(0)

            # --- Header row: colored dot + name + mini stats ---
            header_widget = QWidget()
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(12, 8, 12, 6)
            header_layout.setSpacing(8)

            if len(group_signal_names) == 1:
                header_title = f"●  {primary_signal_name}"
            else:
                header_title = f"●  {primary_signal_name}  (+{len(group_signal_names) - 1})"
            dot_and_name = QLabel(header_title)
            dot_and_name.setObjectName("stackedPanelTitle")
            header_layout.addWidget(dot_and_name, stretch=1)

            # Mini stats row
            if sig_stats:
                fmt = "{:.4g}"
                stats_str = (
                    f"RMS: {fmt.format(sig_stats.get('rms', 0))}  "
                    f"Peak: {fmt.format(sig_stats.get('max', 0))}  "
                    f"Avg: {fmt.format(sig_stats.get('mean', 0))}"
                )
                stats_lbl = QLabel(stats_str)
                stats_lbl.setObjectName("stackedPanelStats")
                header_layout.addWidget(stats_lbl)

            panel_layout.addWidget(header_widget)

            # --- Plot ---
            plot = pg.PlotWidget(
                viewBox=ScopePlotViewBox(
                    group_leader=group_leader,
                    wheel_handler=self._on_group_plot_wheel,
                    select_handler=self._on_group_plot_selected,
                )
            )
            plot.setMinimumHeight(220)
            plot.getPlotItem().hideButtons()
            grid_alpha = 0.23
            if not self._stacked_grid_enabled:
                grid_alpha = 0.0
            plot.showGrid(x=self._stacked_grid_enabled, y=self._stacked_grid_enabled, alpha=grid_alpha)
            item = plot.getPlotItem()
            item.setLabel("left", "")
            self._style_stacked_axes(item)
            if idx == len(group_items) - 1:
                item.setLabel("bottom", "Time", units="s")
            else:
                item.getAxis("bottom").setStyle(showValues=False)

            if first_plot is None:
                first_plot = plot
            else:
                plot.setXLink(first_plot)

            if len(group_signal_names) > 1:
                item.addLegend(offset=(8, 8))

            hover_series: list[tuple[str, np.ndarray, tuple[int, int, int]]] = []
            for signal_name in group_signal_names:
                values = self._stacked_signals.get(signal_name)
                if values is None:
                    continue
                t_trace, plot_values = self._decimate_stacked_for_display(
                    time,
                    values,
                    max_points=points_per_signal,
                )
                color = self._trace_style_color(signal_name)
                if color is None:
                    color = self._stacked_signal_list.get_signal_color(signal_name)
                if color is None:
                    color_index = signal_order.index(signal_name)
                    color = palette[color_index % len(palette)]
                line_width = self._trace_style_width(signal_name)
                if signal_name == self._stacked_active_signal:
                    line_width = min(8.0, line_width + 0.35)
                pen = pg.mkPen(color=color, width=line_width)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                trace_name = signal_name if len(group_signal_names) > 1 else None
                trace = plot.plot(
                    t_trace,
                    plot_values,
                    pen=pen,
                    name=trace_name,
                    skipFiniteCheck=True,
                )
                self._configure_stacked_trace_performance(trace, len(t_trace))
                hover_series.append((signal_name, values, color))

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

            plot_container = QWidget()
            plot_overlay_layout = QGridLayout(plot_container)
            plot_overlay_layout.setContentsMargins(0, 0, 0, 0)
            plot_overlay_layout.setSpacing(0)
            plot_overlay_layout.addWidget(plot, 0, 0)
            copy_plot_btn = QToolButton(plot_container)
            copy_plot_btn.setObjectName("scopePlotCopyBtn")
            copy_plot_btn.setText("Copy")
            copy_plot_btn.setToolTip("Copy this plot image to clipboard")
            copy_plot_btn.clicked.connect(
                lambda _checked=False, target_plot=plot: self._copy_plot_to_clipboard(target_plot)
            )
            plot_overlay_layout.addWidget(
                copy_plot_btn,
                0,
                0,
                alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
            )

            panel_layout.addWidget(plot_container)

            # --- Apply theming ---
            shell = self._scope_shell_palette()
            plot_colors = self._scope_plot_palette()
            plot.setBackground(plot_colors["plot_bg"])
            for axis_name in ("left", "bottom"):
                axis = item.getAxis(axis_name)
                axis.setPen(pg.mkPen(plot_colors["plot_axis"]))
                axis.setTickPen(pg.mkPen(plot_colors["plot_axis"]))
                axis.setTextPen(pg.mkPen(plot_colors["plot_text"]))
            plot.showGrid(
                x=self._stacked_grid_enabled,
                y=self._stacked_grid_enabled,
                alpha=0.23,
            )

            header_bg = shell["header_bg"] if is_active else shell["panel_bg"]
            name_weight = "700" if is_active else "600"
            dot_and_name.setStyleSheet(
                f"color: {hex_color}; font-weight: {name_weight}; font-size: 12px;"
            )
            if sig_stats:
                stats_lbl.setStyleSheet(
                    f"color: {shell['muted']}; font-size: 10px; font-family: monospace; font-weight: 500;"
                )
            panel.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {shell["panel_bg"]};
                    border: 1px solid {shell["border"]};
                    border-left: 3px solid {hex_color};
                    border-radius: 10px;
                }}
                """
            )
            header_widget.setStyleSheet(
                f"background-color: {header_bg}; border-radius: 7px; margin: 0; border: 1px solid {shell['border_soft']};"
            )

            self._attach_plot_interactions(
                plot,
                time=time,
                line_color=primary_color,
                hover_series=hover_series,
                primary_signal_name=primary_signal_name,
            )
            self._stacked_layout.addWidget(panel)
            self._plot_widgets.append(plot)

        self._refresh_bottom_controls_enabled()
        self._apply_bottom_viewport_controls()

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
