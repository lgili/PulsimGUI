"""Floating windows that host per-component scope viewers."""

from __future__ import annotations

import re
from collections.abc import Callable

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QAction,
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
    QAbstractItemView,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.component import ComponentType
from pulsimgui.resources.icons import IconService
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.scope_workbench import normalize_interval_target
from pulsimgui.services.theme_service import LIGHT_THEME, Theme, ThemeService
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


class ScopePlotWidget(pg.PlotWidget):
    """Plot widget that accepts signal drops onto a specific plot group."""

    def __init__(
        self,
        *,
        group_leader: str,
        drop_handler: Callable[[str, str | None], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._group_leader = group_leader
        self._drop_handler = drop_handler
        self.setAcceptDrops(True)

    def _dragged_signal_name(self, event) -> str | None:
        return SignalListPanel.signal_name_from_mime(event.mimeData())

    def dragEnterEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        signal_name = self._dragged_signal_name(event)
        if signal_name and self._drop_handler is not None:
            if self._drop_handler(signal_name, self._group_leader):
                event.acceptProposedAction()
                return
        super().dropEvent(event)


class ScopeWorkspaceDropArea(QWidget):
    """Central workspace drop area for assigning a signal to a dedicated pane."""

    def __init__(
        self,
        *,
        drop_handler: Callable[[str, str | None], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._drop_handler = drop_handler
        self.setAcceptDrops(True)

    def _dragged_signal_name(self, event) -> str | None:
        return SignalListPanel.signal_name_from_mime(event.mimeData())

    def dragEnterEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        signal_name = self._dragged_signal_name(event)
        if signal_name and self._drop_handler is not None:
            if self._drop_handler(signal_name, None):
                event.acceptProposedAction()
                return
        super().dropEvent(event)


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
        self._plot_right_view_boxes: list[pg.ViewBox] = []
        self._syncing_stacked_cursor_controls = False
        self._stacked_cursor_initialized = False
        self._trace_styles: dict[str, dict[str, object]] = {}
        self._stacked_plot_groups: dict[str, str] = {}
        self._selected_plot_group_leader: str | None = None
        self._default_trace_width = self.DEFAULT_TRACE_WIDTH
        self._syncing_trace_style_controls = False
        self._syncing_bottom_sliders = False
        self._stacked_interval_target: str = "full"
        self._saved_views: dict[str, tuple[float, float]] = {}
        self._signal_axis_targets: dict[str, str] = {}
        self._signal_labels: dict[str, str] = {}
        self._inspector_snap_mode: str = "none"
        self._bottom_drawer_expanded = False
        self._bottom_drawer_height = 196
        self._bottom_drawer_active_tab = 0
        self._bottom_events: list[str] = []
        self._simulation_state: str = "ready"
        self._scope_actions: dict[str, QAction] = {}
        self._panel_anim_timer: QTimer | None = None
        self._panel_anim_steps: int = 8
        self._panel_anim_target: list[int] = []
        self._panel_anim_current_step: int = 0

        self._viewer = WaveformViewer(theme_service=self._theme_service)
        self._viewer.setMinimumSize(820, 500)
        self._viewer.set_manual_signal_add_enabled(False)
        self._viewer.set_auto_show_all_signals(True)
        self._viewer.set_default_trace_width(self._default_trace_width)
        self._viewer.set_trace_styles(self._trace_styles)

        self._trace_signal_combo = QComboBox()
        self._trace_signal_combo.setMinimumWidth(260)
        self._trace_signal_combo.currentTextChanged.connect(self._on_trace_style_signal_changed)
        self._trace_alias_edit = QLineEdit()
        self._trace_alias_edit.setPlaceholderText("Use signal name")
        self._trace_alias_edit.editingFinished.connect(self._on_trace_alias_edited)
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
        self._stacked_page_layout = QVBoxLayout(self._stacked_page)
        self._stacked_page_layout.setContentsMargins(0, 0, 0, 0)
        self._stacked_page_layout.setSpacing(0)
        self._stacked_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._stacked_page_layout.addWidget(self._stacked_splitter)

        self._stacked_sidebar = QWidget()
        self._stacked_sidebar.setObjectName("scopeLeftPanel")
        self._stacked_sidebar.setMinimumWidth(270)
        self._stacked_sidebar.setMaximumWidth(380)
        stacked_sidebar_layout = QVBoxLayout(self._stacked_sidebar)
        stacked_sidebar_layout.setContentsMargins(10, 10, 10, 10)
        stacked_sidebar_layout.setSpacing(8)

        sidebar_top = QWidget()
        sidebar_top.setObjectName("scopeSidebarHeader")
        self._left_sidebar_top_row = sidebar_top
        sidebar_top_layout = QHBoxLayout(sidebar_top)
        sidebar_top_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_top_layout.setSpacing(6)
        self._left_scope_label = QLabel("Signals")
        self._left_scope_label.setObjectName("scopeSidebarTitle")
        sidebar_top_layout.addWidget(self._left_scope_label)
        sidebar_top_layout.addStretch(1)
        self._left_panel_toggle_btn = QPushButton("◀")
        self._left_panel_toggle_btn.setObjectName("scopePanelToggleBtn")
        self._left_panel_toggle_btn.setCheckable(True)
        self._left_panel_toggle_btn.setChecked(True)
        self._left_panel_toggle_btn.setFixedWidth(26)
        self._left_panel_toggle_btn.setToolTip("Collapse left panel")
        self._left_panel_toggle_btn.clicked.connect(self._on_toggle_left_panel_clicked)
        self._toggle_sidebar_shortcut = QShortcut(QKeySequence("Ctrl+B"), self)
        self._toggle_sidebar_shortcut.activated.connect(self._on_toggle_sidebar_shortcut)
        sidebar_top_layout.addWidget(self._left_panel_toggle_btn, stretch=0)
        stacked_sidebar_layout.addWidget(sidebar_top, stretch=0)

        self._scope_selector_row = QWidget()
        self._scope_selector_row.setObjectName("scopeSidebarSelectorRow")
        selector_layout = QHBoxLayout(self._scope_selector_row)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        selector_layout.setSpacing(6)
        self._scope_selector_hint = QLabel("Active Scope")
        self._scope_selector_hint.setObjectName("scopeSidebarHint")
        selector_layout.addWidget(self._scope_selector_hint, stretch=0)
        self._scope_selector_combo = QComboBox()
        self._scope_selector_combo.setObjectName("scopeSidebarScopeCombo")
        self._scope_selector_combo.setMinimumWidth(130)
        self._scope_selector_combo.currentTextChanged.connect(self._on_scope_selector_changed)
        selector_layout.addWidget(self._scope_selector_combo, stretch=1)
        stacked_sidebar_layout.addWidget(self._scope_selector_row, stretch=0)

        sidebar_actions = QWidget()
        sidebar_actions.setObjectName("scopeSidebarActionRow")
        self._left_sidebar_actions_row = sidebar_actions
        sidebar_actions_layout = QHBoxLayout(sidebar_actions)
        sidebar_actions_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_actions_layout.setSpacing(0)
        self._create_math_signal_btn = QPushButton("+ Add Signal Expression...")
        self._create_math_signal_btn.setObjectName("scopeAddSignalExprBtn")
        self._create_math_signal_btn.clicked.connect(self._on_create_math_signal_clicked)
        sidebar_actions_layout.addWidget(self._create_math_signal_btn, stretch=1)

        # Collapsed rail: icon buttons shown only when sidebar is collapsed
        self._collapsed_rail = QWidget()
        self._collapsed_rail.setObjectName("scopeCollapsedRail")
        collapsed_rail_layout = QVBoxLayout(self._collapsed_rail)
        collapsed_rail_layout.setContentsMargins(4, 4, 4, 4)
        collapsed_rail_layout.setSpacing(6)
        for _rail_icon, _rail_tooltip, _rail_tab_idx in (
            ("activity", "Signals", 0),
            ("layers", "Scopes", 1),
            ("grid", "Traces", 2),
            ("eye", "Views", 3),
        ):
            _rail_btn = QToolButton()
            _rail_btn.setObjectName("scopeCollapsedRailBtn")
            _rail_btn.setToolTip(_rail_tooltip)
            _rail_btn.setFixedSize(QSize(30, 30))
            _rail_btn.setIcon(IconService.get_icon(_rail_icon, "#91a0bf", 14))
            _rail_btn.setIconSize(QSize(14, 14))

            def _make_rail_handler(tab_idx: int) -> Callable[[], None]:
                def _handler() -> None:
                    self._left_panel_visible = True
                    self._left_panel_toggle_btn.blockSignals(True)
                    self._left_panel_toggle_btn.setChecked(True)
                    self._left_panel_toggle_btn.blockSignals(False)
                    self._apply_panel_visibility()
                    self._sidebar_tabs.setCurrentIndex(tab_idx)
                return _handler

            _rail_btn.clicked.connect(_make_rail_handler(_rail_tab_idx))
            collapsed_rail_layout.addWidget(_rail_btn)
        collapsed_rail_layout.addStretch(1)
        self._collapsed_rail.setVisible(False)
        stacked_sidebar_layout.addWidget(self._collapsed_rail, stretch=0)

        # QTabWidget with 4 tabs
        self._sidebar_tabs = QTabWidget()
        self._sidebar_tabs.setObjectName("scopeSidebarTabs")
        self._sidebar_tabs.setDocumentMode(True)
        self._sidebar_tabs.tabBar().setExpanding(False)

        # Tab 0: Signals
        _signals_tab_widget = QWidget()
        _signals_tab_layout = QVBoxLayout(_signals_tab_widget)
        _signals_tab_layout.setContentsMargins(0, 6, 0, 0)
        _signals_tab_layout.setSpacing(8)
        self._sidebar_tabs.addTab(_signals_tab_widget, "Signals")

        # Tab 1: Scopes
        _scopes_tab_widget = QWidget()
        _scopes_tab_layout = QVBoxLayout(_scopes_tab_widget)
        _scopes_tab_layout.setContentsMargins(0, 4, 0, 0)
        _scopes_tab_layout.setSpacing(4)
        self._scopes_list_widget = QListWidget()
        _scopes_tab_layout.addWidget(self._scopes_list_widget, stretch=1)
        _scopes_btn_row = QWidget()
        _scopes_btn_layout = QHBoxLayout(_scopes_btn_row)
        _scopes_btn_layout.setContentsMargins(0, 0, 0, 0)
        _scopes_btn_layout.setSpacing(4)
        self._scope_rename_btn = QPushButton("Rename")
        self._scope_rename_btn.clicked.connect(self._on_scope_renamed)
        self._scope_duplicate_btn = QPushButton("Duplicate")
        _scopes_btn_layout.addWidget(self._scope_rename_btn)
        _scopes_btn_layout.addWidget(self._scope_duplicate_btn)
        _scopes_btn_layout.addStretch(1)
        _scopes_tab_layout.addWidget(_scopes_btn_row, stretch=0)
        self._sidebar_tabs.addTab(_scopes_tab_widget, "Scopes")

        # Tab 2: Traces
        _traces_tab_widget = QWidget()
        _traces_tab_layout = QVBoxLayout(_traces_tab_widget)
        _traces_tab_layout.setContentsMargins(0, 4, 0, 0)
        _traces_tab_layout.setSpacing(4)
        self._traces_list_widget = QListWidget()
        _traces_tab_layout.addWidget(self._traces_list_widget, stretch=1)
        self._sidebar_tabs.addTab(_traces_tab_widget, "Traces")

        # Tab 3: Views
        _views_tab_widget = QWidget()
        _views_tab_layout = QVBoxLayout(_views_tab_widget)
        _views_tab_layout.setContentsMargins(0, 4, 0, 0)
        _views_tab_layout.setSpacing(4)
        self._views_list_widget = QListWidget()
        _views_tab_layout.addWidget(self._views_list_widget, stretch=1)
        _views_btn_row = QWidget()
        _views_btn_layout = QHBoxLayout(_views_btn_row)
        _views_btn_layout.setContentsMargins(0, 0, 0, 0)
        _views_btn_layout.setSpacing(4)
        self._save_view_btn = QPushButton("Save view")
        self._save_view_btn.clicked.connect(self._on_save_view_clicked)
        self._delete_view_btn = QPushButton("Delete")
        _views_btn_layout.addWidget(self._save_view_btn)
        _views_btn_layout.addWidget(self._delete_view_btn)
        _views_btn_layout.addStretch(1)
        _views_tab_layout.addWidget(_views_btn_row, stretch=0)
        self._sidebar_tabs.addTab(_views_tab_widget, "Views")

        stacked_sidebar_layout.addWidget(self._sidebar_tabs, stretch=1)

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
        self._stacked_signal_list.signal_axis_badge_clicked.connect(
            self._on_signal_axis_badge_clicked
        )
        self._stacked_signal_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._stacked_signal_list.customContextMenuRequested.connect(
            self._on_signal_list_context_menu
        )
        _signals_tab_layout.addWidget(self._stacked_signal_list, stretch=1)
        _signals_tab_layout.addWidget(sidebar_actions, stretch=0)

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
        self._right_header_label = QLabel("Inspector")
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
        self._interval_combo = QComboBox()
        self._interval_combo.addItem("Full Range", "full")
        self._interval_combo.addItem("Visible Window", "window")
        self._interval_combo.addItem("Between Cursors", "a_to_b")
        self._interval_combo.currentTextChanged.connect(self._on_interval_target_changed)
        right_controls_layout.addStretch(1)
        self._stacked_right_controls.setVisible(False)

        self._inspector_visible_toggle = QCheckBox("Visible")
        self._inspector_visible_toggle.toggled.connect(self._on_inspector_visible_toggled)

        self._inspector_axis_combo = QComboBox()
        self._inspector_axis_combo.addItem("Left", "left")
        self._inspector_axis_combo.addItem("Right", "right")
        self._inspector_axis_combo.addItem("New Plot", "new_plot")
        self._inspector_axis_combo.currentIndexChanged.connect(self._on_inspector_axis_changed)

        self._inspector_autoscale_toggle = QCheckBox("Auto Scale")
        self._inspector_autoscale_toggle.setChecked(True)

        self._inspector_min_spin = QDoubleSpinBox()
        self._inspector_min_spin.setDecimals(5)
        self._inspector_min_spin.setRange(-1e12, 1e12)
        self._inspector_min_spin.setEnabled(False)

        self._inspector_max_spin = QDoubleSpinBox()
        self._inspector_max_spin.setDecimals(5)
        self._inspector_max_spin.setRange(-1e12, 1e12)
        self._inspector_max_spin.setEnabled(False)

        self._inspector_line_style_combo = QComboBox()
        self._inspector_line_style_combo.addItem("Solid", "solid")
        self._inspector_line_style_combo.addItem("Dashed", "dashed")
        self._inspector_line_style_combo.addItem("Dotted", "dotted")
        self._inspector_line_style_combo.setEnabled(False)

        self._inspector_snap_combo = QComboBox()
        self._inspector_snap_combo.addItem("None", "none")
        self._inspector_snap_combo.addItem("Samples", "samples")
        self._inspector_snap_combo.addItem("Peaks", "peaks")
        self._inspector_snap_combo.addItem("Edges", "edges")
        self._inspector_snap_combo.addItem("Zero Crossings", "zero_crossings")
        self._inspector_snap_combo.currentIndexChanged.connect(self._on_inspector_snap_mode_changed)

        self._inspector_interval_combo = QComboBox()
        self._inspector_interval_combo.addItem("Full Range", "full")
        self._inspector_interval_combo.addItem("Visible Window", "window")
        self._inspector_interval_combo.addItem("Between Cursors", "a_to_b")
        self._inspector_interval_combo.currentIndexChanged.connect(
            self._on_inspector_interval_changed
        )

        self._inspector_measure_menu_btn = QToolButton()
        self._inspector_measure_menu_btn.setObjectName("scopeMeasurementMenuBtn")
        self._inspector_measure_menu_btn.setText("+ Add Measurement")
        self._inspector_measure_menu_btn.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self._inspector_measure_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        trace_body = QWidget()
        trace_form = QFormLayout(trace_body)
        trace_form.setContentsMargins(0, 0, 0, 0)
        trace_form.setSpacing(8)
        trace_form.addRow("Signal", self._trace_signal_combo)
        trace_form.addRow("Alias", self._trace_alias_edit)
        trace_form.addRow("", self._inspector_visible_toggle)
        trace_form.addRow("Color", self._trace_color_btn)

        axis_body = QWidget()
        axis_form = QFormLayout(axis_body)
        axis_form.setContentsMargins(0, 0, 0, 0)
        axis_form.setSpacing(8)
        axis_form.addRow("Target", self._inspector_axis_combo)
        axis_form.addRow("", self._inspector_autoscale_toggle)
        axis_form.addRow("Min", self._inspector_min_spin)
        axis_form.addRow("Max", self._inspector_max_spin)

        style_body = QWidget()
        style_form = QFormLayout(style_body)
        style_form.setContentsMargins(0, 0, 0, 0)
        style_form.setSpacing(8)
        style_form.addRow("Line Style", self._inspector_line_style_combo)
        style_form.addRow("Thickness", self._trace_width_spin)
        style_form.addRow("Reset", self._trace_reset_btn)

        cursor_body = QWidget()
        cursor_form = QFormLayout(cursor_body)
        cursor_form.setContentsMargins(0, 0, 0, 0)
        cursor_form.setSpacing(8)
        cursor_form.addRow("", self._stacked_cursor_toggle)
        cursor_form.addRow("X1", self._c1_spin)
        cursor_form.addRow("X2", self._c2_spin)
        cursor_form.addRow("Snap", self._inspector_snap_combo)

        measure_body = QWidget()
        measure_form = QFormLayout(measure_body)
        measure_form.setContentsMargins(0, 0, 0, 0)
        measure_form.setSpacing(8)
        measure_form.addRow("Scope", self._inspector_interval_combo)
        measure_form.addRow("Columns", self._inspector_measure_menu_btn)

        self._inspector_scroll = QScrollArea()
        self._inspector_scroll.setObjectName("scopeInspectorScroll")
        self._inspector_scroll.setWidgetResizable(True)
        self._inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._inspector_content = QWidget()
        self._inspector_content.setObjectName("scopeInspectorContent")
        inspector_layout = QVBoxLayout(self._inspector_content)
        inspector_layout.setContentsMargins(0, 2, 0, 0)
        inspector_layout.setSpacing(8)
        inspector_layout.addWidget(self._create_inspector_section("Trace", trace_body))
        inspector_layout.addWidget(self._create_inspector_section("Axis", axis_body))
        inspector_layout.addWidget(self._create_inspector_section("Style", style_body))
        inspector_layout.addWidget(self._create_inspector_section("Cursor", cursor_body))
        inspector_layout.addWidget(
            self._create_inspector_section("Measurements", measure_body)
        )
        inspector_layout.addStretch(1)
        self._inspector_scroll.setWidget(self._inspector_content)
        right_layout.addWidget(self._inspector_scroll, stretch=1)

        self._stacked_scroll = QScrollArea()
        self._stacked_scroll.setObjectName("scopeStackedScroll")
        self._stacked_scroll.setWidgetResizable(True)
        self._stacked_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._stacked_content = ScopeWorkspaceDropArea(
            drop_handler=self._handle_signal_drop_request
        )
        self._stacked_content.setObjectName("scopeStackedScrollContent")
        self._stacked_layout = QVBoxLayout(self._stacked_content)
        self._stacked_layout.setContentsMargins(8, 8, 8, 8)
        self._stacked_layout.setSpacing(8)
        self._stacked_layout.addStretch()
        self._stacked_scroll.setWidget(self._stacked_content)

        # Overview mini-plot (zoom thumbnail)
        self._overview_inset = QFrame()
        self._overview_inset.setObjectName("scopeOverviewInset")
        self._overview_inset.hide()
        overview_inset_layout = QVBoxLayout(self._overview_inset)
        overview_inset_layout.setContentsMargins(6, 6, 6, 6)
        overview_inset_layout.setSpacing(0)
        self._overview_plot = pg.PlotWidget()
        self._overview_plot.setObjectName("scopeOverviewPlot")
        self._overview_plot.setFixedSize(148, 82)
        self._overview_plot.setMouseEnabled(x=False, y=False)
        self._overview_plot.hideAxis("left")
        self._overview_plot.hideAxis("bottom")
        self._overview_plot.getPlotItem().setMenuEnabled(False)
        self._overview_plot.getPlotItem().hideButtons()
        self._overview_region = pg.LinearRegionItem(movable=False)
        self._overview_region.setZValue(10)
        self._overview_plot.addItem(self._overview_region)
        overview_inset_layout.addWidget(self._overview_plot)

        self._stacked_splitter.addWidget(self._stacked_sidebar)
        self._stacked_splitter.addWidget(self._stacked_scroll)
        self._stacked_splitter.addWidget(self._stacked_right_panel)
        self._stacked_splitter.setCollapsible(0, False)
        self._stacked_splitter.setCollapsible(1, False)
        self._stacked_splitter.setCollapsible(2, False)
        self._stacked_splitter.setStretchFactor(0, 2)
        self._stacked_splitter.setStretchFactor(1, 7)
        self._stacked_splitter.setStretchFactor(2, 2)
        self._stacked_splitter.setSizes([300, 900, 0])
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
        menu_layout.setContentsMargins(9, 3, 9, 3)
        menu_layout.setSpacing(6)

        self._scope_brand_icon = QLabel()
        self._scope_brand_icon.setObjectName("scopeBrandIcon")
        self._scope_brand_icon.setFixedSize(18, 18)
        menu_layout.addWidget(self._scope_brand_icon)
        self._scope_brand_label = QLabel("VirtuScope")
        self._scope_brand_label.setObjectName("scopeBrandLabel")
        menu_layout.addWidget(self._scope_brand_label)
        menu_layout.addSpacing(8)

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

        self._menu_tools_btn = QToolButton()
        self._menu_tools_btn.setObjectName("scopeMenuTextBtn")
        self._menu_tools_btn.setText("Tools")
        self._menu_tools_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_tools_btn)

        self._menu_window_btn = QToolButton()
        self._menu_window_btn.setObjectName("scopeMenuTextBtn")
        self._menu_window_btn.setText("Window")
        self._menu_window_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_window_btn)

        self._menu_help_btn = QToolButton()
        self._menu_help_btn.setObjectName("scopeMenuTextBtn")
        self._menu_help_btn.setText("Help")
        self._menu_help_btn.setAutoRaise(True)
        menu_layout.addWidget(self._menu_help_btn)

        menu_layout.addStretch(1)
        self._scope_version_label = QLabel("SimuScope v1.0")
        self._scope_version_label.setObjectName("scopeVersionLabel")
        menu_layout.addWidget(self._scope_version_label)
        chrome_layout.addWidget(self._scope_menu_row)

        self._scope_tool_row = QWidget()
        self._scope_tool_row.setObjectName("scopeToolbarRow")
        toolbar_layout = QHBoxLayout(self._scope_tool_row)
        toolbar_layout.setContentsMargins(8, 3, 8, 3)
        toolbar_layout.setSpacing(3)

        self._toolbar_run_btn = QToolButton()
        self._toolbar_run_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_run_btn.setProperty("accentTone", "green")
        self._toolbar_run_btn.clicked.connect(self._on_run_requested)
        toolbar_layout.addWidget(self._toolbar_run_btn)

        self._toolbar_pause_btn = QToolButton()
        self._toolbar_pause_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_pause_btn.clicked.connect(self._on_pause_requested)
        toolbar_layout.addWidget(self._toolbar_pause_btn)

        self._toolbar_stop_btn = QToolButton()
        self._toolbar_stop_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_stop_btn.setProperty("accentTone", "red")
        self._toolbar_stop_btn.clicked.connect(self._on_stop_requested)
        toolbar_layout.addWidget(self._toolbar_stop_btn)

        self._toolbar_step_btn = QToolButton()
        self._toolbar_step_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_step_btn.clicked.connect(self._on_step_requested)
        toolbar_layout.addWidget(self._toolbar_step_btn)

        self._toolbar_separator_0 = QFrame()
        self._toolbar_separator_0.setObjectName("scopeToolbarSeparator")
        self._toolbar_separator_0.setFrameShape(QFrame.Shape.VLine)
        self._toolbar_separator_0.setFrameShadow(QFrame.Shadow.Plain)
        toolbar_layout.addWidget(self._toolbar_separator_0)

        self._toolbar_left_btn = QToolButton()
        self._toolbar_left_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_left_btn.setProperty("accentTone", "blue")
        self._toolbar_left_btn.setCheckable(True)
        self._toolbar_left_btn.setChecked(True)
        self._toolbar_left_btn.setToolTip("Toggle signals panel (Ctrl+B)")
        self._toolbar_left_btn.toggled.connect(self._on_toolbar_left_toggled)
        toolbar_layout.addWidget(self._toolbar_left_btn)

        self._toolbar_cursor_btn = QToolButton()
        self._toolbar_cursor_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_cursor_btn.setProperty("accentTone", "green")
        self._toolbar_cursor_btn.setCheckable(True)
        self._toolbar_cursor_btn.setChecked(False)
        self._toolbar_cursor_btn.setToolTip("Enable cursors")
        self._toolbar_cursor_btn.toggled.connect(self._on_toolbar_cursor_toggled)
        toolbar_layout.addWidget(self._toolbar_cursor_btn)

        self._toolbar_grid_btn = QToolButton()
        self._toolbar_grid_btn.setObjectName("scopeToolbarTransportBtn")
        self._toolbar_grid_btn.setProperty("accentTone", "cyan")
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
        self._toolbar_autoscale_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_autoscale_btn.setToolTip("Fit view (AutoScale)")
        self._toolbar_autoscale_btn.clicked.connect(self._on_autoscale_clicked)
        toolbar_layout.addWidget(self._toolbar_autoscale_btn)

        self._toolbar_zoom_in_btn = QToolButton()
        self._toolbar_zoom_in_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_zoom_in_btn.clicked.connect(lambda _checked=False: self._step_slider(self._zoom_slider, 8))
        toolbar_layout.addWidget(self._toolbar_zoom_in_btn)

        self._toolbar_zoom_out_btn = QToolButton()
        self._toolbar_zoom_out_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_zoom_out_btn.clicked.connect(lambda _checked=False: self._step_slider(self._zoom_slider, -8))
        toolbar_layout.addWidget(self._toolbar_zoom_out_btn)

        self._toolbar_measure_btn = QToolButton()
        self._toolbar_measure_btn.setObjectName("scopeToolbarMenuBtn")
        self._toolbar_measure_btn.setToolTip("Measurement columns")
        self._toolbar_measure_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        toolbar_layout.addWidget(self._toolbar_measure_btn)

        self._toolbar_math_btn = QToolButton()
        self._toolbar_math_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_math_btn.setToolTip("Create math signal")
        self._toolbar_math_btn.clicked.connect(self._on_create_math_signal_clicked)
        toolbar_layout.addWidget(self._toolbar_math_btn)

        self._toolbar_fft_btn = QToolButton()
        self._toolbar_fft_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_fft_btn.clicked.connect(lambda _checked=False: self._analysis_tabs.setCurrentIndex(1))
        toolbar_layout.addWidget(self._toolbar_fft_btn)

        self._toolbar_compare_btn = QToolButton()
        self._toolbar_compare_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_compare_btn.clicked.connect(lambda _checked=False: self._analysis_tabs.setCurrentIndex(2))
        toolbar_layout.addWidget(self._toolbar_compare_btn)

        self._toolbar_separator_2 = QFrame()
        self._toolbar_separator_2.setObjectName("scopeToolbarSeparator")
        self._toolbar_separator_2.setFrameShape(QFrame.Shape.VLine)
        self._toolbar_separator_2.setFrameShadow(QFrame.Shadow.Plain)
        toolbar_layout.addWidget(self._toolbar_separator_2)

        self._trace_style_menu_btn.setObjectName("scopeToolbarMenuBtn")
        self._trace_style_menu_btn.setToolTip("Trace style and plot placement")
        self._trace_style_menu_btn.setAutoRaise(False)
        self._trace_style_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        toolbar_layout.addWidget(self._trace_style_menu_btn)

        self._toolbar_copy_btn = QToolButton()
        self._toolbar_copy_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_copy_btn.setToolTip("Copy active plot image")
        self._toolbar_copy_btn.clicked.connect(
            lambda _checked=False: self._copy_plot_to_clipboard(
                self._plot_widgets[0] if self._plot_widgets else None
            )
        )
        toolbar_layout.addWidget(self._toolbar_copy_btn)

        self._toolbar_right_btn = QToolButton()
        self._toolbar_right_btn.setObjectName("scopeToolbarActionBtn")
        self._toolbar_right_btn.setCheckable(True)
        self._toolbar_right_btn.setChecked(True)
        self._toolbar_right_btn.toggled.connect(lambda checked: self._set_right_panel_visible(bool(checked)))
        toolbar_layout.addWidget(self._toolbar_right_btn)

        toolbar_layout.addStretch(1)
        self._toolbar_scope_label = QLabel()
        self._toolbar_scope_label.setObjectName("scopeToolbarScopeBadge")
        self._toolbar_scope_label.setText("No signal")
        toolbar_layout.addWidget(self._toolbar_scope_label)
        chrome_layout.addWidget(self._scope_tool_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self._analysis_tabs = QTabWidget()
        self._analysis_tabs.setObjectName("scopeAnalysisTabs")
        self._analysis_tabs.setDocumentMode(True)
        self._analysis_tabs.currentChanged.connect(self._on_analysis_tab_changed)
        self._analysis_tabs.addTab(self._stacked_page, "Scope")
        self._fft_placeholder = self._build_analysis_placeholder(
            "FFT",
            "Frequency-domain analysis will appear here.",
        )
        self._compare_placeholder = self._build_analysis_placeholder(
            "Compare",
            "Compare traces and runs inside this workspace.",
        )
        self._analysis_tabs.addTab(self._fft_placeholder, "FFT")
        self._analysis_tabs.addTab(self._compare_placeholder, "Compare")

        layout.addWidget(self._scope_toolbar, stretch=0)
        layout.addWidget(self._analysis_tabs, stretch=1)

        self._scope_bottom_controls = QWidget()
        self._scope_bottom_controls.setObjectName("scopeBottomControlBar")
        bottom_layout = QVBoxLayout(self._scope_bottom_controls)
        bottom_layout.setContentsMargins(8, 5, 8, 5)
        bottom_layout.setSpacing(5)

        self._scope_quick_metrics_row = QWidget()
        self._scope_quick_metrics_row.setObjectName("scopeQuickMetricsRow")
        quick_layout = QHBoxLayout(self._scope_quick_metrics_row)
        quick_layout.setContentsMargins(0, 0, 0, 0)
        quick_layout.setSpacing(8)
        self._quick_metric_signal = QLabel("No signal")
        self._quick_metric_signal.setObjectName("scopeQuickMetricPrimary")
        self._quick_metric_rms = QLabel("RMS —")
        self._quick_metric_peak = QLabel("Peak —")
        self._quick_metric_mean = QLabel("Mean —")
        self._quick_metric_dt = QLabel("Δt —")
        self._quick_metric_dv = QLabel("ΔY —")
        for widget in (
            self._quick_metric_signal,
            self._quick_metric_rms,
            self._quick_metric_peak,
            self._quick_metric_mean,
            self._quick_metric_dt,
            self._quick_metric_dv,
        ):
            widget.setObjectName("scopeQuickMetricChip")
            quick_layout.addWidget(widget, stretch=0)
        quick_layout.addStretch(1)
        bottom_layout.addWidget(self._scope_quick_metrics_row, stretch=0)

        self._scope_bottom_viewport_row = QWidget()
        self._scope_bottom_viewport_row.setObjectName("scopeBottomViewportRow")
        viewport_layout = QHBoxLayout(self._scope_bottom_viewport_row)
        viewport_layout.setContentsMargins(0, 0, 0, 0)
        viewport_layout.setSpacing(6)

        viewport_layout.addWidget(QLabel("Timeline"))
        self._timeline_dec_btn = QPushButton("◀")
        self._timeline_dec_btn.setObjectName("scopeSliderStepBtn")
        self._timeline_dec_btn.setFixedWidth(24)
        self._timeline_dec_btn.clicked.connect(lambda: self._step_timeline_window(-20))
        viewport_layout.addWidget(self._timeline_dec_btn)

        self._timeline_slider = TimeRangeSlider()
        self._timeline_slider.setRange(0, 1000)
        self._timeline_slider.setValues(0, 1000)
        self._timeline_slider.rangeChanged.connect(self._on_timeline_slider_changed)
        viewport_layout.addWidget(self._timeline_slider, stretch=4)

        self._timeline_inc_btn = QPushButton("▶")
        self._timeline_inc_btn.setObjectName("scopeSliderStepBtn")
        self._timeline_inc_btn.setFixedWidth(24)
        self._timeline_inc_btn.clicked.connect(lambda: self._step_timeline_window(20))
        viewport_layout.addWidget(self._timeline_inc_btn)

        self._timeline_range_label = QLabel("-- to --")
        self._timeline_range_label.setObjectName("scopeSliderInfoLabel")
        self._timeline_range_label.setMinimumWidth(132)
        viewport_layout.addWidget(self._timeline_range_label)

        viewport_layout.addWidget(QLabel("Zoom"))
        self._zoom_dec_btn = QPushButton("−")
        self._zoom_dec_btn.setObjectName("scopeSliderStepBtn")
        self._zoom_dec_btn.setFixedWidth(24)
        self._zoom_dec_btn.clicked.connect(lambda: self._step_slider(self._zoom_slider, -5))
        viewport_layout.addWidget(self._zoom_dec_btn)

        self._zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self._zoom_slider.setObjectName("scopeZoomSlider")
        self._zoom_slider.setRange(0, 100)
        self._zoom_slider.setValue(0)
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider_changed)
        viewport_layout.addWidget(self._zoom_slider, stretch=3)

        self._zoom_inc_btn = QPushButton("+")
        self._zoom_inc_btn.setObjectName("scopeSliderStepBtn")
        self._zoom_inc_btn.setFixedWidth(24)
        self._zoom_inc_btn.clicked.connect(lambda: self._step_slider(self._zoom_slider, 5))
        viewport_layout.addWidget(self._zoom_inc_btn)

        self._zoom_percent_label = QLabel("0%")
        self._zoom_percent_label.setObjectName("scopeSliderInfoLabel")
        self._zoom_percent_label.setMinimumWidth(34)
        viewport_layout.addWidget(self._zoom_percent_label)

        self._autoscale_btn = QPushButton("AutoScale")
        self._autoscale_btn.clicked.connect(self._on_autoscale_clicked)
        viewport_layout.addWidget(self._autoscale_btn)
        self._measurement_menu_btn = QToolButton()
        self._measurement_menu_btn.setObjectName("scopeMeasurementMenuBtn")
        self._measurement_menu_btn.setText("+ Add Measurement")
        self._measurement_menu_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._measurement_menu_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._measurement_menu = QMenu(self._measurement_menu_btn)
        self._measurement_menu.aboutToShow.connect(self._populate_measurement_menu)
        self._measurement_menu_btn.setMenu(self._measurement_menu)
        self._toolbar_measure_btn.setMenu(self._measurement_menu)
        self._inspector_measure_menu_btn.setMenu(self._measurement_menu)
        viewport_layout.addWidget(self._interval_combo)
        viewport_layout.addWidget(self._measurement_menu_btn)
        bottom_layout.addWidget(self._scope_bottom_viewport_row, stretch=0)

        self._scope_bottom_drawer_header = QWidget()
        self._scope_bottom_drawer_header.setObjectName("scopeBottomDrawerHeader")
        drawer_header_layout = QHBoxLayout(self._scope_bottom_drawer_header)
        drawer_header_layout.setContentsMargins(0, 0, 0, 0)
        drawer_header_layout.setSpacing(8)
        self._scope_bottom_measure_title = QLabel("Analysis Drawer")
        self._scope_bottom_measure_title.setObjectName("scopeBottomMeasureTitle")
        drawer_header_layout.addWidget(self._scope_bottom_measure_title)
        self._scope_bottom_measure_summary = QLabel("Scope: Full Range  |  Δt: —  |  f: —")
        self._scope_bottom_measure_summary.setObjectName("scopeBottomMeasureSummary")
        drawer_header_layout.addWidget(self._scope_bottom_measure_summary)
        drawer_header_layout.addStretch(1)
        self._scope_bottom_measure_mode = QLabel("Sample based")
        self._scope_bottom_measure_mode.setObjectName("scopeBottomMeasureMode")
        drawer_header_layout.addWidget(self._scope_bottom_measure_mode)
        self._scope_bottom_drawer_toggle_btn = QToolButton()
        self._scope_bottom_drawer_toggle_btn.setObjectName("scopeBottomDrawerToggleBtn")
        self._scope_bottom_drawer_toggle_btn.setCheckable(True)
        self._scope_bottom_drawer_toggle_btn.setChecked(self._bottom_drawer_expanded)
        self._scope_bottom_drawer_toggle_btn.setText("Expand")
        self._scope_bottom_drawer_toggle_btn.toggled.connect(self._on_bottom_drawer_toggled)
        drawer_header_layout.addWidget(self._scope_bottom_drawer_toggle_btn)
        bottom_layout.addWidget(self._scope_bottom_drawer_header, stretch=0)

        self._scope_bottom_tab = QWidget()
        self._scope_bottom_tab.setObjectName("scopeBottomDrawerBody")
        drawer_layout = QVBoxLayout(self._scope_bottom_tab)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.setSpacing(4)

        self._scope_bottom_tabs = QTabWidget()
        self._scope_bottom_tabs.setObjectName("scopeBottomTabs")
        self._scope_bottom_tabs.currentChanged.connect(self._on_bottom_tab_changed)

        measurements_page = QWidget()
        measure_layout = QVBoxLayout(measurements_page)
        measure_layout.setContentsMargins(0, 0, 0, 0)
        measure_layout.setSpacing(4)

        self._scope_bottom_measure_table = QTableWidget(0, 0)
        self._scope_bottom_measure_table.setObjectName("scopeBottomMeasureTable")
        self._scope_bottom_measure_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._scope_bottom_measure_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._scope_bottom_measure_table.setAlternatingRowColors(True)
        self._scope_bottom_measure_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._scope_bottom_measure_table.horizontalHeader().setMinimumSectionSize(54)
        self._scope_bottom_measure_table.horizontalHeader().setDefaultSectionSize(84)
        self._scope_bottom_measure_table.horizontalHeader().setFixedHeight(20)
        self._scope_bottom_measure_table.verticalHeader().setVisible(False)
        self._scope_bottom_measure_table.setShowGrid(True)
        self._scope_bottom_measure_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scope_bottom_measure_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scope_bottom_measure_table.setMinimumHeight(86)
        self._scope_bottom_measure_table.setMaximumHeight(180)
        measure_layout.addWidget(self._scope_bottom_measure_table)
        self._scope_bottom_tabs.addTab(measurements_page, "Measurements")

        self._scope_bottom_events = QListWidget()
        self._scope_bottom_events.setObjectName("scopeBottomEventsList")
        self._scope_bottom_tabs.addTab(self._scope_bottom_events, "Events")

        self._scope_bottom_console = QPlainTextEdit()
        self._scope_bottom_console.setObjectName("scopeBottomConsole")
        self._scope_bottom_console.setReadOnly(True)
        self._scope_bottom_tabs.addTab(self._scope_bottom_console, "Console")

        drawer_layout.addWidget(self._scope_bottom_tabs)
        bottom_layout.addWidget(self._scope_bottom_tab, stretch=1)

        self._scope_status_bar = QWidget()
        self._scope_status_bar.setObjectName("scopeStatusBar")
        status_layout = QHBoxLayout(self._scope_status_bar)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)
        self._scope_status_state = QLabel("Ready")
        self._scope_status_state.setObjectName("scopeStatusLabel")
        self._scope_status_mode = QLabel("Transient Mode")
        self._scope_status_mode.setObjectName("scopeStatusLabel")
        self._scope_status_rate = QLabel("Sample rate: —")
        self._scope_status_rate.setObjectName("scopeStatusLabel")
        self._scope_status_cursor = QLabel("Δt —  ΔY —")
        self._scope_status_cursor.setObjectName("scopeStatusLabel")
        for widget in (
            self._scope_status_state,
            self._scope_status_mode,
            self._scope_status_rate,
            self._scope_status_cursor,
        ):
            status_layout.addWidget(widget, stretch=0)
        status_layout.addStretch(1)
        bottom_layout.addWidget(self._scope_status_bar, stretch=0)

        layout.addWidget(self._scope_bottom_controls, stretch=0)
        self._scope_bottom_controls.setVisible(True)
        self._scope_bottom_tab.setVisible(self._bottom_drawer_expanded)

        self._mapping_label.setVisible(False)
        self._message_label.setVisible(False)

        self._set_stacked_cursor_enabled(False)
        self._apply_stacked_trace_colors()
        self._sync_trace_style_controls()
        self._build_scope_actions()
        self._build_scope_menus()
        self._on_bottom_drawer_toggled(False)
        self._apply_panel_visibility()
        self._refresh_inspector()
        self._refresh_quick_metrics()
        self._refresh_status_bar()

        self._refresh_title()
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)
        else:
            self.apply_theme(LIGHT_THEME)

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
            "interval_target": normalize_interval_target(self._stacked_interval_target),
            "signal_axis_targets": dict(self._signal_axis_targets),
            "signal_labels": dict(self._signal_labels),
            "bottom_drawer_expanded": bool(self._bottom_drawer_expanded),
            "bottom_drawer_tab": int(self._bottom_drawer_active_tab),
            "analysis_tab_index": int(self._analysis_tabs.currentIndex()),
            "inspector_snap_mode": str(self._inspector_snap_mode),
            "simulation_state": str(self._simulation_state),
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
            self._right_panel_visible = right_visible_raw

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

        signal_axis_targets_raw = state.get("signal_axis_targets")
        if isinstance(signal_axis_targets_raw, dict):
            self._signal_axis_targets = {
                str(signal_name): str(target)
                for signal_name, target in signal_axis_targets_raw.items()
                if str(signal_name).strip() and str(target).strip()
            }

        signal_labels_raw = state.get("signal_labels")
        if isinstance(signal_labels_raw, dict):
            self._signal_labels = {
                str(signal_name): str(label)
                for signal_name, label in signal_labels_raw.items()
                if str(signal_name).strip() and str(label).strip()
            }

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

        interval_target_raw = state.get("interval_target")
        if isinstance(interval_target_raw, str) and interval_target_raw.strip():
            combo_idx = self._interval_combo.findData(
                normalize_interval_target(interval_target_raw.strip())
            )
            if combo_idx >= 0:
                self._interval_combo.setCurrentIndex(combo_idx)

        drawer_expanded_raw = state.get("bottom_drawer_expanded")
        if isinstance(drawer_expanded_raw, bool):
            self._on_bottom_drawer_toggled(drawer_expanded_raw)

        drawer_tab_raw = state.get("bottom_drawer_tab")
        if isinstance(drawer_tab_raw, int):
            self._scope_bottom_tabs.setCurrentIndex(max(0, drawer_tab_raw))

        analysis_tab_raw = state.get("analysis_tab_index")
        if isinstance(analysis_tab_raw, int):
            self._analysis_tabs.setCurrentIndex(max(0, analysis_tab_raw))

        snap_mode_raw = state.get("inspector_snap_mode")
        if isinstance(snap_mode_raw, str) and snap_mode_raw.strip():
            snap_index = self._inspector_snap_combo.findData(snap_mode_raw.strip())
            if snap_index >= 0:
                self._inspector_snap_combo.setCurrentIndex(snap_index)

        simulation_state_raw = state.get("simulation_state")
        if isinstance(simulation_state_raw, str) and simulation_state_raw.strip():
            self._simulation_state = simulation_state_raw.strip().lower()

        self._apply_panel_visibility()
        self._sync_scope_action_states()

        if self._stacked_signals:
            self._sync_plot_groups()
            if self._stacked_active_signal not in self._stacked_signals:
                self._stacked_active_signal = next(iter(self._stacked_signals))
            self._sync_scope_selector()
            self._refresh_signal_list_metadata()
            self._sync_trace_style_controls()
            self._rebuild_stacked_plots(self._current_result)
            self._update_stacked_measurements()
            self._refresh_inspector()

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
            self._toolbar_scope_label.setText(
                self._display_signal_name(active or (self._component_name or label))
            )

    def _display_signal_name(self, signal_name: str | None) -> str:
        """Return the current UI label for one signal."""
        text = str(signal_name or "").strip()
        if not text:
            return "No signal"
        return self._signal_labels.get(text, text)

    def _measurement_scope_label(self) -> str:
        target = normalize_interval_target(self._stacked_interval_target)
        return {
            "full": "Full Range",
            "window": "Visible Window",
            "a_to_b": "Between Cursors",
        }.get(target, "Full Range")

    def _current_visible_time_window(self) -> tuple[float, float] | None:
        """Return the currently visible horizontal time range."""
        if not self._plot_widgets or len(self._stacked_time) < 2:
            return None
        x_range = self._plot_widgets[0].getPlotItem().getViewBox().viewRange()[0]
        start = float(x_range[0])
        end = float(x_range[1])
        if end < start:
            start, end = end, start
        t_min = float(self._stacked_time[0])
        t_max = float(self._stacked_time[-1])
        start = min(max(start, t_min), t_max)
        end = min(max(end, t_min), t_max)
        return (start, end)

    def _measurement_scope_bounds(self) -> tuple[float, float] | None:
        """Resolve the active measurement bounds in seconds."""
        if len(self._stacked_time) < 1:
            return None

        target = normalize_interval_target(self._stacked_interval_target)
        if target == "full":
            return (float(self._stacked_time[0]), float(self._stacked_time[-1]))
        if target == "window":
            return self._current_visible_time_window() or (
                float(self._stacked_time[0]),
                float(self._stacked_time[-1]),
            )
        if target == "a_to_b":
            if not self._stacked_cursors_enabled:
                return None
            start = float(min(self._c1_spin.value(), self._c2_spin.value()))
            end = float(max(self._c1_spin.value(), self._c2_spin.value()))
            if abs(end - start) < 1e-15:
                return None
            return (start, end)
        return (float(self._stacked_time[0]), float(self._stacked_time[-1]))

    def _measurement_subset(
        self,
        values: np.ndarray,
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        """Return the active measurement subset for one signal array."""
        bounds = self._measurement_scope_bounds()
        if bounds is None or len(self._stacked_time) != len(values):
            return None, None
        start, end = bounds
        if end < start:
            start, end = end, start

        if normalize_interval_target(self._stacked_interval_target) == "full":
            return self._stacked_time, values

        left = int(np.searchsorted(self._stacked_time, start, side="left"))
        right = int(np.searchsorted(self._stacked_time, end, side="right"))
        left = max(0, min(left, len(self._stacked_time)))
        right = max(left, min(right, len(self._stacked_time)))
        if right <= left:
            return None, None
        return self._stacked_time[left:right], values[left:right]

    @staticmethod
    def _calculate_measurement_stats(values: np.ndarray | None) -> dict[str, float | None]:
        """Compute deterministic statistics for one measurement subset."""
        if values is None or len(values) == 0:
            return {
                "min": None,
                "max": None,
                "mean": None,
                "rms": None,
                "pkpk": None,
            }
        min_val = float(np.min(values))
        max_val = float(np.max(values))
        mean_val = float(np.mean(values))
        rms_val = float(np.sqrt(np.mean(values ** 2)))
        return {
            "min": min_val,
            "max": max_val,
            "mean": mean_val,
            "rms": rms_val,
            "pkpk": max_val - min_val,
        }

    def _axis_badge_text(self, signal_name: str) -> str:
        target = self._signal_axis_targets.get(signal_name, "left")
        return {
            "left": "L",
            "right": "R",
            "new_plot": "P",
        }.get(target, "L")

    def _create_inspector_section(self, title: str, body: QWidget) -> QFrame:
        """Create one collapsible inspector section."""
        section = QFrame()
        section.setObjectName("scopeInspectorSection")
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(0)

        header_btn = QToolButton()
        header_btn.setObjectName("scopeInspectorSectionBtn")
        header_btn.setText(title)
        header_btn.setCheckable(True)
        header_btn.setChecked(True)
        header_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        header_btn.setArrowType(Qt.ArrowType.DownArrow)

        def _on_toggled(checked: bool) -> None:
            body.setVisible(bool(checked))
            header_btn.setArrowType(
                Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
            )

        header_btn.toggled.connect(_on_toggled)
        section_layout.addWidget(header_btn)

        body_container = QWidget()
        body_container.setObjectName("scopeInspectorSectionBody")
        body_layout = QVBoxLayout(body_container)
        body_layout.setContentsMargins(10, 8, 10, 10)
        body_layout.setSpacing(0)
        body_layout.addWidget(body)
        section_layout.addWidget(body_container)
        return section

    def _build_analysis_placeholder(self, title: str, subtitle: str) -> QWidget:
        """Create a lightweight placeholder for non-scope analysis tabs."""
        page = QWidget()
        page.setObjectName("scopeAnalysisPlaceholder")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(6)
        title_label = QLabel(title)
        title_label.setObjectName("scopePlaceholderTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("scopePlaceholderSubtitle")
        subtitle_label.setWordWrap(True)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addStretch(1)
        return page

    @staticmethod
    def _compose_scope_action_tooltip(
        title: str,
        description: str = "",
        shortcut: str | None = None,
    ) -> str:
        lines = [title]
        text = str(description or "").strip()
        if text:
            lines.append(text)
        shortcut_text = str(shortcut or "").strip()
        if shortcut_text:
            lines.append(f"Shortcut: {shortcut_text}")
        return "\n".join(lines)

    def _register_scope_action(
        self,
        key: str,
        text: str,
        handler: Callable[[bool], None] | Callable[[], None],
        *,
        shortcut: str | None = None,
        description: str = "",
        checkable: bool = False,
        checked: bool = False,
        enabled: bool = True,
    ) -> QAction:
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutVisibleInContextMenu(True)
        action.setCheckable(checkable)
        if checkable:
            action.setChecked(bool(checked))
        action.setEnabled(bool(enabled))
        tooltip = self._compose_scope_action_tooltip(text, description, shortcut)
        action.setToolTip(tooltip)
        action.setStatusTip(description or text)
        action.triggered.connect(handler)  # type: ignore[arg-type]
        self.addAction(action)
        self._scope_actions[key] = action
        return action

    def _build_scope_actions(self) -> None:
        """Create reusable QAction objects for menus, shortcuts, and toolbar state."""
        if self._scope_actions:
            return

        self._register_scope_action(
            "run",
            "Run",
            self._on_run_requested,
            shortcut="Space",
            description="Start or resume the simulation context for this scope",
        )
        self._register_scope_action(
            "pause",
            "Pause",
            self._on_pause_requested,
            description="Pause the active simulation context",
            enabled=False,
        )
        self._register_scope_action(
            "stop",
            "Stop",
            self._on_stop_requested,
            shortcut="S",
            description="Stop the active simulation context",
            enabled=False,
        )
        self._register_scope_action(
            "step",
            "Step",
            self._on_step_requested,
            description="Advance one deterministic analysis step",
            enabled=False,
        )
        self._register_scope_action(
            "zoom_in",
            "Zoom In",
            lambda _checked=False: self._step_slider(self._zoom_slider, 8),
            description="Tighten the visible time window",
        )
        self._register_scope_action(
            "zoom_out",
            "Zoom Out",
            lambda _checked=False: self._step_slider(self._zoom_slider, -8),
            description="Expand the visible time window",
        )
        self._register_scope_action(
            "fit_view",
            "Fit View",
            lambda _checked=False: self._on_autoscale_clicked(),
            shortcut="F",
            description="Fit the current plot view to the full data range",
        )
        self._register_scope_action(
            "toggle_signals_panel",
            "Toggle Signals Panel",
            lambda checked: self._on_toggle_left_panel_clicked(bool(checked)),
            shortcut="Ctrl+B",
            description="Show or hide the left signals panel",
            checkable=True,
            checked=self._left_panel_visible,
        )
        self._register_scope_action(
            "toggle_inspector",
            "Toggle Inspector",
            lambda checked: self._set_right_panel_visible(bool(checked)),
            description="Show or hide the right inspector panel",
            checkable=True,
            checked=self._right_panel_visible,
        )
        self._register_scope_action(
            "toggle_grid",
            "Toggle Grid",
            lambda checked: self._on_stacked_grid_toggled(bool(checked)),
            shortcut="G",
            description="Show or hide the plot grid",
            checkable=True,
            checked=self._stacked_grid_enabled,
        )
        self._register_scope_action(
            "toggle_cursors",
            "Cursor Tool",
            lambda checked: self._on_stacked_cursor_toggled(bool(checked)),
            shortcut="C",
            description="Enable or disable the analysis cursors",
            checkable=True,
            checked=self._stacked_cursors_enabled,
        )
        self._register_scope_action(
            "toggle_measurements",
            "Measurements",
            lambda checked: self._on_bottom_drawer_toggled(bool(checked)),
            shortcut="M",
            description="Expand or collapse the detailed measurements drawer",
            checkable=True,
            checked=self._bottom_drawer_expanded,
        )
        self._register_scope_action(
            "add_expression",
            "Add Expression",
            lambda _checked=False: self._on_create_math_signal_clicked(),
            shortcut="Ctrl+E",
            description="Create a derived math trace from existing signals",
        )
        self._register_scope_action(
            "show_fft_tab",
            "FFT",
            lambda _checked=False: self._analysis_tabs.setCurrentIndex(1),
            description="Switch to FFT analysis mode",
        )
        self._register_scope_action(
            "show_compare_tab",
            "Compare",
            lambda _checked=False: self._analysis_tabs.setCurrentIndex(2),
            description="Switch to run or trace comparison mode",
        )
        self._register_scope_action(
            "split_view",
            "Split View",
            lambda _checked=False: self._split_all_plot_groups(),
            description="Split visible traces into dedicated plots",
        )
        self._register_scope_action(
            "export_snapshot",
            "Export Snapshot",
            lambda _checked=False: self._copy_plot_to_clipboard(
                self._plot_widgets[0] if self._plot_widgets else None
            ),
            shortcut="Ctrl+Shift+E",
            description="Copy the active plot as an image",
        )
        self._register_scope_action(
            "reset_layout",
            "Reset Layout",
            lambda _checked=False: self._reset_scope_layout(),
            description="Restore the default scope panel layout",
        )
        self._register_scope_action(
            "show_shortcuts",
            "Shortcuts",
            lambda _checked=False: self._show_scope_shortcuts(),
            description="Open the scope shortcut reference",
        )
        self._register_scope_action(
            "show_about",
            "About",
            lambda _checked=False: self._show_scope_about(),
            description="Open information about the scope workspace",
        )
        self._sync_scope_action_states()

    def _build_scope_menus(self) -> None:
        """Attach popup menus to the compact scope menu buttons."""
        self._file_menu = QMenu(self)
        self._file_menu.addAction("Save Session", lambda: self._log_scope_event("Session saved"))
        self._file_menu.addAction(self._scope_actions["export_snapshot"])
        self._file_menu.addAction(
            "Export Measurements",
            lambda: self._log_scope_event("Measurements exported"),
        )

        self._view_menu = QMenu(self)
        self._view_menu.addAction(self._scope_actions["toggle_signals_panel"])
        self._view_menu.addAction(self._scope_actions["toggle_inspector"])
        self._view_menu.addAction(self._scope_actions["toggle_measurements"])
        self._view_menu.addAction(self._scope_actions["toggle_grid"])
        self._view_menu.addSeparator()
        self._view_menu.addAction(self._scope_actions["fit_view"])
        self._view_menu.addAction(self._scope_actions["reset_layout"])

        self._simulation_menu = QMenu(self)
        self._simulation_menu.addAction(self._scope_actions["run"])
        self._simulation_menu.addAction(self._scope_actions["pause"])
        self._simulation_menu.addAction(self._scope_actions["stop"])
        self._simulation_menu.addAction(self._scope_actions["step"])

        self._tools_menu = QMenu(self)
        self._tools_menu.addAction(self._scope_actions["toggle_cursors"])
        self._tools_menu.addAction(self._scope_actions["toggle_measurements"])
        self._tools_menu.addAction(self._scope_actions["add_expression"])
        self._tools_menu.addSeparator()
        self._tools_menu.addAction(self._scope_actions["show_fft_tab"])
        self._tools_menu.addAction(self._scope_actions["show_compare_tab"])

        self._window_menu = QMenu(self)
        self._window_menu.addAction("Scope", lambda: self._analysis_tabs.setCurrentIndex(0))
        self._window_menu.addAction(self._scope_actions["show_fft_tab"])
        self._window_menu.addAction(self._scope_actions["show_compare_tab"])
        self._window_menu.addSeparator()
        self._window_menu.addAction(self._scope_actions["split_view"])
        self._window_menu.addAction(self._scope_actions["reset_layout"])

        self._help_menu = QMenu(self)
        self._help_menu.addAction(self._scope_actions["show_shortcuts"])
        self._help_menu.addAction(self._scope_actions["show_about"])

        menu_map = {
            self._menu_file_btn: self._file_menu,
            self._menu_view_btn: self._view_menu,
            self._menu_sim_btn: self._simulation_menu,
            self._menu_tools_btn: self._tools_menu,
            self._menu_window_btn: self._window_menu,
            self._menu_help_btn: self._help_menu,
        }
        for button, menu in menu_map.items():
            button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            button.setMenu(menu)

    def _show_scope_shortcuts(self) -> None:
        """Display a compact shortcuts help dialog."""
        QMessageBox.information(
            self,
            "Scope Shortcuts",
            "Space: Run/Pause\nS: Stop\nF: Fit\nC: Toggle cursors\nM: Measurements\nG: Grid\nCtrl+B: Toggle sidebar",
        )

    def _show_scope_about(self) -> None:
        """Display scope workbench information."""
        QMessageBox.information(
            self,
            "About Scope Workbench",
            "Standalone professional scope workspace for PulsimGui.",
        )

    def _set_simulation_state(self, state: str) -> None:
        """Persist the lightweight local simulation state used by the scope chrome."""
        value = str(state or "").strip().lower() or "ready"
        if value not in {"ready", "running", "paused", "stopped", "error"}:
            value = "ready"
        self._simulation_state = value
        self._apply_toolbar_icons()
        self._sync_scope_action_states()
        self._refresh_status_bar()

    def _on_run_requested(self, _checked: bool = False) -> None:
        self._set_simulation_state("running")
        self._log_scope_event("Run requested")

    def _on_pause_requested(self, _checked: bool = False) -> None:
        if self._simulation_state != "running":
            return
        self._set_simulation_state("paused")
        self._log_scope_event("Pause requested")

    def _on_stop_requested(self, _checked: bool = False) -> None:
        if self._simulation_state not in {"running", "paused"}:
            return
        self._set_simulation_state("stopped")
        self._log_scope_event("Stop requested")

    def _on_step_requested(self, _checked: bool = False) -> None:
        if len(self._stacked_time) < 2:
            return
        self._set_simulation_state("paused")
        self._log_scope_event("Single step requested")

    def _reset_scope_layout(self) -> None:
        """Restore the default panel and drawer layout."""
        self._left_panel_visible = True
        self._right_panel_visible = True
        self._left_panel_width = 300
        self._right_panel_width = 300
        self._bottom_drawer_expanded = False
        self._scope_bottom_drawer_toggle_btn.blockSignals(True)
        self._scope_bottom_drawer_toggle_btn.setChecked(False)
        self._scope_bottom_drawer_toggle_btn.blockSignals(False)
        self._scope_bottom_tab.setVisible(False)
        self._apply_panel_visibility()

    def _set_right_panel_visible(self, visible: bool) -> None:
        """Set right inspector visibility and sync the toggle button."""
        self._right_panel_visible = bool(visible)
        self._right_panel_toggle_btn.blockSignals(True)
        self._right_panel_toggle_btn.setChecked(bool(visible))
        self._right_panel_toggle_btn.blockSignals(False)
        self._apply_panel_visibility()

    def _log_scope_event(self, message: str) -> None:
        """Append one message to the Events and Console drawer tabs."""
        text = str(message or "").strip()
        if not text:
            return
        self._bottom_events.append(text)
        if hasattr(self, "_scope_bottom_events"):
            self._scope_bottom_events.addItem(text)
        if hasattr(self, "_scope_bottom_console"):
            self._scope_bottom_console.appendPlainText(text)

    def _refresh_signal_list_metadata(self) -> None:
        """Push current label and axis metadata into the left signal list."""
        if not hasattr(self, "_stacked_signal_list"):
            return
        for signal_name in self._stacked_signals:
            self._stacked_signal_list.set_signal_label(
                signal_name,
                self._display_signal_name(signal_name),
            )
            self._stacked_signal_list.set_signal_axis_badge(
                signal_name,
                self._axis_badge_text(signal_name),
            )

    def _refresh_inspector(self) -> None:
        """Synchronize right inspector widgets from current selection/state."""
        signal_name = self._selected_trace_signal() or self._stacked_active_signal
        enabled = signal_name in self._stacked_signals

        self._trace_alias_edit.blockSignals(True)
        self._trace_alias_edit.setText(self._signal_labels.get(signal_name or "", ""))
        self._trace_alias_edit.blockSignals(False)
        self._trace_alias_edit.setEnabled(enabled)

        self._inspector_visible_toggle.blockSignals(True)
        self._inspector_visible_toggle.setChecked(
            bool(enabled and signal_name in self._stacked_signal_list.get_visible_signals())
        )
        self._inspector_visible_toggle.blockSignals(False)
        self._inspector_visible_toggle.setEnabled(enabled)

        axis_target = self._signal_axis_targets.get(signal_name or "", "left")
        axis_index = self._inspector_axis_combo.findData(axis_target)
        self._inspector_axis_combo.blockSignals(True)
        if axis_index >= 0:
            self._inspector_axis_combo.setCurrentIndex(axis_index)
        self._inspector_axis_combo.blockSignals(False)
        self._inspector_axis_combo.setEnabled(enabled)

        interval_index = self._inspector_interval_combo.findData(self._stacked_interval_target)
        self._inspector_interval_combo.blockSignals(True)
        if interval_index >= 0:
            self._inspector_interval_combo.setCurrentIndex(interval_index)
        self._inspector_interval_combo.blockSignals(False)

        snap_index = self._inspector_snap_combo.findData(self._inspector_snap_mode)
        self._inspector_snap_combo.blockSignals(True)
        if snap_index >= 0:
            self._inspector_snap_combo.setCurrentIndex(snap_index)
        self._inspector_snap_combo.blockSignals(False)

        if enabled and signal_name:
            stats = self._stacked_signal_stats.get(signal_name)
            if stats is not None:
                self._inspector_min_spin.setValue(float(stats.get("min", 0.0)))
                self._inspector_max_spin.setValue(float(stats.get("max", 0.0)))
        self._sync_scope_action_states()

    def _refresh_quick_metrics(self) -> None:
        """Update compact bottom readouts for the active trace and cursor state."""
        signal_name = self._stacked_active_signal
        if signal_name not in self._stacked_signals:
            self._quick_metric_signal.setText("No signal")
            self._quick_metric_rms.setText("RMS —")
            self._quick_metric_peak.setText("Peak —")
            self._quick_metric_mean.setText("Mean —")
            self._quick_metric_dt.setText("Δt —")
            self._quick_metric_dv.setText("ΔY —")
            return

        _subset_time, subset_values = self._measurement_subset(self._stacked_signals[signal_name])
        stats = self._calculate_measurement_stats(subset_values)
        self._quick_metric_signal.setText(
            f"{self._display_signal_name(signal_name)}  •  {self._measurement_scope_label()}"
        )
        self._quick_metric_rms.setText(
            f"RMS {self._format_measurement_value(stats.get('rms'))}"
        )
        self._quick_metric_peak.setText(
            f"Peak {self._format_measurement_value(stats.get('max'))}"
        )
        self._quick_metric_mean.setText(
            f"Mean {self._format_measurement_value(stats.get('mean'))}"
        )

        dt_text = "—"
        dv_text = "—"
        if self._stacked_cursors_enabled:
            dt = self._c2_spin.value() - self._c1_spin.value()
            dt_text = self._format_time_display(abs(dt))
            values = self._stacked_signals.get(signal_name)
            if values is not None:
                v1 = self._interpolate_stacked_value(self._c1_spin.value(), values)
                v2 = self._interpolate_stacked_value(self._c2_spin.value(), values)
                if v1 is not None and v2 is not None:
                    dv_text = self._format_measurement_value(v2 - v1)
        self._quick_metric_dt.setText(f"Δt {dt_text}")
        self._quick_metric_dv.setText(f"ΔY {dv_text}")

    def _estimate_sample_rate_text(self) -> str:
        """Return a compact sample-rate label derived from current timebase."""
        if len(self._stacked_time) < 2:
            return "Sample rate: —"
        dt = float(self._stacked_time[1] - self._stacked_time[0])
        if abs(dt) < 1e-18:
            return "Sample rate: —"
        sample_rate = abs(1.0 / dt)
        if sample_rate >= 1e6:
            return f"Sample rate: {sample_rate/1e6:.3g} MHz"
        if sample_rate >= 1e3:
            return f"Sample rate: {sample_rate/1e3:.3g} kHz"
        return f"Sample rate: {sample_rate:.4g} Hz"

    def _refresh_status_bar(self) -> None:
        """Update the compact status bar readout."""
        tab_label = self._analysis_tabs.tabText(self._analysis_tabs.currentIndex())
        self._scope_status_state.setText(self._simulation_state.title())
        self._scope_status_mode.setText(f"{tab_label} Mode")
        self._scope_status_rate.setText(self._estimate_sample_rate_text())
        if self._stacked_cursors_enabled:
            signal_name = self._stacked_active_signal
            dv_text = "—"
            if signal_name in self._stacked_signals:
                values = self._stacked_signals[signal_name]
                v1 = self._interpolate_stacked_value(self._c1_spin.value(), values)
                v2 = self._interpolate_stacked_value(self._c2_spin.value(), values)
                if v1 is not None and v2 is not None:
                    dv_text = self._format_measurement_value(v2 - v1)
            self._scope_status_cursor.setText(
                f"X1 {self._format_time_display(self._c1_spin.value())}   "
                f"X2 {self._format_time_display(self._c2_spin.value())}   "
                f"Δt {self._format_time_display(abs(self._c2_spin.value() - self._c1_spin.value()))}   "
                f"ΔY {dv_text}"
            )
        else:
            self._scope_status_cursor.setText("Δt —   ΔY —")

    def _on_analysis_tab_changed(self, index: int) -> None:
        """Track active analysis tab changes."""
        if not hasattr(self, "_scope_status_state"):
            return
        self._bottom_drawer_active_tab = max(self._bottom_drawer_active_tab, 0)
        if index >= 0:
            self._log_scope_event(f"Analysis tab changed to {self._analysis_tabs.tabText(index)}")
        self._sync_scope_action_states()
        self._refresh_status_bar()

    def _on_bottom_drawer_toggled(self, checked: bool) -> None:
        """Expand or collapse the detailed bottom drawer."""
        self._bottom_drawer_expanded = bool(checked)
        self._scope_bottom_tab.setVisible(bool(checked))
        self._scope_bottom_drawer_toggle_btn.blockSignals(True)
        self._scope_bottom_drawer_toggle_btn.setChecked(bool(checked))
        self._scope_bottom_drawer_toggle_btn.blockSignals(False)
        self._scope_bottom_drawer_toggle_btn.setText("Collapse" if checked else "Expand")
        self._sync_scope_action_states()

    def _on_bottom_tab_changed(self, index: int) -> None:
        """Persist last active drawer tab."""
        self._bottom_drawer_active_tab = int(max(0, index))

    def _on_inspector_visible_toggled(self, checked: bool) -> None:
        """Toggle the active signal visibility from the inspector."""
        signal_name = self._selected_trace_signal() or self._stacked_active_signal
        if not signal_name or signal_name not in self._stacked_signals:
            return
        self._stacked_signal_list.set_signal_visible(signal_name, bool(checked))
        self._on_stacked_signal_visibility_changed(signal_name, bool(checked))

    def _set_signal_alias(self, signal_name: str, alias: str | None) -> None:
        """Store an optional display alias and refresh all synchronized surfaces."""
        if signal_name not in self._stacked_signals:
            return
        text = str(alias or "").strip()
        if not text or text == signal_name:
            self._signal_labels.pop(signal_name, None)
        else:
            self._signal_labels[signal_name] = text
        self._refresh_signal_list_metadata()
        self._sync_scope_selector()
        self._refresh_inspector()
        self._update_stacked_measurements()
        self._rebuild_stacked_plots(self._current_result)

    def _on_trace_alias_edited(self) -> None:
        """Apply alias edits from the inspector trace section."""
        signal_name = self._selected_trace_signal() or self._stacked_active_signal
        if not signal_name or signal_name not in self._stacked_signals:
            return
        self._set_signal_alias(signal_name, self._trace_alias_edit.text())

    def _set_signal_axis_target(self, signal_name: str, target: str) -> None:
        """Set one signal axis target and refresh dependent UI."""
        if signal_name not in self._stacked_signals:
            return
        normalized = str(target or "left").strip().lower() or "left"
        if normalized not in {"left", "right", "new_plot"}:
            normalized = "left"
        self._signal_axis_targets[signal_name] = normalized
        if normalized == "new_plot":
            self._set_signal_plot_group(signal_name, signal_name)
        self._refresh_signal_list_metadata()
        self._refresh_inspector()
        self._rebuild_stacked_plots(self._current_result)

    def _cycle_signal_axis_target(self, signal_name: str) -> None:
        """Rotate axis assignment between left, right, and dedicated plot."""
        order = ("left", "right", "new_plot")
        current = self._signal_axis_targets.get(signal_name, "left")
        try:
            next_index = (order.index(current) + 1) % len(order)
        except ValueError:
            next_index = 0
        self._set_signal_axis_target(signal_name, order[next_index])

    def _on_signal_axis_badge_clicked(self, signal_name: str) -> None:
        """Handle direct axis badge interaction from the signals panel."""
        if signal_name not in self._stacked_signals:
            return
        self._on_stacked_signal_selected(signal_name)
        self._cycle_signal_axis_target(signal_name)

    def _on_inspector_axis_changed(self) -> None:
        """Apply a new axis/placement assignment to the active signal."""
        signal_name = self._selected_trace_signal() or self._stacked_active_signal
        if not signal_name or signal_name not in self._stacked_signals:
            return
        target = str(self._inspector_axis_combo.currentData() or "left")
        self._set_signal_axis_target(signal_name, target)

    def _on_inspector_snap_mode_changed(self) -> None:
        """Persist snap mode selection for future cursor interactions."""
        self._inspector_snap_mode = str(self._inspector_snap_combo.currentData() or "none")
        self._refresh_inspector()

    def _on_inspector_interval_changed(self) -> None:
        """Keep bottom and inspector interval selectors synchronized."""
        target = self._inspector_interval_combo.currentData()
        index = self._interval_combo.findData(target)
        if index >= 0 and self._interval_combo.currentIndex() != index:
            self._interval_combo.blockSignals(True)
            self._interval_combo.setCurrentIndex(index)
            self._interval_combo.blockSignals(False)
        self._on_interval_target_changed(self._inspector_interval_combo.currentText())

    def _sync_scope_action_states(self) -> None:
        """Keep shared QAction state aligned with current workspace state."""
        if not self._scope_actions:
            return

        has_data = len(self._stacked_time) > 1 and bool(self._stacked_signals)
        has_selection = bool(self._selected_trace_signal() or self._stacked_active_signal)
        running = self._simulation_state == "running"
        paused = self._simulation_state == "paused"

        check_states = {
            "toggle_signals_panel": self._left_panel_visible,
            "toggle_inspector": self._right_panel_visible,
            "toggle_grid": self._stacked_grid_enabled,
            "toggle_cursors": self._stacked_cursors_enabled,
            "toggle_measurements": self._bottom_drawer_expanded,
        }
        for key, checked in check_states.items():
            action = self._scope_actions.get(key)
            if action is None:
                continue
            action.blockSignals(True)
            action.setChecked(bool(checked))
            action.blockSignals(False)

        enabled_states = {
            "run": True,
            "pause": running,
            "stop": running or paused,
            "step": has_data and not running,
            "zoom_in": has_data,
            "zoom_out": has_data,
            "fit_view": has_data,
            "toggle_grid": has_data,
            "toggle_cursors": has_data,
            "toggle_measurements": has_data,
            "add_expression": bool(self._stacked_signals),
            "show_fft_tab": bool(self._stacked_signals),
            "show_compare_tab": bool(self._stacked_signals),
            "split_view": has_data,
            "export_snapshot": has_data,
            "toggle_signals_panel": True,
            "toggle_inspector": True,
            "reset_layout": True,
            "show_shortcuts": True,
            "show_about": True,
        }
        for key, enabled in enabled_states.items():
            action = self._scope_actions.get(key)
            if action is not None:
                action.setEnabled(bool(enabled))

        button_map = {
            "run": getattr(self, "_toolbar_run_btn", None),
            "pause": getattr(self, "_toolbar_pause_btn", None),
            "stop": getattr(self, "_toolbar_stop_btn", None),
            "step": getattr(self, "_toolbar_step_btn", None),
            "toggle_signals_panel": getattr(self, "_toolbar_left_btn", None),
            "toggle_cursors": getattr(self, "_toolbar_cursor_btn", None),
            "toggle_grid": getattr(self, "_toolbar_grid_btn", None),
            "fit_view": getattr(self, "_toolbar_autoscale_btn", None),
            "zoom_in": getattr(self, "_toolbar_zoom_in_btn", None),
            "zoom_out": getattr(self, "_toolbar_zoom_out_btn", None),
            "toggle_measurements": getattr(self, "_toolbar_measure_btn", None),
            "add_expression": getattr(self, "_toolbar_math_btn", None),
            "show_fft_tab": getattr(self, "_toolbar_fft_btn", None),
            "show_compare_tab": getattr(self, "_toolbar_compare_btn", None),
            "export_snapshot": getattr(self, "_toolbar_copy_btn", None),
            "toggle_inspector": getattr(self, "_toolbar_right_btn", None),
        }
        for key, button in button_map.items():
            action = self._scope_actions.get(key)
            if action is None or button is None:
                continue
            button.setEnabled(action.isEnabled())
            button.setToolTip(action.toolTip())

    @staticmethod
    def _scope_shell_palette() -> dict[str, str]:
        """Return scope-local dark shell colors (VirtuScope style)."""
        return {
            "window_bg": "#111318",
            "surface_bg": "#161b27",
            "panel_bg": "#1a1f2e",
            "panel_alt": "#1e2438",
            "header_bg": "#1c2235",
            "border": "#2a3044",
            "border_soft": "#2e3a52",
            "text": "#e2e8f4",
            "muted": "#7a8aaa",
            "accent": "#3b82f6",
            "accent_hover": "#2563eb",
            "accent_fg": "#ffffff",
            "card_bg": "#1e2438",
            "card_border": "#2e3a52",
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
        running_color = "#96db79" if self._simulation_state == "running" else base_color
        paused_color = "#f4d35e" if self._simulation_state == "paused" else base_color
        stopped_color = "#f87171" if self._simulation_state in {"stopped", "error"} else base_color
        cursor_color = "#96db79" if self._stacked_cursors_enabled else base_color
        grid_color = "#72cfff" if self._stacked_grid_enabled else base_color
        inspector_color = "#92a5c9" if self._right_panel_visible else base_color
        self._toolbar_run_btn.setIcon(IconService.get_icon("play", running_color, 14))
        self._toolbar_pause_btn.setIcon(IconService.get_icon("pause", paused_color, 14))
        self._toolbar_stop_btn.setIcon(IconService.get_icon("stop", stopped_color, 14))
        self._toolbar_step_btn.setIcon(IconService.get_icon("ph.skip-forward", base_color, 14))
        self._toolbar_left_btn.setIcon(IconService.get_icon("ph.sidebar-simple-fill", "#92a5c9", 14))
        self._toolbar_cursor_btn.setIcon(IconService.get_icon("ph.crosshair-simple", cursor_color, 14))
        self._toolbar_grid_btn.setIcon(IconService.get_icon("ph.grid-four", grid_color, 14))
        self._toolbar_autoscale_btn.setIcon(IconService.get_icon("ph.corners-out", base_color, 14))
        self._toolbar_zoom_in_btn.setIcon(IconService.get_icon("zoom-in", base_color, 14))
        self._toolbar_zoom_out_btn.setIcon(IconService.get_icon("zoom-out", base_color, 14))
        self._toolbar_measure_btn.setIcon(IconService.get_icon("ph.ruler", base_color, 14))
        self._toolbar_math_btn.setIcon(IconService.get_icon("ph.function", base_color, 14))
        self._toolbar_fft_btn.setIcon(IconService.get_icon("ph.waveform", base_color, 14))
        self._toolbar_compare_btn.setIcon(IconService.get_icon("layers", base_color, 14))
        self._trace_style_menu_btn.setIcon(IconService.get_icon("ph.waveform", base_color, 14))
        self._toolbar_copy_btn.setIcon(IconService.get_icon("ph.arrow-square-out", base_color, 14))
        self._toolbar_right_btn.setIcon(IconService.get_icon("ph.sidebar-simple", inspector_color, 14))
        self._measurement_menu_btn.setIcon(IconService.get_icon("plus", "#dbe4f5", 13))
        if hasattr(self, "_scope_brand_icon"):
            self._scope_brand_icon.setPixmap(
                IconService.get_icon("ph.wave-sine", "#59c7ff", 16).pixmap(16, 16)
            )
        for btn in (
            self._toolbar_run_btn,
            self._toolbar_pause_btn,
            self._toolbar_stop_btn,
            self._toolbar_step_btn,
            self._toolbar_left_btn,
            self._toolbar_cursor_btn,
            self._toolbar_grid_btn,
            self._toolbar_autoscale_btn,
            self._toolbar_zoom_in_btn,
            self._toolbar_zoom_out_btn,
            self._toolbar_measure_btn,
            self._toolbar_math_btn,
            self._toolbar_fft_btn,
            self._toolbar_compare_btn,
            self._trace_style_menu_btn,
            self._toolbar_copy_btn,
            self._toolbar_right_btn,
            self._measurement_menu_btn,
        ):
            btn.setIconSize(QSize(11, 11))

    def _sync_toolbar_toggles(self) -> None:
        for btn, checked in (
            (self._toolbar_left_btn, self._left_panel_visible),
            (self._toolbar_cursor_btn, self._stacked_cursors_enabled),
            (self._toolbar_grid_btn, self._stacked_grid_enabled),
            (self._toolbar_right_btn, self._right_panel_visible),
        ):
            btn.blockSignals(True)
            btn.setChecked(bool(checked))
            btn.blockSignals(False)
        self._apply_toolbar_icons()
        self._sync_scope_action_states()

    def _on_toolbar_left_toggled(self, checked: bool) -> None:
        self._left_panel_toggle_btn.blockSignals(True)
        self._left_panel_toggle_btn.setChecked(bool(checked))
        self._left_panel_toggle_btn.blockSignals(False)
        self._on_toggle_left_panel_clicked(bool(checked))

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
                background-color: #2b3040;
                border: 1px solid #3a4156;
                border-radius: 10px;
            }}
            QWidget#scopeTopMenuRow {{
                background-color: #2b3040;
                border-bottom: 1px solid #40495f;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                min-height: 25px;
            }}
            QLabel#scopeBrandIcon {{
                background: transparent;
            }}
            QLabel#scopeBrandLabel {{
                color: #ecf2ff;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.3px;
            }}
            QToolButton#scopeMenuTextBtn {{
                color: #d6deed;
                background: transparent;
                border: none;
                padding: 0px 5px;
                font-size: 8px;
                font-weight: 500;
            }}
            QToolButton#scopeMenuTextBtn:hover {{
                color: #ffffff;
                background-color: rgba(255, 255, 255, 0.08);
                border-radius: 4px;
            }}
            QLabel#scopeVersionLabel {{
                color: #aab6cc;
                font-size: 8px;
                font-weight: 600;
            }}
            QWidget#scopeToolbarRow {{
                background-color: #32394b;
                border-bottom-left-radius: 10px;
                border-bottom-right-radius: 10px;
                min-height: 24px;
            }}
            QLabel#scopeToolbarScopeBadge {{
                color: #c6d0e2;
                font-size: 8px;
                font-weight: 600;
                padding: 1px 7px;
                background-color: rgba(18, 24, 35, 0.30);
                border: 1px solid rgba(125, 144, 178, 0.22);
                border-radius: 8px;
            }}
            QFrame#scopeToolbarSeparator {{
                background-color: #4d566c;
                min-width: 1px;
                max-width: 1px;
                border: none;
                margin: 2px 5px;
            }}
            QToolButton#scopeToolbarTransportBtn {{
                min-width: 20px;
                max-width: 20px;
                min-height: 20px;
                max-height: 20px;
                background-color: rgba(34, 40, 54, 0.45);
                border: 1px solid rgba(130, 145, 172, 0.16);
                border-radius: 10px;
                padding: 0px;
            }}
            QToolButton#scopeToolbarActionBtn {{
                min-width: 17px;
                max-width: 17px;
                min-height: 17px;
                max-height: 17px;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0px;
            }}
            QToolButton#scopeToolbarMenuBtn {{
                min-width: 18px;
                max-width: 18px;
                min-height: 17px;
                max-height: 17px;
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 0px;
            }}
            QToolButton#scopeToolbarTransportBtn:hover {{
                border-color: rgba(206, 220, 242, 0.30);
                background-color: rgba(52, 60, 76, 0.78);
            }}
            QToolButton#scopeToolbarActionBtn:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                border-color: rgba(206, 220, 242, 0.18);
            }}
            QToolButton#scopeToolbarMenuBtn:hover {{
                background-color: rgba(255, 255, 255, 0.08);
                border-color: rgba(206, 220, 242, 0.18);
            }}
            QToolButton#scopeToolbarTransportBtn:checked {{
                background-color: rgba(88, 104, 130, 0.28);
                border-color: rgba(131, 177, 241, 0.48);
            }}
            QToolButton#scopeToolbarTransportBtn[accentTone="blue"]:checked {{
                background-color: rgba(93, 146, 224, 0.34);
                border-color: rgba(131, 177, 241, 0.68);
            }}
            QToolButton#scopeToolbarTransportBtn[accentTone="green"]:checked {{
                background-color: rgba(126, 176, 95, 0.32);
                border-color: rgba(163, 214, 126, 0.65);
            }}
            QToolButton#scopeToolbarTransportBtn[accentTone="cyan"]:checked {{
                background-color: rgba(67, 155, 197, 0.30);
                border-color: rgba(112, 207, 255, 0.62);
            }}
            QToolButton#scopeToolbarTransportBtn::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QToolButton#scopeToolbarActionBtn::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QToolButton#scopeToolbarMenuBtn::menu-indicator {{
                subcontrol-origin: padding;
                subcontrol-position: right center;
                width: 5px;
                image: none;
            }}
            QWidget#scopePlotSurface {{
                background: {shell["surface_bg"]};
                border: 1px solid {shell["border"]};
                border-radius: 12px;
            }}
            QTabWidget#scopeAnalysisTabs::pane {{
                border: 1px solid {shell["border"]};
                border-radius: 12px;
                background-color: {shell["surface_bg"]};
                top: -1px;
            }}
            QTabWidget#scopeAnalysisTabs > QTabBar::tab {{
                background-color: transparent;
                color: {shell["muted"]};
                padding: 6px 12px;
                font-size: 10px;
                font-weight: 600;
                border: none;
                margin-right: 4px;
            }}
            QTabWidget#scopeAnalysisTabs > QTabBar::tab:selected {{
                color: {shell["text"]};
                border-bottom: 2px solid {shell["accent"]};
            }}
            QWidget#scopeAnalysisPlaceholder {{
                background-color: {shell["surface_bg"]};
            }}
            QLabel#scopePlaceholderTitle {{
                color: {shell["text"]};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel#scopePlaceholderSubtitle {{
                color: {shell["muted"]};
                font-size: 11px;
                font-weight: 500;
            }}
            QWidget#scopeLeftPanel,
            QWidget#scopeRightPanel,
            QWidget#scopeStackedScrollContent,
            QScrollArea#scopeStackedScroll,
            QScrollArea#scopeStackedScroll > QWidget,
            QScrollArea#scopeStackedScroll > QWidget > QWidget {{
                background-color: {shell["panel_bg"]};
            }}
            QFrame#scopeOverviewInset {{
                background-color: rgba(25, 30, 40, 0.92);
                border: 1px solid #4b556d;
                border-radius: 10px;
            }}
            QWidget#scopeBottomControlBar {{
                background-color: #2d3241;
                border: 1px solid #3a4254;
                border-radius: 12px;
            }}
            QWidget#scopeQuickMetricsRow {{
                background-color: transparent;
                border: none;
            }}
            QLabel#scopeQuickMetricPrimary {{
                color: #eef3ff;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#scopeQuickMetricChip {{
                color: #d6deef;
                font-size: 9px;
                font-weight: 600;
                background-color: rgba(18, 23, 33, 0.34);
                border: 1px solid rgba(112, 126, 152, 0.24);
                border-radius: 8px;
                padding: 3px 8px;
            }}
            QWidget#scopeBottomControlBar QLabel {{
                color: #c3cee0;
                font-size: 9px;
                font-weight: 600;
            }}
            QWidget#scopeBottomViewportRow {{
                background-color: transparent;
                border: none;
            }}
            QWidget#scopeBottomDrawerHeader {{
                background-color: transparent;
                border: none;
            }}
            QWidget#scopeBottomDrawerBody {{
                background-color: #262c39;
                border: 1px solid #3a4254;
                border-radius: 8px;
            }}
            QLabel#scopeBottomMeasureTitle {{
                color: #e5ecfb;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#scopeBottomMeasureSummary {{
                color: #c9d5ec;
                font-size: 9px;
                font-weight: 600;
            }}
            QLabel#scopeBottomMeasureMode {{
                color: #a9b8d4;
                font-size: 9px;
                font-weight: 500;
            }}
            QToolButton#scopeBottomDrawerToggleBtn {{
                background-color: #31394b;
                color: #dbe4f5;
                border: 1px solid #46516b;
                border-radius: 8px;
                padding: 2px 10px;
                min-height: 22px;
                font-weight: 600;
            }}
            QToolButton#scopeBottomDrawerToggleBtn:hover {{
                background-color: #3a4356;
                border-color: #6ea6ff;
            }}
            QTabWidget#scopeBottomTabs::pane {{
                border: none;
                background-color: transparent;
            }}
            QTabWidget#scopeBottomTabs > QTabBar::tab {{
                background-color: rgba(255,255,255,0.04);
                color: #b9c4db;
                border: 1px solid #3a4254;
                border-bottom: none;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                padding: 5px 10px;
                margin-right: 4px;
                font-size: 9px;
                font-weight: 600;
            }}
            QTabWidget#scopeBottomTabs > QTabBar::tab:selected {{
                background-color: #2b3140;
                color: #eef3ff;
            }}
            QTableWidget#scopeBottomMeasureTable {{
                background-color: #1f2531;
                alternate-background-color: #232a37;
                border: 1px solid #384258;
                border-radius: 6px;
                gridline-color: #3a455e;
                color: #dde6f8;
                font-size: 9px;
            }}
            QTableWidget#scopeBottomMeasureTable QHeaderView::section {{
                background-color: #2d3447;
                color: #cdd8ef;
                border: none;
                border-right: 1px solid #3a455e;
                border-bottom: 1px solid #3a455e;
                padding: 3px 6px;
                font-size: 9px;
                font-weight: 600;
            }}
            QListWidget#scopeBottomEventsList,
            QPlainTextEdit#scopeBottomConsole {{
                background-color: #1f2531;
                color: #dde6f8;
                border: 1px solid #384258;
                border-radius: 6px;
                font-size: 9px;
            }}
            QWidget#scopeStatusBar {{
                background-color: rgba(17, 23, 33, 0.28);
                border-top: 1px solid #3a4254;
                padding-top: 2px;
            }}
            QLabel#scopeStatusLabel {{
                color: #b9c7df;
                font-size: 9px;
                font-weight: 600;
            }}
            QLabel#scopeSliderInfoLabel {{
                color: #dbe4f7;
                font-size: 9px;
                font-weight: 600;
            }}
            QPushButton#scopeSliderStepBtn {{
                min-width: 22px;
                max-width: 22px;
                min-height: 22px;
                max-height: 22px;
                padding: 0px;
                border-radius: 7px;
                background-color: #262d3b;
                border: 1px solid #3f4a63;
                color: #dce6f8;
            }}
            QPushButton#scopeSliderStepBtn:hover {{
                border-color: #6ea6ff;
            }}
            QSlider#scopeTimelineSlider::groove:horizontal,
            QSlider#scopeZoomSlider::groove:horizontal {{
                border: none;
                height: 5px;
                background: #3a445c;
                border-radius: 2px;
            }}
            QSlider#scopeTimelineSlider::handle:horizontal,
            QSlider#scopeZoomSlider::handle:horizontal {{
                background: #6ea6ff;
                border: 1px solid #6ea6ff;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
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
            QWidget#scopeBottomControlBar QPushButton {{
                background-color: #31394b;
                color: #dbe4f5;
                border: 1px solid #46516b;
                min-height: 22px;
                padding: 3px 9px;
            }}
            QWidget#scopeBottomControlBar QPushButton:hover {{
                background-color: #3a4356;
                border-color: #6ea6ff;
            }}
            QPushButton#scopeMathSignalBtn {{
                background-color: {shell["accent"]};
                color: {shell["accent_fg"]};
                border-color: {shell["accent"]};
            }}
            QPushButton#scopeMathSignalBtn:hover {{
                background-color: {shell["accent_hover"]};
            }}
            QPushButton#scopeAddSignalExprBtn {{
                background-color: #303748;
                color: #eef3ff;
                border: 1px solid #46506a;
                border-radius: 9px;
                padding: 6px 10px;
                min-height: 28px;
                font-size: 11px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton#scopeAddSignalExprBtn:hover {{
                background-color: #384154;
                border-color: #7eb0ff;
            }}
            QToolButton#scopeMeasurementMenuBtn {{
                background-color: #31394b;
                color: #dbe4f5;
                border: 1px solid #46516b;
                border-radius: 8px;
                padding: 2px 8px;
                min-height: 22px;
                font-weight: 600;
            }}
            QToolButton#scopeMeasurementMenuBtn:hover {{
                background-color: #3a4356;
                border-color: #6ea6ff;
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
            QScrollArea#scopeInspectorScroll,
            QWidget#scopeInspectorContent {{
                background-color: transparent;
                border: none;
            }}
            QFrame#scopeInspectorSection {{
                background-color: #202736;
                border: 1px solid #394158;
                border-radius: 10px;
            }}
            QToolButton#scopeInspectorSectionBtn {{
                color: #e5ecfb;
                background-color: transparent;
                border: none;
                padding: 7px 10px;
                font-size: 10px;
                font-weight: 700;
                text-align: left;
            }}
            QWidget#scopeInspectorSectionBody {{
                background-color: transparent;
                border: none;
            }}
            QFrame#scopeRightPanel QLabel {{
                color: #cfdbf0;
                font-size: 10px;
                font-weight: 600;
            }}
            QFrame#scopeRightPanel QCheckBox {{
                color: #dbe4f5;
                font-size: 10px;
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
            track_bg=QColor("#3a445c"),
            track_border=QColor("#4a5672"),
            selected_fill=QColor("#6ea6ff"),
            handle_fill=QColor("#2b3140"),
            handle_border=QColor("#7eb0ff"),
        )

        # ── Force-dark overrides on child panels ──────────────────────────
        # These win over the panels' own apply_theme() because they are
        # applied AFTER, targeting the exact same widget objectNames.
        self._stacked_signal_list.apply_scope_dark_overrides(shell)
        self._stacked_measurements.apply_scope_dark_overrides(shell)
        self._apply_dark_sidebar_tabs(shell)

        self._sync_trace_style_controls()
        self._refresh_signal_list_metadata()
        self._refresh_inspector()
        self._refresh_quick_metrics()
        self._refresh_status_bar()
        self._refresh_title()
        self._rebuild_stacked_plots(self._current_result)

    def _apply_dark_sidebar_tabs(self, shell: dict) -> None:
        """Apply dark VirtuScope styling to the sidebar tab widget and lists."""
        if not hasattr(self, "_sidebar_tabs"):
            return
        bg = shell["panel_bg"]
        surface = shell["surface_bg"]
        border = shell["border"]
        border_soft = shell.get("border_soft", border)
        text = shell["text"]
        muted = shell["muted"]
        accent = shell["accent"]
        card = shell.get("card_bg", "#1e2438")

        self._sidebar_tabs.setStyleSheet(f"""
            QTabWidget#scopeSidebarTabs::pane {{
                background-color: {bg};
                border: none;
            }}
            QTabWidget#scopeSidebarTabs > QTabBar::tab {{
                background-color: transparent;
                color: {muted};
                border: none;
                padding: 4px 8px 6px 8px;
                font-size: 9px;
                font-weight: 600;
                min-width: 44px;
            }}
            QTabWidget#scopeSidebarTabs > QTabBar::tab:selected {{
                background-color: transparent;
                color: {text};
                border-bottom: 2px solid {accent};
            }}
            QTabWidget#scopeSidebarTabs > QTabBar::tab:hover:!selected {{
                background-color: rgba(255,255,255,0.05);
                color: {text};
            }}
        """)

        # Lists inside Scopes / Traces / Views tabs
        list_style = f"""
            QListWidget {{
                background-color: {surface};
                border: none;
                color: {text};
                outline: none;
            }}
            QListWidget::item {{
                padding: 5px 8px;
                border-radius: 6px;
                margin: 1px 2px;
                color: {text};
            }}
            QListWidget::item:selected {{
                background-color: rgba(59, 130, 246, 0.22);
            }}
            QListWidget::item:hover {{
                background-color: rgba(255,255,255,0.05);
            }}
        """
        for lw in (
            self._scopes_list_widget,
            self._traces_list_widget,
            self._views_list_widget,
        ):
            lw.setStyleSheet(list_style)

        # Style action buttons inside the Views/Scopes tab containers
        btn_style = f"""
            QPushButton {{
                background-color: {card};
                color: {text};
                border: 1px solid {border};
                border-radius: 7px;
                padding: 4px 10px;
                font-weight: 600;
                font-size: 10px;
            }}
            QPushButton:hover {{
                background-color: {shell.get("panel_alt", "#1e2438")};
                border-color: {accent};
                color: {text};
            }}
        """
        for btn in (self._save_view_btn, self._delete_view_btn):
            btn.setStyleSheet(btn_style)

        # Re-apply dark to the stacked sidebar container itself
        self._stacked_sidebar.setStyleSheet(f"""
            QWidget#scopeLeftPanel,
            QWidget#scopeLeftPanel > QWidget {{
                background-color: {bg};
            }}
            QWidget#scopeSidebarHeader {{
                background-color: transparent;
            }}
            QLabel#scopeSidebarTitle {{
                color: {text};
                font-size: 13px;
                font-weight: 700;
            }}
            QWidget#scopeSidebarSelectorRow {{
                background-color: {card};
                border: 1px solid {border_soft};
                border-radius: 10px;
            }}
            QLabel#scopeSidebarHint {{
                color: {muted};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.3px;
                padding-left: 10px;
            }}
            QComboBox#scopeSidebarScopeCombo {{
                background-color: transparent;
                color: {text};
                border: none;
                padding: 6px 10px 6px 4px;
                min-height: 28px;
                font-size: 11px;
                font-weight: 600;
            }}
            QComboBox#scopeSidebarScopeCombo:hover {{
                border: none;
            }}
            QWidget#scopeCollapsedRail {{
                background-color: {bg};
                border-right: 1px solid {border};
            }}
            QToolButton#scopeCollapsedRailBtn {{
                background-color: {card};
                border: 1px solid {border_soft};
                color: {muted};
                padding: 4px;
                border-radius: 8px;
            }}
            QToolButton#scopeCollapsedRailBtn:hover {{
                background-color: rgba(59,130,246,0.18);
                border-color: {accent};
                color: {text};
            }}
            QPushButton#scopePanelToggleBtn {{
                background-color: {card};
                color: {muted};
                border: 1px solid {border_soft};
                border-radius: 8px;
                font-size: 11px;
                min-height: 24px;
            }}
            QPushButton#scopePanelToggleBtn:hover {{
                color: {text};
                border-color: {accent};
                background-color: rgba(255,255,255,0.07);
            }}
        """)

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
        if hasattr(self, "_overview_inset"):
            self._overview_inset.hide()
            self._overview_inset.setParent(self._stacked_page)
        while self._stacked_layout.count():
            item = self._stacked_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._plot_widgets.clear()
        self._plot_right_view_boxes.clear()
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

    @staticmethod
    def _measurement_column_label(key: str) -> str:
        labels = {
            "c1": "C1",
            "c2": "C2",
            "dv": "dV",
            "min": "Min",
            "max": "Max",
            "mean": "Mean",
            "rms": "RMS",
            "pkpk": "Pk-Pk",
        }
        return labels.get(key, key.upper())

    @staticmethod
    def _format_measurement_value(value: float | None) -> str:
        if value is None:
            return "—"
        abs_val = abs(value)
        if abs_val >= 1e4 or (0 < abs_val < 1e-4):
            return f"{value:.3e}"
        return f"{value:.5g}"

    def _refresh_bottom_measurements(
        self,
        table_data: dict[str, dict[str, float | None]],
        *,
        dt: float | None,
    ) -> None:
        visible_keys = self._stacked_measurements.visible_measurement_keys()
        headers = ["Signal", *[self._measurement_column_label(key) for key in visible_keys]]
        self._scope_bottom_measure_table.setColumnCount(len(headers))
        self._scope_bottom_measure_table.setHorizontalHeaderLabels(headers)
        self._scope_bottom_measure_table.setRowCount(len(table_data))

        for row, signal_name in enumerate(table_data.keys()):
            self._scope_bottom_measure_table.setRowHeight(row, 22)
            signal_item = QTableWidgetItem(self._display_signal_name(signal_name))
            signal_color = self._stacked_signal_list.get_signal_color(signal_name)
            if signal_color is not None:
                signal_item.setForeground(QColor(*signal_color))
            self._scope_bottom_measure_table.setItem(row, 0, signal_item)

            values = table_data[signal_name]
            for col, key in enumerate(visible_keys, start=1):
                text = self._format_measurement_value(values.get(key))
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self._scope_bottom_measure_table.setItem(row, col, item)

        content_rows = max(1, len(table_data))
        target_height = 20 + (content_rows * 22) + 8
        target_height = max(74, min(138, target_height))
        self._scope_bottom_measure_table.setFixedHeight(target_height)

        scope_text = self._measurement_scope_label()
        if dt is None:
            self._scope_bottom_measure_summary.setText(f"Scope: {scope_text}  |  Δt: —  |  f: —")
            return
        dt_abs = abs(dt)
        freq = (1.0 / dt_abs) if dt_abs > 1e-15 else None
        dt_text = self._format_time_display(dt_abs)
        if freq is None:
            freq_text = "—"
        elif freq >= 1e3:
            freq_text = f"{freq/1e3:.3g} kHz"
        else:
            freq_text = f"{freq:.4g} Hz"
        self._scope_bottom_measure_summary.setText(
            f"Scope: {scope_text}  |  Δt: {dt_text}  |  f: {freq_text}"
        )

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

    def _handle_signal_drop_request(
        self,
        signal_name: str,
        target_group_leader: str | None,
    ) -> bool:
        """Handle a drag/drop request from the signal tree into the workspace."""
        applied = self._apply_dragged_signal_mapping(
            signal_name,
            target_group_leader=target_group_leader,
        )
        if not applied:
            return False
        self._on_stacked_signal_selected(signal_name)
        self._refresh_signal_list_metadata()
        self._log_scope_event(
            f"Signal '{self._display_signal_name(signal_name)}' dropped into "
            f"{'new plot' if target_group_leader is None else self._display_signal_name(target_group_leader)}"
        )
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
        self._refresh_inspector()

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
        self._refresh_inspector()

    def _reset_trace_style_for_signal(self, signal_name: str) -> None:
        if signal_name not in self._trace_signal_names():
            return
        self._trace_styles.pop(signal_name, None)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        self._rebuild_stacked_plots(self._current_result)
        self._refresh_inspector()

    def _reset_all_trace_styles(self) -> None:
        if not self._trace_styles:
            return
        self._trace_styles.clear()
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._sync_trace_style_controls()
        self._rebuild_stacked_plots(self._current_result)
        self._refresh_inspector()

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
        self._right_panel_visible = bool(checked)
        self._apply_panel_visibility()

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        sizes = self._stacked_splitter.sizes()
        if len(sizes) < 2:
            return
        if self._left_panel_visible and sizes[0] > 0:
            self._left_panel_width = sizes[0]
        if len(sizes) >= 3 and self._right_panel_visible and sizes[2] > 0:
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
            if hasattr(self, "_sidebar_tabs"):
                self._sidebar_tabs.setVisible(True)
            if hasattr(self, "_collapsed_rail"):
                self._collapsed_rail.setVisible(False)
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
            if hasattr(self, "_sidebar_tabs"):
                self._sidebar_tabs.setVisible(False)
            if hasattr(self, "_collapsed_rail"):
                self._collapsed_rail.setVisible(True)
            left = self._collapsed_panel_width

        if self._right_panel_visible:
            self._right_header_label.setVisible(True)
            self._stacked_right_panel.setMinimumWidth(280)
            self._stacked_right_panel.setMaximumWidth(420)
            self._stacked_right_panel.setVisible(True)
            self._right_panel_toggle_btn.setText("▶")
            self._right_panel_toggle_btn.setToolTip("Collapse inspector")
            right = self._right_panel_width
        else:
            self._stacked_right_panel.setMinimumWidth(0)
            self._stacked_right_panel.setMaximumWidth(0)
            self._stacked_right_panel.setVisible(False)
            self._right_panel_toggle_btn.setText("◀")
            self._right_panel_toggle_btn.setToolTip("Expand inspector")
            right = 0

        total = max(self.width(), 1200)
        center = max(500, total - left - right - 24)
        target_sizes = [left, center, right]
        self._start_panel_animation(target_sizes)
        self._sync_toolbar_toggles()

    def _start_panel_animation(self, target_sizes: list[int]) -> None:
        """Animate splitter from current sizes to target sizes over ~150ms."""
        if self._panel_anim_timer is not None:
            self._panel_anim_timer.stop()
            self._panel_anim_timer = None
        current = self._stacked_splitter.sizes()
        if len(current) != 3 or current == target_sizes:
            self._stacked_splitter.setSizes(target_sizes)
            return
        self._panel_anim_target = list(target_sizes)
        self._panel_anim_start = list(current)
        self._panel_anim_current_step = 0
        self._panel_anim_timer = QTimer(self)
        self._panel_anim_timer.setInterval(max(1, 150 // self._panel_anim_steps))
        self._panel_anim_timer.timeout.connect(self._panel_anim_step)
        self._panel_anim_timer.start()

    def _panel_anim_step(self) -> None:
        """Advance one animation step."""
        self._panel_anim_current_step += 1
        steps = self._panel_anim_steps
        t = self._panel_anim_current_step / steps
        sizes = [
            int(s + (e - s) * t)
            for s, e in zip(self._panel_anim_start, self._panel_anim_target)
        ]
        self._stacked_splitter.setSizes(sizes)
        if self._panel_anim_current_step >= steps:
            if self._panel_anim_timer is not None:
                self._panel_anim_timer.stop()
                self._panel_anim_timer = None
            self._stacked_splitter.setSizes(self._panel_anim_target)

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
        self._update_stacked_measurements()

    def _on_scope_selector_changed(self, signal_name: str) -> None:
        if not signal_name or signal_name not in self._stacked_signals:
            return
        self._stacked_active_signal = signal_name
        if hasattr(self, "_toolbar_scope_label"):
            self._toolbar_scope_label.setText(self._display_signal_name(signal_name))
        self._selected_plot_group_leader = self._plot_group_leader(signal_name)
        self._stacked_signal_list.set_signal_visible(signal_name, True)
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()
        self._refresh_inspector()

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
        self._signal_axis_targets[name] = "left"

        visible = set(self._stacked_signal_list.get_visible_signals())
        visible.add(name)
        self._stacked_signal_list.set_signals(list(self._stacked_signals.keys()))
        self._apply_stacked_trace_colors()
        for signal in self._stacked_signals:
            self._stacked_signal_list.set_signal_visible(signal, signal in visible)

        self._stacked_active_signal = name
        self._sync_scope_selector()
        self._sync_trace_style_controls()
        self._refresh_signal_list_metadata()
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()
        self._refresh_inspector()
        self._log_scope_event(f"Math signal added: {name}")

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
        self._log_scope_event("Autoscale applied")

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
            if self._stacked_interval_target == "window":
                self._update_stacked_measurements()
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
        if normalize_interval_target(self._stacked_interval_target) == "window":
            self._update_stacked_measurements()

    def _refresh_bottom_controls_enabled(self) -> None:
        has_data = len(self._stacked_time) > 1 and bool(self._plot_widgets)
        self._timeline_slider.setEnabled(has_data)
        self._zoom_slider.setEnabled(has_data)
        self._autoscale_btn.setEnabled(has_data)
        self._measurement_menu_btn.setEnabled(has_data)
        self._inspector_measure_menu_btn.setEnabled(has_data)
        self._scope_bottom_drawer_toggle_btn.setEnabled(has_data)
        self._sync_scope_action_states()

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
        if checked and not self._bottom_drawer_expanded:
            self._on_bottom_drawer_toggled(True)
        self._sync_toolbar_toggles()
        self._set_stacked_cursor_enabled(len(self._stacked_time) > 0)
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()
        self._log_scope_event("Cursors enabled" if checked else "Cursors disabled")
        self._refresh_inspector()
        self._refresh_status_bar()

    def _on_stacked_grid_toggled(self, checked: bool) -> None:
        self._stacked_grid_enabled = checked
        self._sync_toolbar_toggles()
        self._rebuild_stacked_plots(self._current_result)
        self._log_scope_event("Grid shown" if checked else "Grid hidden")

    def _auto_range_stacked(self) -> None:
        for plot in self._plot_widgets:
            plot.autoRange()
        for right_view_box in self._plot_right_view_boxes:
            right_view_box.enableAutoRange(axis=pg.ViewBox.YAxis, enable=True)
            right_view_box.autoRange()

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
            self._signal_axis_targets = {}
            self._stacked_active_signal = None
            self._selected_plot_group_leader = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._scope_selector_combo.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._scope_bottom_measure_table.setRowCount(0)
            self._scope_bottom_measure_summary.setText("Scope: Full Range  |  Δt: —  |  f: —")
            self._sync_trace_style_controls()
            self._refresh_bottom_controls_enabled()
            self._refresh_signal_list_metadata()
            self._refresh_inspector()
            self._refresh_quick_metrics()
            self._refresh_status_bar()
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
            self._signal_axis_targets = {}
            self._stacked_active_signal = None
            self._selected_plot_group_leader = None
            self._stacked_cursor_initialized = False
            self._stacked_signal_list.clear()
            self._scope_selector_combo.clear()
            self._set_stacked_cursor_enabled(False)
            self._stacked_measurements.clear_statistics()
            self._stacked_measurements.clear_cursor_measurements()
            self._stacked_measurements.set_multi_signal_measurements({})
            self._scope_bottom_measure_table.setRowCount(0)
            self._scope_bottom_measure_summary.setText("Scope: Full Range  |  Δt: —  |  f: —")
            self._sync_trace_style_controls()
            self._refresh_bottom_controls_enabled()
            self._refresh_signal_list_metadata()
            self._refresh_inspector()
            self._refresh_quick_metrics()
            self._refresh_status_bar()
            return

        self._stacked_time = time
        self._stacked_signals = valid_signals
        self._signal_axis_targets = {
            name: self._signal_axis_targets.get(name, "left")
            for name in valid_signals
        }
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
        self._refresh_signal_list_metadata()
        self._refresh_inspector()
        self._refresh_quick_metrics()
        self._refresh_status_bar()

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
            self._toolbar_scope_label.setText(
                self._display_signal_name(current or (self._component_name or "No signal"))
            )

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
        self._refresh_inspector()

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
            self._refresh_inspector()

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
        self._refresh_inspector()

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
            self._scope_bottom_measure_table.setRowCount(0)
            self._scope_bottom_measure_summary.setText(
                f"Scope: {self._measurement_scope_label()}  |  Δt: —  |  f: —"
            )
            self._refresh_quick_metrics()
            self._refresh_status_bar()
            return

        signal_name = self._stacked_active_signal
        if signal_name not in self._stacked_signals:
            signal_name = next(iter(self._stacked_signals))
            self._stacked_active_signal = signal_name

        values = self._stacked_signals[signal_name]
        subset_time, subset_values = self._measurement_subset(values)
        scoped_stats = self._calculate_measurement_stats(subset_values)
        if scoped_stats.get("min") is None:
            self._stacked_measurements.clear_statistics()
        else:
            self._stacked_measurements.update_statistics(
                float(scoped_stats["min"]),
                float(scoped_stats["max"]),
                float(scoped_stats["mean"]),
                float(scoped_stats["rms"]),
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
            table_data = self._build_stacked_measurements_table(t1, t2)
            self._stacked_measurements.set_multi_signal_measurements(table_data)
            summary_dt = dt if normalize_interval_target(self._stacked_interval_target) == "a_to_b" else None
            self._refresh_bottom_measurements(table_data, dt=summary_dt)
        else:
            self._stacked_measurements.clear_cursor_measurements()
            table_data = self._build_stacked_measurements_table(None, None)
            self._stacked_measurements.set_multi_signal_measurements(table_data)
            self._refresh_bottom_measurements(table_data, dt=None)
        self._refresh_quick_metrics()
        self._refresh_status_bar()

    def _build_stacked_measurements_table(
        self,
        t1: float | None,
        t2: float | None,
    ) -> dict[str, dict[str, float | None]]:
        table: dict[str, dict[str, float | None]] = {}
        for name, values in self._stacked_signals.items():
            _subset_time, subset_values = self._measurement_subset(values)
            stats = self._calculate_measurement_stats(subset_values)
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
        self._log_scope_event("Plot image copied to clipboard")

    def _rebuild_stacked_plots(self, result: SimulationResult | None) -> None:
        self._clear_stacked_plots()

        if not result or len(self._stacked_time) == 0 or not self._stacked_signals:
            self._overview_inset.hide()
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
            self._overview_inset.hide()
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
        overview_target_leader = (
            self._selected_plot_group_leader
            if self._selected_plot_group_leader in grouped_signals
            else group_items[0][0]
        )
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

            # --- Header row: signal chip + title/meta + mini stats ---
            header_widget = QWidget()
            header_widget.setObjectName("scopePlotHeaderBar")
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(10, 7, 10, 7)
            header_layout.setSpacing(8)

            color_chip = QLabel()
            color_chip.setObjectName("scopePlotHeaderChip")
            color_chip.setFixedSize(12, 12)
            color_chip.setStyleSheet(
                f"background-color: {hex_color}; border-radius: 4px; border: 1px solid rgba(255,255,255,0.18);"
            )
            header_layout.addWidget(color_chip, stretch=0)

            title_stack = QWidget()
            title_stack_layout = QVBoxLayout(title_stack)
            title_stack_layout.setContentsMargins(0, 0, 0, 0)
            title_stack_layout.setSpacing(1)

            title_row = QWidget()
            title_row_layout = QHBoxLayout(title_row)
            title_row_layout.setContentsMargins(0, 0, 0, 0)
            title_row_layout.setSpacing(6)

            title_label = QLabel(self._display_signal_name(primary_signal_name))
            title_label.setObjectName("scopePlotHeaderTitle")
            title_row_layout.addWidget(title_label, stretch=0)

            if len(group_signal_names) > 1:
                overlay_badge = QLabel(f"+{len(group_signal_names) - 1}")
                overlay_badge.setObjectName("scopePlotHeaderBadge")
                title_row_layout.addWidget(overlay_badge, stretch=0)

            title_row_layout.addStretch(1)
            title_stack_layout.addWidget(title_row)

            axis_badge = self._axis_badge_text(primary_signal_name)
            subtitle_text = f"Axis {axis_badge}"
            if len(group_signal_names) > 1:
                overlay_names = [
                    self._display_signal_name(name)
                    for name in group_signal_names
                    if name != primary_signal_name
                ]
                overlay_preview = ", ".join(overlay_names[:2])
                if len(overlay_names) > 2:
                    overlay_preview = f"{overlay_preview}, ..."
                subtitle_text = f"Axis {axis_badge}  •  Overlay: {overlay_preview}"
            subtitle_label = QLabel(subtitle_text)
            subtitle_label.setObjectName("scopePlotHeaderMeta")
            title_stack_layout.addWidget(subtitle_label)

            header_layout.addWidget(title_stack, stretch=1)

            # Mini stats row
            if sig_stats:
                fmt = "{:.4g}"
                stats_str = (
                    f"RMS: {fmt.format(sig_stats.get('rms', 0))}  "
                    f"Peak: {fmt.format(sig_stats.get('max', 0))}  "
                    f"Avg: {fmt.format(sig_stats.get('mean', 0))}"
                )
                stats_lbl = QLabel(stats_str)
                stats_lbl.setObjectName("scopePlotHeaderStats")
                header_layout.addWidget(stats_lbl)

            panel_layout.addWidget(header_widget)

            # --- Plot ---
            group_right_signal_names = [
                name
                for name in group_signal_names
                if self._signal_axis_targets.get(name, "left") == "right"
            ]

            plot = ScopePlotWidget(
                group_leader=group_leader,
                drop_handler=self._handle_signal_drop_request,
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
            item.hideAxis("right")
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

            right_view_box: ScopePlotViewBox | None = None
            if group_right_signal_names:
                item.showAxis("right")
                right_axis = item.getAxis("right")
                right_axis.setStyle(
                    tickFont=item.getAxis("left").style.get("tickFont"),
                    autoExpandTextSpace=False,
                    tickTextOffset=6,
                )
                right_view_box = ScopePlotViewBox(
                    group_leader=group_leader,
                    wheel_handler=self._on_group_plot_wheel,
                    select_handler=self._on_group_plot_selected,
                )
                item.scene().addItem(right_view_box)
                right_axis.linkToView(right_view_box)
                right_view_box.setXLink(item.vb)

                def _sync_right_geometry(*_args, main_vb=item.vb, secondary_vb=right_view_box) -> None:
                    secondary_vb.setGeometry(main_vb.sceneBoundingRect())
                    secondary_vb.linkedViewChanged(main_vb, secondary_vb.XAxis)

                item.vb.sigResized.connect(_sync_right_geometry)
                _sync_right_geometry()
                self._plot_right_view_boxes.append(right_view_box)

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
                if signal_name in group_right_signal_names and right_view_box is not None:
                    trace = pg.PlotDataItem(
                        t_trace,
                        plot_values,
                        pen=pen,
                        skipFiniteCheck=True,
                    )
                    right_view_box.addItem(trace)
                    if item.legend is not None and trace_name:
                        item.legend.addItem(trace, trace_name)
                else:
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
            if group_leader == overview_target_leader:
                plot_overlay_layout.addWidget(
                    self._overview_inset,
                    0,
                    0,
                    alignment=Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight,
                )
                self._overview_inset.show()

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
            if group_right_signal_names:
                axis = item.getAxis("right")
                axis.setPen(pg.mkPen(plot_colors["plot_axis"]))
                axis.setTickPen(pg.mkPen(plot_colors["plot_axis"]))
                axis.setTextPen(pg.mkPen(plot_colors["plot_text"]))
            plot.showGrid(
                x=self._stacked_grid_enabled,
                y=self._stacked_grid_enabled,
                alpha=0.23,
            )

            header_bg = "#253046" if is_active else "#202839"
            header_border = "#3e506f" if is_active else shell["border_soft"]
            title_weight = "700" if is_active else "600"
            title_label.setStyleSheet(
                f"color: {hex_color}; font-weight: {title_weight}; font-size: 12px;"
            )
            subtitle_label.setStyleSheet(
                f"color: {shell['muted']}; font-size: 9px; font-weight: 600; letter-spacing: 0.2px;"
            )
            if len(group_signal_names) > 1:
                overlay_badge.setStyleSheet(
                    f"color: {shell['text']}; font-size: 9px; font-weight: 700; "
                    f"background-color: rgba({r}, {g}, {b}, 0.22); border: 1px solid rgba({r}, {g}, {b}, 0.34); "
                    "border-radius: 8px; padding: 1px 6px;"
                )
            if sig_stats:
                stats_lbl.setStyleSheet(
                    f"color: {shell['muted']}; font-size: 9px; font-family: monospace; font-weight: 600; "
                    "background-color: rgba(10, 14, 22, 0.35); border-radius: 8px; padding: 2px 6px;"
                )
            panel.setStyleSheet(
                f"""
                QFrame {{
                    background-color: {shell["panel_bg"]};
                    border: 1px solid {shell["border"]};
                    border-left: 2px solid {hex_color};
                    border-radius: 10px;
                }}
                """
            )
            header_widget.setStyleSheet(
                f"background-color: {header_bg}; border-radius: 8px; margin: 0; border: 1px solid {header_border};"
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
        self._refresh_overview_plot()

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

    # ------------------------------------------------------------------
    # Feature: Signal pane context menu (task 2.3)
    # ------------------------------------------------------------------
    def _on_signal_list_context_menu(self, pos: object) -> None:
        """Show context menu for the signal list panel."""
        list_widget = self._stacked_signal_list._list_widget
        global_pos = self._stacked_signal_list.mapToGlobal(pos)
        list_pos = list_widget.viewport().mapFromGlobal(global_pos)
        item = list_widget.itemAt(list_pos)
        if item is None:
            return

        menu = QMenu(self)

        if item.data(Qt.ItemDataRole.UserRole) == "__group_header__":
            leader = str(item.data(Qt.ItemDataRole.UserRole + 1) or "").strip()
            if not leader:
                return
            collapsed = self._stacked_signal_list._collapsed_groups.get(leader, False)
            toggle_group_action = menu.addAction("Expand Group" if collapsed else "Collapse Group")
            group_visible = all(
                name in self._stacked_signal_list.get_visible_signals()
                for name in self._stacked_signal_list._group_children.get(leader, [])
            )
            visibility_action = menu.addAction("Hide Group" if group_visible else "Show Group")
            split_group_action = menu.addAction("Split Group into Dedicated Plots")
            action = menu.exec(global_pos)
            if action == toggle_group_action:
                self._stacked_signal_list._toggle_group_collapsed(leader)
            elif action == visibility_action:
                self._stacked_signal_list._set_group_visibility(leader, not group_visible)
            elif action == split_group_action:
                for signal_name in self._stacked_signal_list._group_children.get(leader, []):
                    self._set_signal_plot_group(signal_name, signal_name)
            return

        selected = getattr(item, "signal_name", None)
        if not selected or selected not in self._stacked_signals:
            return
        self._on_stacked_signal_selected(selected)

        is_visible = selected in self._stacked_signal_list.get_visible_signals()
        visible_action = menu.addAction("Hide" if is_visible else "Show")
        rename_action = menu.addAction("Rename Alias…")
        color_action = menu.addAction("Change Color…")

        axis_menu = menu.addMenu("Move to Axis")
        current_axis = self._signal_axis_targets.get(selected, "left")
        axis_actions = {}
        for label, target in (("Left", "left"), ("Right", "right"), ("New Plot", "new_plot")):
            axis_action = axis_menu.addAction(label)
            axis_action.setCheckable(True)
            axis_action.setChecked(current_axis == target)
            axis_actions[axis_action] = target

        menu.addSeparator()
        overlay_action = menu.addAction("Overlay on Active Pane")
        new_pane_action = menu.addAction("Open in New Pane")
        add_measure_action = menu.addAction("Show Measurements")
        highlight_action = menu.addAction("Highlight Trace")

        action = menu.exec(global_pos)
        if action == visible_action:
            self._stacked_signal_list.set_signal_visible(selected, not is_visible)
            self._on_stacked_signal_visibility_changed(selected, not is_visible)
        elif action == rename_action:
            current_alias = self._signal_labels.get(selected, "")
            alias, ok = QInputDialog.getText(
                self,
                "Rename Signal Alias",
                "Alias:",
                text=current_alias,
            )
            if ok:
                self._set_signal_alias(selected, alias)
        elif action == color_action:
            self._pick_trace_color_for_signal(selected)
        elif action in axis_actions:
            self._set_signal_axis_target(selected, axis_actions[action])
        elif action == overlay_action:
            self._set_signal_pane(selected, overlay=True)
        elif action == new_pane_action:
            self._set_signal_pane(selected, overlay=False)
        elif action == add_measure_action:
            self._on_bottom_drawer_toggled(True)
            self._scope_bottom_tabs.setCurrentIndex(0)
        elif action == highlight_action:
            self._on_stacked_signal_selected(selected)

    def _set_signal_pane(self, signal_name: str, overlay: bool) -> None:
        """Move signal_name to overlay on active pane or give it its own pane."""
        if signal_name not in self._stacked_signals:
            return
        if overlay:
            leader = self._selected_plot_group_leader
            if leader and leader != signal_name:
                self._set_signal_plot_group(signal_name, leader)
            else:
                # Overlay on the first available leader that isn't itself
                for name in self._stacked_signals:
                    if name != signal_name:
                        self._set_signal_plot_group(signal_name, name)
                        break
        else:
            # Give it its own pane by making it a leader
            self._stacked_plot_groups[signal_name] = signal_name
        self._stacked_signal_list.set_signal_visible(signal_name, True)
        self._rebuild_stacked_plots(self._current_result)

    # ------------------------------------------------------------------
    # Feature: Interval selector (task 4.4)
    # ------------------------------------------------------------------
    def _on_interval_target_changed(self, text: str) -> None:
        """Update interval target from the combo box selection."""
        idx = self._interval_combo.currentIndex()
        if idx >= 0:
            value = self._interval_combo.itemData(idx)
            if value:
                self._stacked_interval_target = normalize_interval_target(str(value))
        inspector_idx = self._inspector_interval_combo.findData(self._stacked_interval_target)
        if inspector_idx >= 0 and self._inspector_interval_combo.currentIndex() != inspector_idx:
            self._inspector_interval_combo.blockSignals(True)
            self._inspector_interval_combo.setCurrentIndex(inspector_idx)
            self._inspector_interval_combo.blockSignals(False)
        self._refresh_stacked_measurements()
        self._refresh_inspector()

    def _refresh_stacked_measurements(self) -> None:
        """Refresh all measurement-dependent surfaces."""
        self._update_stacked_measurements()

    # ------------------------------------------------------------------
    # Feature: Scopes tab (task 3.1)
    # ------------------------------------------------------------------
    def _refresh_scopes_tab(self) -> None:
        """Update the Scopes tab list widget."""
        if not hasattr(self, "_scopes_list_widget"):
            return
        self._scopes_list_widget.clear()
        scope_name = self._stacked_active_signal or "Default Scope"
        self._scopes_list_widget.addItem(scope_name)

    # ------------------------------------------------------------------
    # Feature: Traces tab (task 3.1)
    # ------------------------------------------------------------------
    def _refresh_traces_tab(self) -> None:
        """Update the Traces tab list widget with active traces."""
        if not hasattr(self, "_traces_list_widget"):
            return
        self._traces_list_widget.clear()
        visible = set(self._stacked_signal_list.get_visible_signals())
        for signal_name in self._stacked_signals:
            label = signal_name
            if signal_name in visible:
                label = f"\u25cf {signal_name}"
            else:
                label = f"\u25cb {signal_name}"
            self._traces_list_widget.addItem(label)

    # ------------------------------------------------------------------
    # Feature: Views tab (task 3.1)
    # ------------------------------------------------------------------
    def _refresh_views_tab(self) -> None:
        """Update the saved views list widget."""
        if not hasattr(self, "_views_list_widget"):
            return
        self._views_list_widget.clear()
        for view_id, (t_start, t_end) in self._saved_views.items():
            self._views_list_widget.addItem(f"{view_id}: {t_start:.4g}s \u2192 {t_end:.4g}s")

    def _on_save_view_clicked(self) -> None:
        """Save the current visible time window as a named view."""
        name, ok = QInputDialog.getText(self, "Save View", "View name:")
        if not ok or not name.strip():
            return
        sizes = self._stacked_splitter.sizes()
        t_arr = self._stacked_time
        if len(t_arr) < 2:
            return
        t_start = float(t_arr[0])
        t_end = float(t_arr[-1])
        view_id = name.strip()
        self._saved_views[view_id] = (t_start, t_end)
        self._refresh_views_tab()
        self._log_scope_event(f"Saved view created: {view_id}")

    def _on_apply_view_clicked(self, view_id: str) -> None:
        """Restore a saved view's time window."""
        if view_id not in self._saved_views:
            return
        _t_start, _t_end = self._saved_views[view_id]
        # Rebuild plots with the saved view context (time window restored via sliders)
        self._rebuild_stacked_plots(self._current_result)

    def _on_delete_view_clicked(self, view_id: str) -> None:
        """Delete a saved view."""
        self._saved_views.pop(view_id, None)
        self._refresh_views_tab()

    def _on_scope_renamed(self) -> None:
        """Rename the current scope via dialog."""
        current_name = self._stacked_active_signal or "Scope"
        name, ok = QInputDialog.getText(
            self, "Rename Scope", "New name:", text=current_name
        )
        if not ok or not name.strip():
            return
        new_name = name.strip()
        if self._stacked_active_signal and new_name != self._stacked_active_signal:
            if hasattr(self, "_toolbar_scope_label"):
                self._toolbar_scope_label.setText(new_name)
        self._refresh_scopes_tab()

    # ------------------------------------------------------------------
    # Feature: Zoom overview mini-panel (task 5.3)
    # ------------------------------------------------------------------
    def _refresh_overview_plot(self) -> None:
        """Refresh the overview thumbnail plot with current data."""
        if not hasattr(self, "_overview_plot"):
            return
        self._overview_plot.clear()
        self._overview_plot.addItem(self._overview_region)
        self._overview_plot.setBackground("#171c25")
        overview_item = self._overview_plot.getPlotItem()
        overview_item.showGrid(x=False, y=False)
        self._overview_region.setBrush(QBrush(QColor(110, 166, 255, 34)))
        region_pen = pg.mkPen(QColor(145, 190, 255, 180), width=1.0)
        hover_pen = pg.mkPen(QColor(173, 209, 255, 220), width=1.0)
        for line in self._overview_region.lines:
            line.setPen(region_pen)
            line.setHoverPen(hover_pen)
        if len(self._stacked_time) < 2:
            self._overview_inset.hide()
            return
        time = self._stacked_time
        palette = self._trace_palette() if hasattr(self, "_trace_palette") else []
        color_idx = 0
        for signal_name, values in self._stacked_signals.items():
            if len(values) != len(time):
                continue
            color = palette[color_idx % len(palette)] if palette else (100, 180, 255)
            t_trace, plot_values = self._decimate_stacked_for_display(time, values, max_points=300)
            pen = pg.mkPen(color=color, width=1)
            self._overview_plot.plot(t_trace, plot_values, pen=pen)
            color_idx += 1
        t_min = float(time[0])
        t_max = float(time[-1])
        self._overview_region.setRegion((t_min, t_max))
        self._overview_inset.show()
