"""Floating windows that host per-component scope viewers."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QCloseEvent, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QSplitter,
    QInputDialog,
    QMessageBox,
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


class MathSignalDialog(QDialog):
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
        self._track_bg = track_bg
        self._track_border = track_border
        self._selected_fill = selected_fill
        self._handle_fill = handle_fill
        self._handle_border = handle_border
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum + 1)
        self.setValues(self._low, self._high)

    def setValues(self, low: int, high: int) -> None:
        low_clamped = max(self._minimum, min(int(low), self._maximum - 1))
        high_clamped = max(low_clamped + 1, min(int(high), self._maximum))
        changed = (low_clamped != self._low) or (high_clamped != self._high)
        self._low = low_clamped
        self._high = high_clamped
        if changed:
            self.rangeChanged.emit(self._low, self._high)
        self.update()

    def lowValue(self) -> int:
        return self._low

    def highValue(self) -> int:
        return self._high

    def minimum(self) -> int:
        return self._minimum

    def maximum(self) -> int:
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
        if not self.isEnabled() or self._drag_target is None:
            return
        self._update_from_mouse(int(event.position().x()))

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        self._drag_target = None

    def _update_from_mouse(self, x: int) -> None:
        value = self._x_to_value(x)
        if self._drag_target == "low":
            self.setValues(value, self._high)
        elif self._drag_target == "high":
            self.setValues(self._low, value)


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
        self._syncing_stacked_cursor_controls = False
        self._stacked_cursor_initialized = False
        self._trace_styles: dict[str, dict[str, object]] = {}
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

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

        self._stacked_add_scope_btn = QPushButton("Add Scope")
        self._stacked_add_scope_btn.setObjectName("scopeStackedAddScopeBtn")
        self._stacked_add_scope_btn.clicked.connect(self._on_add_scope_clicked)
        bottom_layout.addWidget(self._stacked_add_scope_btn)

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
        layout.addWidget(self._scope_bottom_controls, stretch=0)

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
        return self._component_id

    def set_component_name(self, name: str) -> None:
        self._component_name = name
        self._refresh_title()

    def set_bindings(self, bindings: list[ScopeChannelBinding]) -> None:
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
        self._refresh_stacked_sidebar(self._current_result)
        self._rebuild_stacked_plots(self._current_result)

        self._message_label.setText(self._format_status(found_channels, missing_channels))

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
        if hasattr(self, "_scope_title_label"):
            self._scope_title_label.setText(self._component_name or "Unnamed")
        if hasattr(self, "_scope_type_badge"):
            self._scope_type_badge.setText(label)

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to scope chrome and stacked display."""
        self._theme = theme
        c = theme.colors
        is_dark = theme.is_dark
        self._viewer.apply_theme(theme)
        self._apply_stacked_trace_colors()
        self._stacked_signal_list.apply_theme(theme)
        self._stacked_measurements.apply_theme(theme, cursor_palette=self._cursor_palette())
        self.setStyleSheet(f"""
            QWidget#scopePlotSurface {{
                background: {c.background};
                border: 1px solid {c.panel_border};
                border-radius: 12px;
            }}
            QWidget#scopeLeftPanel,
            QWidget#scopeRightPanel,
            QWidget#scopeStackedScrollContent,
            QScrollArea#scopeStackedScroll,
            QScrollArea#scopeStackedScroll > QWidget,
            QScrollArea#scopeStackedScroll > QWidget > QWidget {{
                background-color: {c.panel_background};
            }}
            QWidget#scopeBottomControlBar {{
                background-color: {c.panel_background};
                border: 1px solid {c.panel_border};
                border-radius: 12px;
            }}
            QWidget#scopeBottomControlBar QLabel {{
                color: {c.foreground_muted};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#scopeSliderInfoLabel {{
                color: {c.foreground};
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#scopeSliderStepBtn {{
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                padding: 0px;
            }}
            QSlider#scopeTimelineSlider::groove:horizontal,
            QSlider#scopeZoomSlider::groove:horizontal {{
                border: none;
                height: 4px;
                background: {c.divider};
                border-radius: 2px;
            }}
            QSlider#scopeTimelineSlider::handle:horizontal,
            QSlider#scopeZoomSlider::handle:horizontal {{
                background: {c.primary};
                border: 1px solid {c.primary};
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }}
            QLabel#scopeMappingLabel {{
                color: {c.foreground_muted};
                font-size: 11px;
                font-weight: 500;
            }}
            QLabel#scopeMessageLabel {{
                color: {c.success if is_dark else c.primary};
                font-weight: 600;
                font-size: 12px;
            }}
            QComboBox, QDoubleSpinBox {{
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 10px;
                padding: 5px 10px;
                min-height: 28px;
            }}
            QComboBox:hover, QDoubleSpinBox:hover {{
                border-color: {c.input_focus_border};
            }}
            QPushButton {{
                background-color: {c.secondary};
                color: {c.secondary_foreground};
                border: 1px solid {c.border};
                border-radius: 10px;
                padding: 5px 12px;
                min-height: 28px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {c.secondary_hover};
                border-color: {c.input_focus_border};
            }}
            QPushButton#scopeMathSignalBtn,
            QPushButton#scopeStackedAddScopeBtn {{
                background-color: {c.primary};
                color: {c.primary_foreground};
                border-color: {c.primary};
            }}
            QPushButton#scopeMathSignalBtn:hover,
            QPushButton#scopeStackedAddScopeBtn:hover {{
                background-color: {c.primary_hover};
            }}
            QWidget#scopeRightControlBar QCheckBox {{
                spacing: 4px;
                padding: 0;
            }}
            QWidget#scopeRightControlBar {{
                background-color: {c.background_alt};
                border: 1px solid {c.panel_border};
                border-radius: 10px;
            }}
            QWidget#scopeRightControlBar QLabel {{
                color: {c.foreground_muted};
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
                background-color: {c.input_background};
                color: {c.foreground};
                border: 1px solid {c.input_border};
                border-radius: 7px;
                padding: 4px 9px;
                min-height: 25px;
                font-size: 11px;
            }}
        """)
        self._timeline_slider.set_theme_colors(
            track_bg=QColor(c.divider),
            track_border=QColor(c.border),
            selected_fill=QColor(c.primary),
            handle_fill=QColor(c.input_background),
            handle_border=QColor(c.primary),
        )
        self._sync_trace_style_controls()
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
        self._rebuild_stacked_plots(self._current_result)

    def _on_trace_style_reset(self) -> None:
        signal_name = self._selected_trace_signal()
        if signal_name is None:
            return

        self._trace_styles.pop(signal_name, None)
        self._apply_trace_styles_to_viewer()
        self._apply_stacked_trace_colors()
        self._set_trace_controls_for_signal(signal_name)
        self._rebuild_stacked_plots(self._current_result)

    def _on_add_scope_clicked(self) -> None:
        if not self._stacked_signals:
            return

        visible = set(self._stacked_signal_list.get_visible_signals())
        available = [name for name in self._stacked_signals if name not in visible]
        if not available:
            QMessageBox.information(self, "Add Scope", "All available scopes are already added.")
            return

        if len(available) == 1:
            next_signal = available[0]
        else:
            next_signal, ok = QInputDialog.getItem(
                self,
                "Add Scope",
                "Select signal to add:",
                available,
                0,
                False,
            )
            if not ok or not next_signal:
                return

        self._stacked_signal_list.set_signal_visible(next_signal, True)
        self._stacked_active_signal = next_signal
        self._sync_scope_selector()
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_toggle_left_panel_clicked(self, checked: bool) -> None:
        if not checked:
            sizes = self._stacked_splitter.sizes()
            if len(sizes) == 3 and sizes[0] > 0:
                self._left_panel_width = sizes[0]
        self._left_panel_visible = bool(checked)
        self._apply_panel_visibility()

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
            self._left_scope_label.setVisible(True)
            self._scope_selector_combo.setVisible(True)
            self._left_sidebar_top_row.setVisible(True)
            self._left_sidebar_actions_row.setVisible(True)
            self._create_math_signal_btn.setVisible(True)
            self._stacked_signal_list.setVisible(True)
            self._stacked_sidebar.setMinimumWidth(270)
            self._stacked_sidebar.setMaximumWidth(380)
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
            left = self._collapsed_panel_width

        if self._right_panel_visible:
            self._right_header_label.setVisible(True)
            self._stacked_right_controls.setVisible(True)
            self._stacked_measurements.setVisible(True)
            self._stacked_right_panel.setMinimumWidth(280)
            self._stacked_right_panel.setMaximumWidth(420)
            right = self._right_panel_width
        else:
            self._right_header_label.setVisible(False)
            self._stacked_right_controls.setVisible(False)
            self._stacked_measurements.setVisible(False)
            self._stacked_right_panel.setMinimumWidth(self._collapsed_panel_width)
            self._stacked_right_panel.setMaximumWidth(self._collapsed_panel_width)
            right = self._collapsed_panel_width

        total = max(self.width(), 1200)
        center = max(500, total - left - right - 40)
        self._stacked_splitter.setSizes([left, center, right])

        if hasattr(self, "_left_panel_toggle_btn"):
            self._left_panel_toggle_btn.blockSignals(True)
            self._left_panel_toggle_btn.setChecked(self._left_panel_visible)
            if self._left_panel_visible:
                self._left_panel_toggle_btn.setText("◀")
                self._left_panel_toggle_btn.setToolTip("Collapse left panel")
            else:
                self._left_panel_toggle_btn.setText("▶")
                self._left_panel_toggle_btn.setToolTip("Expand left panel")
            self._left_panel_toggle_btn.blockSignals(False)

        if hasattr(self, "_right_panel_toggle_btn"):
            self._right_panel_toggle_btn.blockSignals(True)
            self._right_panel_toggle_btn.setChecked(self._right_panel_visible)
            if self._right_panel_visible:
                self._right_panel_toggle_btn.setText("▶")
                self._right_panel_toggle_btn.setToolTip("Collapse right panel")
            else:
                self._right_panel_toggle_btn.setText("◀")
                self._right_panel_toggle_btn.setToolTip("Expand right panel")
            self._right_panel_toggle_btn.blockSignals(False)

    def _on_scope_selector_changed(self, signal_name: str) -> None:
        if not signal_name or signal_name not in self._stacked_signals:
            return
        self._stacked_active_signal = signal_name
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
            self._stacked_active_signal = None
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
        self._rebuild_stacked_statistics_cache()

        previous_visible = set(self._stacked_signal_list.get_visible_signals())
        previous_active = self._stacked_active_signal

        self._stacked_signal_list.set_signals(list(valid_signals.keys()))
        self._apply_stacked_trace_colors()

        default_visible = {next(iter(valid_signals))} if not previous_visible else previous_visible
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
        self._sync_scope_selector()
        self._rebuild_stacked_plots(self._current_result)
        self._update_stacked_measurements()

    def _on_stacked_signal_selected(self, signal_name: str) -> None:
        if signal_name in self._stacked_signals:
            self._stacked_active_signal = signal_name
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
            self._refresh_bottom_controls_enabled()
            return

        points_per_signal = self._stacked_target_points_per_signal(len(signal_items))

        for idx, (name, values) in enumerate(signal_items):
            t, plot_values = self._decimate_stacked_for_display(
                time,
                values,
                max_points=points_per_signal,
            )

            # Determine color for this signal
            color = self._stacked_signal_list.get_signal_color(name)
            if color is None:
                color = palette[idx % len(palette)]
            color_override = self._trace_style_color(name)
            line_color = color_override if color_override is not None else color
            r, g, b = line_color
            hex_color = f"#{r:02x}{g:02x}{b:02x}"

            # Stats for this signal
            sig_stats = self._stacked_signal_stats.get(name, {})
            is_active = (name == self._stacked_active_signal)

            panel = QFrame()
            panel_layout = QVBoxLayout(panel)
            panel_layout.setContentsMargins(0, 0, 0, 0)
            panel_layout.setSpacing(0)

            # --- Header row: colored dot + name + mini stats ---
            header_widget = QWidget()
            header_layout = QHBoxLayout(header_widget)
            header_layout.setContentsMargins(12, 8, 12, 6)
            header_layout.setSpacing(8)

            dot_and_name = QLabel(f'●  {name}')
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
            plot = pg.PlotWidget()
            plot.setMinimumHeight(220)
            grid_alpha = 0.18 if (self._theme and self._theme.is_dark) else 0.28
            if not self._stacked_grid_enabled:
                grid_alpha = 0.0
            plot.showGrid(x=self._stacked_grid_enabled, y=self._stacked_grid_enabled, alpha=grid_alpha)
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

            panel_layout.addWidget(plot)

            # --- Apply theming ---
            if self._theme is not None:
                c = self._theme.colors
                plot.setBackground(c.plot_background)
                for axis_name in ("left", "bottom"):
                    axis = item.getAxis(axis_name)
                    axis.setPen(pg.mkPen(c.plot_axis))
                    axis.setTickPen(pg.mkPen(c.plot_axis))
                    axis.setTextPen(pg.mkPen(c.plot_text))
                plot.showGrid(
                    x=self._stacked_grid_enabled,
                    y=self._stacked_grid_enabled,
                    alpha=0.18 if self._theme.is_dark else 0.28,
                )

                header_bg = c.panel_header if is_active else c.panel_background
                name_weight = "700" if is_active else "600"
                dot_and_name.setStyleSheet(
                    f"color: {hex_color}; font-weight: {name_weight}; font-size: 12px;"
                )
                if sig_stats:
                    stats_lbl.setStyleSheet(
                        f"color: {c.foreground_muted}; font-size: 10px; font-family: monospace; font-weight: 500;"
                    )
                # Panel border: slim left accent + softer card fill.
                panel.setStyleSheet(
                    f"""
                    QFrame {{
                        background-color: {c.panel_background};
                        border: 1px solid {c.panel_border};
                        border-left: 3px solid {hex_color};
                        border-radius: 10px;
                    }}
                    """
                )
                header_widget.setStyleSheet(
                    f"background-color: {header_bg}; border-radius: 7px; margin: 0; border: 1px solid {c.panel_border};"
                )
            else:
                dot_and_name.setStyleSheet(f"color: {hex_color}; font-weight: 600; font-size: 12px;")
                if sig_stats:
                    stats_lbl.setStyleSheet("color: #666; font-size: 10px; font-family: monospace;")

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
