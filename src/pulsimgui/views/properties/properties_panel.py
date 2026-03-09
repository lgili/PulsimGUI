"""Properties panel for editing component parameters."""

from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.component import (
    C_BLOCK_IO_LIMITS,
    HIDDEN_PARAMS,
    MUX_CHANNEL_LIMITS,
    SCOPE_CHANNEL_LIMITS,
    THERMAL_PORT_PARAMETER,
    Component,
    ComponentType,
    get_control_sample_time,
    set_cblock_input_count,
    set_cblock_output_count,
    set_control_sample_time,
    set_demux_output_count,
    set_mux_input_count,
    set_scope_channel_count,
    set_sum_input_count,
    set_pwm_duty_input_enabled,
    set_thermal_port_enabled,
    supports_electrothermal_parameters,
    DUTY_INPUT_PARAMETER,
)
from pulsimgui.services.theme_service import (
    DARK_THEME,
    LIGHT_THEME,
    Theme,
    ThemeService,
)
from pulsimgui.resources.icons import IconService
from pulsimgui.utils.si_prefix import parse_si_value
from pulsimgui.views.library.library_panel import create_component_icon


class SectionHeader(QWidget):
    """A styled section header with icon and title."""

    def __init__(self, icon_name: str, title: str, icon_color: str = "#3b82f6", parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_color = icon_color
        self._color_bar: QFrame | None = None
        self._icon_label: QLabel | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 4)
        layout.setSpacing(8)

        # Color bar
        self._color_bar = QFrame()
        self._color_bar.setFixedSize(3, 18)
        layout.addWidget(self._color_bar)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(16, 16)
        layout.addWidget(self._icon_label)

        # Title
        self._title_label = QLabel(title)
        layout.addWidget(self._title_label)

        layout.addStretch()
        self.apply_theme(None, icon_color)

    def apply_theme(self, theme: Theme | None, accent_color: str | None = None) -> None:
        """Apply theme to section header visuals."""
        if accent_color is not None:
            self._icon_color = accent_color
        if self._color_bar is not None:
            self._color_bar.setStyleSheet(
                f"background-color: {self._icon_color}; border-radius: 1px;"
            )
        if self._icon_label is not None:
            icon = IconService.get_icon(self._icon_name, self._icon_color, 14)
            self._icon_label.setPixmap(icon.pixmap(14, 14))
        if theme is None:
            self._title_label.setStyleSheet("font-weight: 600; font-size: 12px;")
            return
        self._title_label.setStyleSheet(
            f"font-weight: 600; font-size: 12px; letter-spacing: 0.2px; color: {theme.colors.foreground};"
        )


class AutoSelectLineEdit(QLineEdit):
    """LineEdit that auto-selects all text when focused."""

    def focusInEvent(self, event):
        """Handle the Qt focusInEvent callback."""
        super().focusInEvent(event)
        # Use timer to select after focus is fully set
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.selectAll)


class SIValueWidget(QWidget):
    """Widget with line edit for SI value and fixed unit label."""

    value_changed = Signal(float)

    def __init__(self, unit: str = "", parent=None):
        super().__init__(parent)
        self._unit = unit
        self._value = 0.0
        self._theme: Theme | None = None
        self._invalid = False
        self._unit_label: QLabel | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = AutoSelectLineEdit()
        self._edit.setMinimumWidth(80)
        self._edit.returnPressed.connect(self._on_return_pressed)
        self._edit.editingFinished.connect(self._on_editing_finished)
        self._edit.textChanged.connect(self._validate)
        layout.addWidget(self._edit)

        if unit:
            self._unit_label = QLabel(unit)
            self._unit_label.setMinimumWidth(20)
            layout.addWidget(self._unit_label)
        self._apply_validation_style()

    @property
    def value(self) -> float:
        """Return the current numeric value represented by this editor."""
        return self._value

    @value.setter
    def value(self, val: float) -> None:
        """Set the numeric value represented by this editor."""
        self._value = val
        self._edit.setText(self._format_value(val))

    def _format_value(self, val: float) -> str:
        """Format value with SI prefix but without unit."""
        if val == 0:
            return "0"

        prefixes = [
            (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"),
            (1, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"), (1e-12, "p")
        ]

        for scale, prefix in prefixes:
            if abs(val) >= scale:
                scaled = val / scale
                if scaled == int(scaled):
                    return f"{int(scaled)}{prefix}"
                else:
                    return f"{scaled:.3g}{prefix}"

        return f"{val:.3g}"

    def _validate(self) -> None:
        """Validate input and update style."""
        text = self._edit.text().strip()
        if not text:
            self._invalid = False
            self._apply_validation_style()
            return

        try:
            parse_si_value(text)
            self._invalid = False
            self._apply_validation_style()
        except ValueError:
            self._invalid = True
            self._apply_validation_style()

    def _on_return_pressed(self) -> None:
        """Handle Enter key press - update value immediately."""
        self._apply_value()

    def _on_editing_finished(self) -> None:
        """Parse value when editing is finished."""
        self._apply_value()

    def _apply_value(self) -> None:
        """Apply the current text value."""
        text = self._edit.text().strip()
        if not text:
            return

        try:
            new_value = parse_si_value(text)
            if new_value != self._value:
                self._value = new_value
                self._edit.setText(self._format_value(self._value))
                self.value_changed.emit(self._value)
        except ValueError:
            self._edit.setText(self._format_value(self._value))

    def commit_pending_value(self) -> None:
        """Commit the current text to numeric value even if focus has not changed."""
        self._apply_value()

    def _apply_validation_style(self) -> None:
        """Apply current input style, respecting theme and validation state."""
        if self._theme is None:
            if self._invalid:
                self._edit.setStyleSheet("border: 1px solid #ef4444;")
            else:
                self._edit.setStyleSheet("")
            if self._unit_label is not None:
                self._unit_label.setStyleSheet("color: #6b7280; font-size: 11px;")
            return

        c = self._theme.colors
        border = c.error if self._invalid else c.input_border
        self._edit.setStyleSheet(
            f"border: 1px solid {border}; border-radius: 4px; "
            f"padding: 2px 6px; background-color: {c.input_background}; color: {c.foreground};"
        )
        if self._unit_label is not None:
            self._unit_label.setStyleSheet(f"color: {c.foreground_muted}; font-size: 11px;")

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme-aware visuals."""
        self._theme = theme
        self._apply_validation_style()


class WaveformEditorDialog(QDialog):
    """Dialog for editing waveform parameters."""

    def __init__(self, waveform: dict, unit: str = "V", parent=None):
        super().__init__(parent)
        self._waveform = waveform.copy()
        self._unit = unit

        self.setWindowTitle("Edit Waveform")
        self.setMinimumWidth(350)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Waveform type selector
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        self._type_combo.addItems(["DC", "Pulse", "Sine", "PWL"])
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        type_layout.addWidget(self._type_combo)
        type_layout.addStretch()
        layout.addLayout(type_layout)

        # Stacked widget for different waveform parameters
        self._stack = QStackedWidget()

        # DC page
        dc_page = QWidget()
        dc_layout = QFormLayout(dc_page)
        self._dc_value = SIValueWidget(self._unit)
        dc_layout.addRow("Value:", self._dc_value)
        self._stack.addWidget(dc_page)

        # Pulse page
        pulse_page = QWidget()
        pulse_layout = QFormLayout(pulse_page)
        self._pulse_v1 = SIValueWidget(self._unit)
        self._pulse_v2 = SIValueWidget(self._unit)
        self._pulse_td = SIValueWidget("s")
        self._pulse_tr = SIValueWidget("s")
        self._pulse_tf = SIValueWidget("s")
        self._pulse_pw = SIValueWidget("s")
        self._pulse_per = SIValueWidget("s")
        pulse_layout.addRow("V1 (low):", self._pulse_v1)
        pulse_layout.addRow("V2 (high):", self._pulse_v2)
        pulse_layout.addRow("Delay:", self._pulse_td)
        pulse_layout.addRow("Rise time:", self._pulse_tr)
        pulse_layout.addRow("Fall time:", self._pulse_tf)
        pulse_layout.addRow("Pulse width:", self._pulse_pw)
        pulse_layout.addRow("Period:", self._pulse_per)
        self._stack.addWidget(pulse_page)

        # Sine page
        sine_page = QWidget()
        sine_layout = QFormLayout(sine_page)
        self._sine_offset = SIValueWidget(self._unit)
        self._sine_amp = SIValueWidget(self._unit)
        self._sine_freq = SIValueWidget("Hz")
        self._sine_phase = SIValueWidget("°")
        sine_layout.addRow("Offset:", self._sine_offset)
        sine_layout.addRow("Amplitude:", self._sine_amp)
        sine_layout.addRow("Frequency:", self._sine_freq)
        sine_layout.addRow("Phase:", self._sine_phase)
        self._stack.addWidget(sine_page)

        # PWL page
        pwl_page = QWidget()
        pwl_layout = QVBoxLayout(pwl_page)
        pwl_layout.addWidget(QLabel("Time-Value pairs (one per line):"))
        pwl_layout.addWidget(QLabel("Format: time, value"))
        self._pwl_edit = AutoSelectLineEdit()
        self._pwl_edit.setPlaceholderText("0, 0\n1m, 5\n2m, 5\n3m, 0")
        from PySide6.QtWidgets import QTextEdit
        self._pwl_text = QTextEdit()
        self._pwl_text.setMaximumHeight(100)
        pwl_layout.addWidget(self._pwl_text)
        self._stack.addWidget(pwl_page)

        layout.addWidget(self._stack)

        # Dialog buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Load current values
        self._load_waveform()

    def _load_waveform(self):
        """Load current waveform values into widgets."""
        wf_type = self._waveform.get("type", "dc").upper()

        if wf_type == "DC":
            self._type_combo.setCurrentIndex(0)
            self._dc_value.value = self._waveform.get("value", 0)
        elif wf_type == "PULSE":
            self._type_combo.setCurrentIndex(1)
            self._pulse_v1.value = self._waveform.get("v1", 0)
            self._pulse_v2.value = self._waveform.get("v2", 5)
            self._pulse_td.value = self._waveform.get("td", 0)
            self._pulse_tr.value = self._waveform.get("tr", 1e-9)
            self._pulse_tf.value = self._waveform.get("tf", 1e-9)
            self._pulse_pw.value = self._waveform.get("pw", 1e-3)
            self._pulse_per.value = self._waveform.get("per", 2e-3)
        elif wf_type == "SINE":
            self._type_combo.setCurrentIndex(2)
            self._sine_offset.value = self._waveform.get("offset", 0)
            self._sine_amp.value = self._waveform.get("amplitude", 1)
            self._sine_freq.value = self._waveform.get("frequency", 1000)
            self._sine_phase.value = self._waveform.get("phase", 0)
        elif wf_type == "PWL":
            self._type_combo.setCurrentIndex(3)
            points = self._waveform.get("points", [])
            lines = [f"{t}, {v}" for t, v in points]
            self._pwl_text.setText("\n".join(lines))

    def _on_type_changed(self, type_name: str):
        """Handle waveform type change."""
        index = {"DC": 0, "Pulse": 1, "Sine": 2, "PWL": 3}.get(type_name, 0)
        self._stack.setCurrentIndex(index)

    def get_waveform(self) -> dict:
        """Get the edited waveform data."""
        type_name = self._type_combo.currentText().lower()

        if type_name == "dc":
            return {"type": "dc", "value": self._dc_value.value}
        elif type_name == "pulse":
            return {
                "type": "pulse",
                "v1": self._pulse_v1.value,
                "v2": self._pulse_v2.value,
                "td": self._pulse_td.value,
                "tr": self._pulse_tr.value,
                "tf": self._pulse_tf.value,
                "pw": self._pulse_pw.value,
                "per": self._pulse_per.value,
            }
        elif type_name == "sine":
            return {
                "type": "sine",
                "offset": self._sine_offset.value,
                "amplitude": self._sine_amp.value,
                "frequency": self._sine_freq.value,
                "phase": self._sine_phase.value,
            }
        elif type_name == "pwl":
            points = []
            for line in self._pwl_text.toPlainText().strip().split("\n"):
                if "," in line:
                    parts = line.split(",")
                    if len(parts) >= 2:
                        try:
                            t = parse_si_value(parts[0].strip())
                            v = parse_si_value(parts[1].strip())
                            points.append((t, v))
                        except ValueError:
                            pass
            return {"type": "pwl", "points": points}

        return {"type": "dc", "value": 0}


class IconButton(QPushButton):
    """A styled icon button."""

    def __init__(self, icon_name: str, tooltip: str = "", size: int = 28, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_color = "#6b7280"
        self._theme: Theme | None = None
        self._active = False

        self.setFixedSize(size, size)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_icon()
        self._update_style()

    def _update_icon(self):
        icon = IconService.get_icon(self._icon_name, self._icon_color, 16)
        self.setIcon(icon)

    def _update_style(self):
        if self._theme is None:
            if self._active:
                self.setStyleSheet("""
                    QPushButton {
                        background-color: #dbeafe;
                        border: 1px solid #3b82f6;
                        border-radius: 6px;
                    }
                    QPushButton:hover {
                        background-color: #bfdbfe;
                    }
                """)
            else:
                self.setStyleSheet("""
                    QPushButton {
                        background-color: transparent;
                        border: 1px solid #e5e7eb;
                        border-radius: 6px;
                    }
                    QPushButton:hover {
                        background-color: #f3f4f6;
                        border-color: #d1d5db;
                    }
                    QPushButton:pressed {
                        background-color: #e5e7eb;
                    }
                """)
            return

        c = self._theme.colors
        if self._active:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: {c.tree_item_selected};
                    border: 1px solid {c.primary};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {c.menu_hover};
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    border: 1px solid {c.panel_border};
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background-color: {c.menu_hover};
                    border-color: {c.border};
                }}
                QPushButton:pressed {{
                    background-color: {c.tree_item_selected_inactive};
                }}
            """)

    def set_active(self, active: bool):
        """Set button active state."""
        self._active = active
        self._update_style()

    def apply_theme(self, theme: Theme, icon_color: str | None = None) -> None:
        """Apply themed icon and button surface colors."""
        self._theme = theme
        if icon_color is not None:
            self._icon_color = icon_color
        self._update_icon()
        self._update_style()


class PropertiesPanel(QWidget):
    """Panel for editing selected component properties."""

    property_changed = Signal(str, object)
    name_changed = Signal(str)
    net_label_pair_requested = Signal(str, str)

    def __init__(self, theme_service: ThemeService | None = None, parent=None):
        super().__init__(parent)
        self.setObjectName("PropertiesPanelRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._theme_service = theme_service
        self._theme: Theme | None = None
        self._component: Component | None = None
        self._components: list[Component] = []
        self._widgets: dict[str, QWidget] = {}
        self._scope_channel_layout = None
        self._mux_channel_layout = None
        self._demux_channel_layout = None
        self._cblock_path_edit: AutoSelectLineEdit | None = None
        self._cblock_extra_cflags_edit: AutoSelectLineEdit | None = None
        self._cblock_create_btn: QPushButton | None = None
        self._cblock_open_btn: QPushButton | None = None
        self._cblock_compile_btn: QPushButton | None = None
        self._cblock_sample_time_edit: SIValueWidget | None = None
        self._main_layout: QVBoxLayout | None = None
        self._show_position_controls = False
        self._compact_mode = False
        self._dark_mode = False
        self._info_header: SectionHeader | None = None
        self._params_header: SectionHeader | None = None
        self._pos_header: SectionHeader | None = None
        self._summary_icon: QLabel | None = None
        self._summary_title: QLabel | None = None
        self._summary_subtitle: QLabel | None = None
        self._type_badge: QLabel | None = None
        self._pin_count_badge: QLabel | None = None
        self._param_count_badge: QLabel | None = None
        self._params_count_label: QLabel | None = None
        self._name_field_label: QLabel | None = None
        self._net_label_pair_btn: QPushButton | None = None

        self._setup_ui()
        if self._theme_service is not None:
            self._theme_service.theme_changed.connect(self.apply_theme)
            self.apply_theme(self._theme_service.current_theme)
        else:
            self.apply_theme(LIGHT_THEME)

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        self._main_layout = layout
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Component info section
        self._info_container = QWidget()
        self._info_container.setObjectName("PropertiesSectionCard")
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(12, 10, 12, 12)
        info_layout.setSpacing(8)

        self._info_header = SectionHeader("info", "Component", "#3b82f6")
        info_layout.addWidget(self._info_header)

        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(12)
        self._summary_icon = QLabel()
        self._summary_icon.setFixedSize(44, 44)
        self._summary_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        summary_layout.addWidget(self._summary_icon)

        summary_text = QWidget()
        summary_text_layout = QVBoxLayout(summary_text)
        summary_text_layout.setContentsMargins(0, 0, 0, 0)
        summary_text_layout.setSpacing(1)
        self._summary_title = QLabel("No component selected")
        self._summary_subtitle = QLabel("Select a component to edit parameters")
        self._summary_title.setObjectName("PropertiesSummaryTitle")
        self._summary_subtitle.setObjectName("PropertiesSummarySubtitle")
        summary_text_layout.addWidget(self._summary_title)
        summary_text_layout.addWidget(self._summary_subtitle)
        summary_layout.addWidget(summary_text, 1)
        info_layout.addWidget(summary)

        badges = QWidget()
        badges_layout = QHBoxLayout(badges)
        badges_layout.setContentsMargins(0, 0, 0, 0)
        badges_layout.setSpacing(6)
        self._type_badge = QLabel("Type")
        self._type_badge.setObjectName("PropertiesInfoBadge")
        badges_layout.addWidget(self._type_badge)
        self._pin_count_badge = QLabel("Pins: 0")
        self._pin_count_badge.setObjectName("PropertiesInfoBadge")
        badges_layout.addWidget(self._pin_count_badge)
        self._param_count_badge = QLabel("Params: 0")
        self._param_count_badge.setObjectName("PropertiesInfoBadge")
        badges_layout.addWidget(self._param_count_badge)
        badges_layout.addStretch(1)
        info_layout.addWidget(badges)

        # Type and name
        form = QWidget()
        form_layout = QFormLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self._type_label = QLabel("-")
        self._type_label.setObjectName("PropertiesTypeValue")
        form_layout.addRow("Type:", self._type_label)

        self._name_edit = AutoSelectLineEdit()
        self._name_edit.setPlaceholderText("Component name")
        self._name_edit.returnPressed.connect(self._on_name_changed)
        self._name_edit.editingFinished.connect(self._on_name_changed)
        name_row = QWidget()
        name_row_layout = QHBoxLayout(name_row)
        name_row_layout.setContentsMargins(0, 0, 0, 0)
        name_row_layout.setSpacing(6)
        name_row_layout.addWidget(self._name_edit, 1)
        self._net_label_pair_btn = QPushButton("Go to Pair")
        self._net_label_pair_btn.setObjectName("NetPairButton")
        self._net_label_pair_btn.setToolTip("Jump to linked Goto/From with same label")
        self._net_label_pair_btn.clicked.connect(self._on_net_label_pair_clicked)
        self._net_label_pair_btn.hide()
        name_row_layout.addWidget(self._net_label_pair_btn, 0)
        self._name_field_label = QLabel("Name:")
        form_layout.addRow(self._name_field_label, name_row)

        info_layout.addWidget(form)

        layout.addWidget(self._info_container)

        # Parameters section
        self._params_container = QWidget()
        self._params_container.setObjectName("PropertiesSectionCard")
        params_container_layout = QVBoxLayout(self._params_container)
        params_container_layout.setContentsMargins(12, 10, 12, 12)
        params_container_layout.setSpacing(8)

        self._params_header = SectionHeader("sliders", "Parameters", "#10b981")
        params_container_layout.addWidget(self._params_header)

        params_meta = QWidget()
        params_meta_layout = QHBoxLayout(params_meta)
        params_meta_layout.setContentsMargins(0, 0, 0, 0)
        params_meta_layout.setSpacing(8)
        self._params_count_label = QLabel("0 editable parameters")
        self._params_count_label.setObjectName("PropertiesParamsCount")
        params_meta_layout.addWidget(self._params_count_label)
        params_meta_layout.addStretch(1)
        params_container_layout.addWidget(params_meta)

        # Parameters scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setMinimumHeight(270)
        scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self._params_widget = QWidget()
        self._params_layout = QFormLayout(self._params_widget)
        self._params_layout.setContentsMargins(0, 0, 0, 0)
        self._params_layout.setHorizontalSpacing(12)
        self._params_layout.setVerticalSpacing(9)
        self._params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        self._params_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        scroll.setWidget(self._params_widget)

        params_container_layout.addWidget(scroll)
        self._params_container.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self._params_container, 1)

        self._scroll = scroll

        # Position section
        self._pos_container = QWidget()
        self._pos_container.setObjectName("PropertiesSectionCard")
        pos_layout = QVBoxLayout(self._pos_container)
        pos_layout.setContentsMargins(12, 10, 12, 12)
        pos_layout.setSpacing(8)

        self._pos_header = SectionHeader("move", "Position", "#f59e0b")
        pos_layout.addWidget(self._pos_header)

        pos_form = QWidget()
        pos_form_layout = QHBoxLayout(pos_form)
        pos_form_layout.setContentsMargins(0, 0, 0, 0)
        pos_form_layout.setSpacing(8)

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(-10000, 10000)
        self._x_spin.setDecimals(0)
        self._x_spin.setPrefix("X: ")
        self._x_spin.setSingleStep(10)
        self._x_spin.valueChanged.connect(lambda v: self._on_position_changed("x", v))
        pos_form_layout.addWidget(self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(-10000, 10000)
        self._y_spin.setDecimals(0)
        self._y_spin.setPrefix("Y: ")
        self._y_spin.setSingleStep(10)
        self._y_spin.valueChanged.connect(lambda v: self._on_position_changed("y", v))
        pos_form_layout.addWidget(self._y_spin)

        pos_layout.addWidget(pos_form)
        layout.addWidget(self._pos_container, 0)

        layout.addStretch()

        # No selection label
        self._no_selection_label = QLabel("No component selected")
        self._no_selection_label.setObjectName("PropertiesEmptyState")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._no_selection_label)

        # Initially hide everything except no selection label
        self._info_container.hide()
        self._params_container.hide()
        self._pos_container.hide()

    def set_component(self, component: Component | None) -> None:
        """Set the component to display/edit."""
        self._component = component
        self._components = [component] if component else []
        self._update_display()

    def set_components(self, components: list[Component]) -> None:
        """Set multiple components for multi-selection editing."""
        self._components = components
        self._component = components[0] if components else None
        self._update_display()

    def _update_display(self) -> None:
        """Update the panel display based on current selection."""
        self._clear_params()

        if not self._component:
            self._no_selection_label.show()
            self._info_container.hide()
            self._params_container.hide()
            self._pos_container.hide()
            if self._summary_icon is not None:
                self._summary_icon.clear()
            if self._summary_title is not None:
                self._summary_title.setText("No component selected")
            if self._summary_subtitle is not None:
                self._summary_subtitle.setText("Select a component to edit parameters")
            if self._name_field_label is not None:
                self._name_field_label.setText("Name:")
            self._update_net_label_pair_button()
            self._update_component_metrics()
            return

        self._no_selection_label.hide()
        self._info_container.show()
        self._pos_container.setVisible(self._show_position_controls)

        # Update component info
        type_name = self._component.type.name.replace("_", " ").title()
        self._type_label.setText(type_name)
        is_net_label = self._is_net_label_component(self._component)
        if self._name_field_label is not None:
            self._name_field_label.setText("Net Label:" if is_net_label else "Name:")
        if is_net_label:
            self._name_edit.setPlaceholderText("NET1")
            self._name_edit.setText(self._net_label_text(self._component))
        else:
            self._name_edit.setPlaceholderText("Component name")
            self._name_edit.setText(self._component.name)
        if self._summary_title is not None:
            title = self._net_label_text(self._component) if is_net_label else self._component.name
            self._summary_title.setText(title or type_name)
        if self._summary_subtitle is not None:
            if len(self._components) > 1:
                self._summary_subtitle.setText(f"{len(self._components)} components selected")
            else:
                self._summary_subtitle.setText(type_name)
        if self._summary_icon is not None:
            dark_mode = bool(self._theme and self._theme.is_dark)
            icon_color = self._theme.colors.foreground_muted if self._theme else "#6b7280"
            self._summary_icon.setPixmap(
                create_component_icon(
                    self._component.type,
                    size=36,
                    color=icon_color,
                    dark_mode=dark_mode,
                )
            )

        # Update position
        self._x_spin.blockSignals(True)
        self._y_spin.blockSignals(True)

        self._x_spin.setValue(self._component.x)
        self._y_spin.setValue(self._component.y)

        self._x_spin.blockSignals(False)
        self._y_spin.blockSignals(False)

        # Create parameter widgets
        self._create_param_widgets()
        self._params_container.setVisible(self._should_show_params_container())
        self._update_net_label_pair_button()
        self._update_component_metrics()
        self._apply_compact_scroll_limits_for_component()
        if self._theme is not None:
            self.apply_theme(self._theme)

    def _should_show_params_container(self) -> bool:
        """Return whether the parameters section should be visible."""
        if self._component is None:
            return False

        comp_type = self._component.type
        if comp_type in {
            ComponentType.ELECTRICAL_SCOPE,
            ComponentType.THERMAL_SCOPE,
            ComponentType.SIGNAL_MUX,
            ComponentType.SIGNAL_DEMUX,
            ComponentType.C_BLOCK,
        }:
            return True

        return self._editable_parameter_count() > 0

    def _clear_params(self) -> None:
        """Clear all parameter widgets."""
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()
        self._scope_channel_layout = None
        self._mux_channel_layout = None
        self._demux_channel_layout = None
        self._cblock_path_edit = None
        self._cblock_extra_cflags_edit = None
        self._cblock_create_btn = None
        self._cblock_open_btn = None
        self._cblock_compile_btn = None
        self._cblock_sample_time_edit = None

    def _editable_parameter_count(self) -> int:
        if self._component is None:
            return 0
        hidden = HIDDEN_PARAMS.get(self._component.type, frozenset())
        return sum(
            1
            for key in self._component.parameters
            if key not in hidden
            and not (
                self._component.type in {ComponentType.GOTO_LABEL, ComponentType.FROM_LABEL}
                and key == "net_label"
            )
        )

    def _update_component_metrics(self) -> None:
        if self._component is None:
            if self._type_badge is not None:
                self._type_badge.setText("Type")
            if self._pin_count_badge is not None:
                self._pin_count_badge.setText("Pins: 0")
            if self._param_count_badge is not None:
                self._param_count_badge.setText("Params: 0")
            if self._params_count_label is not None:
                self._params_count_label.setText("0 editable parameters")
            return

        type_name = self._component.type.name.replace("_", " ").title()
        pin_count = len(self._component.pins)
        param_count = self._editable_parameter_count()

        if self._type_badge is not None:
            self._type_badge.setText(type_name)
        if self._pin_count_badge is not None:
            self._pin_count_badge.setText(f"Pins: {pin_count}")
        if self._param_count_badge is not None:
            self._param_count_badge.setText(f"Params: {param_count}")
        if self._params_count_label is not None:
            self._params_count_label.setText(
                f"{param_count} editable parameter{'s' if param_count != 1 else ''}"
            )

    def _create_param_widgets(self) -> None:
        """Create widgets for component parameters."""
        if not self._component:
            return

        comp_type = self._component.type
        if comp_type in (ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE):
            self._create_scope_param_widgets()
            return
        if comp_type == ComponentType.SIGNAL_MUX:
            self._create_mux_param_widgets()
            return
        if comp_type == ComponentType.SIGNAL_DEMUX:
            self._create_demux_param_widgets()
            return
        if comp_type == ComponentType.C_BLOCK:
            self._create_cblock_param_widgets()
            return

        params = self._component.parameters

        _hidden = HIDDEN_PARAMS.get(comp_type, frozenset())
        for name, value in params.items():
            if name in _hidden:
                continue
            if comp_type in {ComponentType.GOTO_LABEL, ComponentType.FROM_LABEL} and name == "net_label":
                # The top field already edits net_label for router labels.
                continue
            widget = self._create_widget_for_value(name, value)
            if widget:
                label = name.replace("_", " ").title()
                self._params_layout.addRow(f"{label}:", widget)
                self._widgets[name] = widget

    def _create_widget_for_value(self, name: str, value: Any) -> QWidget | None:
        """Create appropriate widget for a parameter value."""
        if isinstance(value, bool):
            checkbox = QCheckBox()
            checkbox.setChecked(value)
            checkbox.stateChanged.connect(
                lambda: self._on_param_changed(name, checkbox.isChecked())
            )
            return checkbox

        elif isinstance(value, (int, float)):
            unit = self._get_unit_for_param(name)
            widget = SIValueWidget(unit)
            widget.value = value
            if self._theme is not None:
                widget.apply_theme(self._theme)
            widget.value_changed.connect(lambda v: self._on_param_changed(name, v))
            return widget

        elif isinstance(value, str):
            edit = AutoSelectLineEdit(value)
            edit.returnPressed.connect(
                lambda: self._on_param_changed(name, edit.text())
            )
            edit.editingFinished.connect(
                lambda: self._on_param_changed(name, edit.text())
            )
            return edit

        elif isinstance(value, dict):
            if "type" in value:
                return self._create_waveform_widget(name, value)

        return None

    def _create_waveform_widget(self, name: str, waveform: dict) -> QWidget:
        """Create widget for waveform parameter."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Waveform type label
        wf_type = waveform.get("type", "dc").upper()
        type_label = QLabel(wf_type)
        type_label.setObjectName("WaveformTypeBadge")
        layout.addWidget(type_label)

        # Value preview
        if wf_type == "DC":
            val = waveform.get("value", 0)
            preview = QLabel(f"{val}")
        elif wf_type == "PULSE":
            v1 = waveform.get("v1", 0)
            v2 = waveform.get("v2", 5)
            preview = QLabel(f"{v1} → {v2}")
        elif wf_type == "SINE":
            amp = waveform.get("amplitude", 1)
            freq = waveform.get("frequency", 1000)
            preview = QLabel(f"{amp} @ {freq}Hz")
        else:
            preview = QLabel("...")

        preview.setObjectName("WaveformPreviewLabel")
        layout.addWidget(preview)

        layout.addStretch()

        # Edit button
        edit_btn = QPushButton("Edit")
        edit_btn.setObjectName("WaveformEditButton")
        edit_btn.setFixedWidth(50)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(lambda: self._on_edit_waveform(name, waveform))
        layout.addWidget(edit_btn)

        return widget

    # --- Scope parameter editors -------------------------------------------------

    def _create_scope_param_widgets(self) -> None:
        if not self._component:
            return

        params = self._component.parameters
        channel_count = params.get("channel_count", len(params.get("channels", [])) or 1)

        count_spin = QSpinBox()
        count_spin.setRange(*SCOPE_CHANNEL_LIMITS)
        count_spin.setValue(channel_count)
        count_spin.valueChanged.connect(self._on_scope_channel_count_changed)
        self._params_layout.addRow("Channels:", count_spin)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._scope_channel_layout = layout
        self._params_layout.addRow("Labels:", container)
        self._rebuild_scope_channel_rows()

    def _rebuild_scope_channel_rows(self) -> None:
        if not (self._scope_channel_layout and self._component):
            return

        self._clear_dynamic_layout(self._scope_channel_layout)
        channels = self._component.parameters.get("channels", [])

        for idx, channel in enumerate(channels):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            idx_label = QLabel(f"{idx + 1}:")
            idx_label.setFixedWidth(20)
            idx_label.setObjectName("ChannelIndexLabel")
            row_layout.addWidget(idx_label)

            label_edit = AutoSelectLineEdit(channel.get("label", ""))
            label_edit.setPlaceholderText(f"CH{idx + 1}")
            label_edit.returnPressed.connect(
                partial(self._on_scope_channel_label_changed, idx, label_edit)
            )
            label_edit.editingFinished.connect(
                partial(self._on_scope_channel_label_changed, idx, label_edit)
            )
            row_layout.addWidget(label_edit)

            self._scope_channel_layout.addWidget(row)

    def _on_scope_channel_count_changed(self, value: int) -> None:
        if not self._component:
            return

        set_scope_channel_count(self._component, value)
        self.property_changed.emit("channel_count", value)
        self._rebuild_scope_channel_rows()

    def _on_scope_channel_label_changed(self, index: int, widget: QLineEdit) -> None:
        if not self._component:
            return

        text = widget.text().strip()
        if not text:
            prefix = "CH" if self._component.type == ComponentType.ELECTRICAL_SCOPE else "T"
            text = f"{prefix}{index + 1}"
            widget.setText(text)

        channels = self._component.parameters.get("channels", [])
        if index >= len(channels):
            return

        if channels[index].get("label") != text:
            channels[index]["label"] = text
            self.property_changed.emit("channels", channels)

    # --- Mux / Demux parameter editors ------------------------------------------

    def _create_mux_param_widgets(self) -> None:
        if not self._component:
            return

        count = self._component.parameters.get("input_count", 2)
        spin = QSpinBox()
        spin.setRange(*MUX_CHANNEL_LIMITS)
        spin.setValue(count)
        spin.valueChanged.connect(self._on_mux_count_changed)
        self._params_layout.addRow("Inputs:", spin)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._mux_channel_layout = layout
        self._params_layout.addRow("Labels:", container)
        self._rebuild_mux_channel_rows()

    def _create_demux_param_widgets(self) -> None:
        if not self._component:
            return

        count = self._component.parameters.get("output_count", 2)
        spin = QSpinBox()
        spin.setRange(*MUX_CHANNEL_LIMITS)
        spin.setValue(count)
        spin.valueChanged.connect(self._on_demux_count_changed)
        self._params_layout.addRow("Outputs:", spin)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._demux_channel_layout = layout
        self._params_layout.addRow("Labels:", container)
        self._rebuild_demux_channel_rows()

    def _rebuild_mux_channel_rows(self) -> None:
        if not (self._mux_channel_layout and self._component):
            return

        self._clear_dynamic_layout(self._mux_channel_layout)
        labels = self._component.parameters.get("channel_labels", [])

        for idx, label in enumerate(labels):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            idx_label = QLabel(f"{idx + 1}:")
            idx_label.setFixedWidth(20)
            idx_label.setObjectName("ChannelIndexLabel")
            row_layout.addWidget(idx_label)

            edit = AutoSelectLineEdit(label)
            edit.setPlaceholderText(f"In{idx + 1}")
            edit.returnPressed.connect(
                partial(self._on_bus_channel_label_changed, "mux", idx, edit)
            )
            edit.editingFinished.connect(
                partial(self._on_bus_channel_label_changed, "mux", idx, edit)
            )
            row_layout.addWidget(edit)

            self._mux_channel_layout.addWidget(row)

    def _rebuild_demux_channel_rows(self) -> None:
        if not (self._demux_channel_layout and self._component):
            return

        self._clear_dynamic_layout(self._demux_channel_layout)
        labels = self._component.parameters.get("channel_labels", [])

        for idx, label in enumerate(labels):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            idx_label = QLabel(f"{idx + 1}:")
            idx_label.setFixedWidth(20)
            idx_label.setObjectName("ChannelIndexLabel")
            row_layout.addWidget(idx_label)

            edit = AutoSelectLineEdit(label)
            edit.setPlaceholderText(f"Out{idx + 1}")
            edit.returnPressed.connect(
                partial(self._on_bus_channel_label_changed, "demux", idx, edit)
            )
            edit.editingFinished.connect(
                partial(self._on_bus_channel_label_changed, "demux", idx, edit)
            )
            row_layout.addWidget(edit)

            self._demux_channel_layout.addWidget(row)

    def _on_mux_count_changed(self, value: int) -> None:
        if not self._component:
            return

        set_mux_input_count(self._component, value)
        self.property_changed.emit("input_count", value)
        self._rebuild_mux_channel_rows()

    def _on_demux_count_changed(self, value: int) -> None:
        if not self._component:
            return

        set_demux_output_count(self._component, value)
        self.property_changed.emit("output_count", value)
        self._rebuild_demux_channel_rows()

    def _on_bus_channel_label_changed(self, kind: str, index: int, widget: QLineEdit) -> None:
        if not self._component:
            return

        text = widget.text().strip() or f"Ch{index + 1}"
        widget.setText(text)

        labels = self._component.parameters.get("channel_labels", [])
        if index >= len(labels):
            return

        if labels[index] != text:
            labels[index] = text
            self.property_changed.emit("channel_labels", labels)

    # --- C-Block parameter editors -----------------------------------------------

    def _create_cblock_param_widgets(self) -> None:
        if not self._component:
            return

        params = self._component.parameters
        params["implementation"] = "source"

        n_inputs_spin = QSpinBox()
        n_inputs_spin.setRange(*C_BLOCK_IO_LIMITS)
        n_inputs_spin.setFixedWidth(84)
        try:
            input_count = int(params.get("n_inputs", 1) or 1)
        except (TypeError, ValueError):
            input_count = 1
        n_inputs_spin.setValue(max(C_BLOCK_IO_LIMITS[0], input_count))
        n_inputs_spin.valueChanged.connect(lambda value: self._on_cblock_io_changed("n_inputs", value))

        n_outputs_spin = QSpinBox()
        n_outputs_spin.setRange(*C_BLOCK_IO_LIMITS)
        n_outputs_spin.setFixedWidth(84)
        try:
            output_count = int(params.get("n_outputs", 1) or 1)
        except (TypeError, ValueError):
            output_count = 1
        n_outputs_spin.setValue(max(C_BLOCK_IO_LIMITS[0], output_count))
        n_outputs_spin.valueChanged.connect(lambda value: self._on_cblock_io_changed("n_outputs", value))

        io_row = QWidget()
        io_layout = QHBoxLayout(io_row)
        io_layout.setContentsMargins(0, 0, 0, 0)
        io_layout.setSpacing(8)
        io_layout.addWidget(QLabel("Inputs:"))
        io_layout.addWidget(n_inputs_spin)
        io_layout.addSpacing(12)
        io_layout.addWidget(QLabel("Outputs:"))
        io_layout.addWidget(n_outputs_spin)
        io_layout.addStretch()
        self._params_layout.addRow("I/O:", io_row)

        sample_time_widget = SIValueWidget("s")
        sample_time_widget.setFixedWidth(170)
        sample_time_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        sample_time = get_control_sample_time(params, default=0.0)
        set_control_sample_time(params, sample_time)
        sample_time_widget.value = sample_time
        if self._theme is not None:
            sample_time_widget.apply_theme(self._theme)
        sample_time_widget.value_changed.connect(self._on_cblock_sample_time_changed)
        self._cblock_sample_time_edit = sample_time_widget
        self._params_layout.addRow("Ts:", sample_time_widget)

        demux_hint = QLabel("Tip: for n_outputs > 1, use SIGNAL_DEMUX to route each output channel.")
        demux_hint.setWordWrap(True)
        demux_hint.setObjectName("CBlockHintLabel")
        self._params_layout.addRow("", demux_hint)

        path_row = QWidget()
        path_layout = QHBoxLayout(path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        path_edit = AutoSelectLineEdit(str(params.get("source", "") or ""))
        path_edit.setPlaceholderText("Select a source file")
        path_edit.returnPressed.connect(self._on_cblock_path_changed)
        path_edit.editingFinished.connect(self._on_cblock_path_changed)
        path_layout.addWidget(path_edit, 1)
        browse_btn = QPushButton("Browse")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._on_browse_cblock_path)
        path_layout.addWidget(browse_btn)
        create_btn = QPushButton("Create Base File...")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create_cblock_base_file)
        self._cblock_create_btn = create_btn
        path_layout.addWidget(create_btn)
        open_btn = QPushButton("Open in Editor")
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._on_open_cblock_source_external)
        self._cblock_open_btn = open_btn
        path_layout.addWidget(open_btn)
        self._cblock_path_edit = path_edit
        self._params_layout.addRow("Path:", path_row)

        flags = params.get("extra_cflags", [])
        if isinstance(flags, list):
            flags_text = ", ".join(str(item) for item in flags if str(item).strip())
        else:
            flags_text = ""
        flags_edit = AutoSelectLineEdit(flags_text)
        flags_edit.setPlaceholderText("-O3, -Wall")
        flags_edit.returnPressed.connect(self._on_cblock_extra_cflags_changed)
        flags_edit.editingFinished.connect(self._on_cblock_extra_cflags_changed)
        self._cblock_extra_cflags_edit = flags_edit
        self._params_layout.addRow("Extra cflags:", flags_edit)

        compile_btn = QPushButton("Test Compilation")
        compile_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        compile_btn.clicked.connect(self._on_test_cblock_compilation)
        self._cblock_compile_btn = compile_btn
        self._params_layout.addRow("Build:", compile_btn)

        abi_hint = QLabel(
            "ABI contract: pulsim_cblock_abi_version and pulsim_cblock_step are required."
        )
        abi_hint.setWordWrap(True)
        abi_hint.setObjectName("CBlockHintLabel")
        self._params_layout.addRow("", abi_hint)

        trust_warning = QLabel(
            "Security warning: C libraries run in-process without sandbox. Use trusted code only."
        )
        trust_warning.setWordWrap(True)
        trust_warning.setObjectName("CBlockHintLabel")
        self._params_layout.addRow("", trust_warning)
        self._refresh_cblock_visibility()

    def _on_cblock_io_changed(self, field: str, value: int) -> None:
        if not self._component:
            return
        if field == "n_inputs":
            set_cblock_input_count(self._component, int(value))
        else:
            set_cblock_output_count(self._component, int(value))
        self.property_changed.emit(field, int(value))

    def _on_cblock_sample_time_changed(self, value: float) -> None:
        if not self._component:
            return
        normalized = set_control_sample_time(self._component.parameters, value)
        self.property_changed.emit("sample_time", normalized)

    def _on_cblock_path_changed(self) -> None:
        if not self._component or self._cblock_path_edit is None:
            return
        path = self._cblock_path_edit.text().strip().replace("\\", "/")
        self._cblock_path_edit.setText(path)
        self._component.parameters["source"] = path
        self.property_changed.emit("source", path)

    def _on_browse_cblock_path(self) -> None:
        start = self._cblock_path_edit.text().strip() if self._cblock_path_edit else ""
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import C source file",
            start,
            "C source (*.c);;All files (*)",
        )
        if not selected or self._cblock_path_edit is None:
            return
        self._cblock_path_edit.setText(selected)
        self._on_cblock_path_changed()

    def _on_cblock_extra_cflags_changed(self) -> None:
        if not self._component or self._cblock_extra_cflags_edit is None:
            return
        raw = self._cblock_extra_cflags_edit.text().strip()
        tokens = [part.strip() for part in raw.split(",")] if "," in raw else raw.split()
        flags = [token for token in tokens if token]
        self._component.parameters["extra_cflags"] = flags
        self.property_changed.emit("extra_cflags", flags)

    @staticmethod
    def _default_cblock_filename(component_name: str) -> str:
        stem = "".join(ch.lower() if ch.isalnum() else "_" for ch in component_name.strip())
        stem = stem.strip("_")
        return f"{(stem or 'cblock')}.c"

    def _build_cblock_base_source(self) -> str:
        if self._component is None:
            return ""
        try:
            n_inputs = max(1, int(self._component.parameters.get("n_inputs", 1) or 1))
        except (TypeError, ValueError):
            n_inputs = 1
        try:
            n_outputs = max(1, int(self._component.parameters.get("n_outputs", 1) or 1))
        except (TypeError, ValueError):
            n_outputs = 1

        output_lines = [
            "    /* Map your control law here. This starter forwards IN0 to all outputs. */",
            "    const double base = in[0];",
            "    out[0] = base;",
        ]
        for out_index in range(1, n_outputs):
            output_lines.append(f"    out[{out_index}] = base;")

        output_block = "\n".join(output_lines)

        return f"""#include "pulsim/v1/cblock_abi.h"

/*
 * Pulsim C-Block starter template.
 *
 * Quick guide:
 * 1) Keep `pulsim_cblock_abi_version` exactly as declared below.
 * 2) Implement your algorithm inside `pulsim_cblock_step`.
 * 3) Return 0 on success. Return non-zero to signal runtime error.
 * 4) Optional: implement `pulsim_cblock_init` / `pulsim_cblock_destroy`
 *    if you need persistent state between simulation steps.
 *
 * This block is configured for:
 * - n_inputs  = {n_inputs}
 * - n_outputs = {n_outputs}
 *
 * Input mapping:
 * - in[0] ... in[{n_inputs - 1}]
 *
 * Output mapping:
 * - out[0] ... out[{n_outputs - 1}]
 */
PULSIM_CBLOCK_EXPORT int pulsim_cblock_abi_version = PULSIM_CBLOCK_ABI_VERSION;

PULSIM_CBLOCK_EXPORT int pulsim_cblock_step(
    PulsimCBlockCtx* ctx, double t, double dt, const double* in, double* out)
{{
    (void)ctx;
    (void)t;
    (void)dt;
{output_block}
    return 0;
}}
"""

    def _on_create_cblock_base_file(self) -> None:
        if self._component is None:
            return

        start = ""
        if self._cblock_path_edit is not None:
            start = self._cblock_path_edit.text().strip()
        if not start:
            start = self._default_cblock_filename(self._component.name)

        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Create C-Block source file",
            start,
            "C source (*.c);;All files (*)",
        )
        if not selected:
            return

        source_path = Path(selected).expanduser()
        if source_path.suffix.lower() != ".c":
            source_path = source_path.with_suffix(".c")

        normalized_path = source_path.as_posix()
        if source_path.exists():
            overwrite = QMessageBox.question(
                self,
                "Overwrite File",
                "Selected file already exists. Overwrite it with the starter template?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if overwrite != QMessageBox.StandardButton.Yes:
                return

        source_code = self._build_cblock_base_source()
        try:
            source_path.parent.mkdir(parents=True, exist_ok=True)
            source_path.write_text(source_code, encoding="utf-8")
        except OSError as exc:
            self._show_cblock_build_message(
                title="C-Block File Error",
                message="Failed to create C-Block source file.",
                details=str(exc),
                icon=QMessageBox.Icon.Critical,
            )
            return

        if self._cblock_path_edit is not None:
            self._cblock_path_edit.setText(normalized_path)
        self._component.parameters["source"] = normalized_path
        self.property_changed.emit("source", normalized_path)

        self._show_cblock_build_message(
            title="C-Block File Created",
            message="Starter C-Block file was created and imported.",
            details=normalized_path,
            icon=QMessageBox.Icon.Information,
        )

    def _on_open_cblock_source_external(self) -> None:
        if self._component is None:
            return

        source_raw = str(self._component.parameters.get("source", "") or "").strip()
        if not source_raw and self._cblock_path_edit is not None:
            source_raw = self._cblock_path_edit.text().strip()

        if not source_raw:
            self._show_cblock_build_message(
                title="C-Block Validation Error",
                message="Select or create a source file before opening in external editor.",
                icon=QMessageBox.Icon.Warning,
            )
            return

        source_path = Path(source_raw).expanduser()
        if not source_path.exists():
            self._show_cblock_build_message(
                title="C-Block Validation Error",
                message="Source file not found. Create the file first.",
                details=source_path.as_posix(),
                icon=QMessageBox.Icon.Warning,
            )
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(source_path)))
        if not opened:
            self._show_cblock_build_message(
                title="C-Block Editor",
                message="Could not open external editor for this file.",
                details=source_path.as_posix(),
                icon=QMessageBox.Icon.Critical,
            )

    @staticmethod
    def _safe_cblock_stem(name: str) -> str:
        stem = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
        stem = stem.strip("_")
        return stem or "cblock"

    @staticmethod
    def _coerce_cblock_flags(value: Any) -> list[str] | None:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            tokens = [part.strip() for part in text.split(",")] if "," in text else text.split()
            return [token for token in tokens if token]
        return None

    def _show_cblock_build_message(
        self,
        *,
        title: str,
        message: str,
        details: str = "",
        icon: QMessageBox.Icon = QMessageBox.Icon.Information,
    ) -> None:
        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(message)
        if details:
            box.setDetailedText(details)
        box.exec()

    def _on_test_cblock_compilation(self) -> None:
        if self._component is None:
            return

        params = self._component.parameters
        try:
            n_inputs = int(params.get("n_inputs", 1) or 1)
            n_outputs = int(params.get("n_outputs", 1) or 1)
        except (TypeError, ValueError):
            self._show_cblock_build_message(
                title="C-Block Validation Error",
                message="n_inputs and n_outputs must be integers >= 1.",
                icon=QMessageBox.Icon.Warning,
            )
            return
        if n_inputs < 1 or n_outputs < 1:
            self._show_cblock_build_message(
                title="C-Block Validation Error",
                message="n_inputs and n_outputs must be >= 1.",
                icon=QMessageBox.Icon.Warning,
            )
            return

        flags = self._coerce_cblock_flags(params.get("extra_cflags", []))
        if flags is None:
            self._show_cblock_build_message(
                title="C-Block Validation Error",
                message="extra_cflags must be list[str].",
                icon=QMessageBox.Icon.Warning,
            )
            return

        source_raw = str(params.get("source", "") or "").strip()
        if not source_raw and self._cblock_path_edit is not None:
            source_raw = self._cblock_path_edit.text().strip()

        source_path: Path | None = None
        try:
            if not source_raw:
                self._show_cblock_build_message(
                    title="C-Block Validation Error",
                    message="Import a C source file before validating.",
                    icon=QMessageBox.Icon.Warning,
                )
                return

            source_path = Path(source_raw).expanduser()

            if source_path is None or not source_path.exists():
                self._show_cblock_build_message(
                    title="C-Block Validation Error",
                    message="C source file was not found.",
                    details=(source_path.as_posix() if source_path is not None else ""),
                    icon=QMessageBox.Icon.Warning,
                )
                return

            try:
                from pulsim.cblock import CBlockCompileError, compile_cblock
            except Exception as exc:  # pragma: no cover - depends on backend install
                self._show_cblock_build_message(
                    title="C-Block Build Error",
                    message="Unable to import pulsim.cblock compile API.",
                    details=str(exc),
                    icon=QMessageBox.Icon.Critical,
                )
                return

            try:
                built_lib = compile_cblock(
                    source_path,
                    name=self._safe_cblock_stem(self._component.name),
                    extra_cflags=flags,
                )
            except CBlockCompileError as exc:
                details: list[str] = [str(exc)]
                compiler_path = str(getattr(exc, "compiler_path", "") or "").strip()
                stderr_output = str(getattr(exc, "stderr_output", "") or "").strip()
                source_hint = str(getattr(exc, "source", "") or source_path.as_posix()).strip()
                if compiler_path:
                    details.append(f"\nCompiler: {compiler_path}")
                if source_hint:
                    details.append(f"\nSource: {source_hint}")
                if stderr_output:
                    details.append(f"\nStderr:\n{stderr_output}")
                self._show_cblock_build_message(
                    title="C-Block Build Error",
                    message="C-Block compilation failed.",
                    details="".join(details),
                    icon=QMessageBox.Icon.Critical,
                )
                return
            except Exception as exc:  # pragma: no cover - defensive guard
                self._show_cblock_build_message(
                    title="C-Block Build Error",
                    message="Unexpected error while compiling C-Block.",
                    details=str(exc),
                    icon=QMessageBox.Icon.Critical,
                )
                return

            self._show_cblock_build_message(
                title="C-Block Build",
                message="C-Block compiled successfully.",
                details=str(built_lib),
                icon=QMessageBox.Icon.Information,
            )
        finally:
            pass

    def _refresh_cblock_visibility(self) -> None:
        if self._cblock_path_edit is not None and self._component is not None:
            self._cblock_path_edit.blockSignals(True)
            self._cblock_path_edit.setText(str(self._component.parameters.get("source", "") or ""))
            self._cblock_path_edit.setPlaceholderText("Select a source file")
            self._cblock_path_edit.blockSignals(False)
        if self._cblock_create_btn is not None:
            self._cblock_create_btn.setVisible(True)
        if self._cblock_open_btn is not None:
            self._cblock_open_btn.setVisible(True)
        if self._cblock_compile_btn is not None:
            self._cblock_compile_btn.setText("Test Compilation")

    # --- Utilities ----------------------------------------------------------------

    @staticmethod
    def _clear_dynamic_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _get_unit_for_param(self, name: str) -> str:
        """Get the SI unit for a parameter name."""
        units = {
            "resistance": "Ω",
            "capacitance": "F",
            "inductance": "H",
            "voltage": "V",
            "current": "A",
            "initial_voltage": "V",
            "initial_current": "A",
            "vth": "V",
            "vce_sat": "V",
            "v_ce_sat": "V",
            "ron": "Ω",
            "roff": "Ω",
            "rs": "Ω",
            "rds_on": "Ω",
            "g_on": "S",
            "g_off": "S",
            "lm": "H",
            "frequency": "Hz",
            "amplitude": "V",
            "switching_eon_j": "J",
            "switching_eoff_j": "J",
            "switching_err_j": "J",
            "thermal_rth": "K/W",
            "thermal_cth": "J/K",
            "thermal_shared_sink_rth": "K/W",
            "thermal_shared_sink_cth": "J/K",
            "thermal_temp_init": "°C",
            "thermal_temp_ref": "°C",
        }
        return units.get(name, "")

    def _on_name_changed(self) -> None:
        """Handle component name change."""
        if self._component:
            new_name = self._name_edit.text()
            if self._is_net_label_component(self._component):
                old_label = self._net_label_text(self._component)
                if old_label != new_name:
                    self._component.parameters["net_label"] = new_name
                    # Keep internal name aligned to avoid stale legacy fallbacks.
                    self._component.name = new_name
                    self.property_changed.emit("net_label", new_name)
                    self.name_changed.emit(new_name)
                    if self._summary_title is not None:
                        self._summary_title.setText(new_name or self._component.type.name.replace("_", " ").title())
            elif self._component.name != new_name:
                self._component.name = new_name
                self.name_changed.emit(new_name)
            self._update_net_label_pair_button()

    @staticmethod
    def _is_net_label_component(component: Component | None) -> bool:
        if component is None:
            return False
        return component.type in {ComponentType.GOTO_LABEL, ComponentType.FROM_LABEL}

    @staticmethod
    def _net_label_text(component: Component | None) -> str:
        if component is None:
            return ""
        label = str(component.parameters.get("net_label", "") or "").strip()
        if label:
            return label
        return str(component.name or "").strip()

    def _update_net_label_pair_button(self) -> None:
        if self._net_label_pair_btn is None:
            return

        if len(self._components) != 1 or not self._is_net_label_component(self._component):
            self._net_label_pair_btn.hide()
            return

        label_text = self._net_label_text(self._component)
        self._net_label_pair_btn.show()
        self._net_label_pair_btn.setEnabled(bool(label_text))
        if label_text:
            self._net_label_pair_btn.setToolTip(
                f"Jump to linked Goto/From for '{label_text}'"
            )
        else:
            self._net_label_pair_btn.setToolTip(
                "Set net_label or name to enable pair navigation"
            )

    def _on_net_label_pair_clicked(self) -> None:
        if not self._is_net_label_component(self._component):
            return
        label_text = self._net_label_text(self._component)
        if not label_text:
            return
        self.net_label_pair_requested.emit(str(self._component.id), label_text)

    def _on_param_changed(self, name: str, value: Any) -> None:
        """Handle parameter value change."""
        if self._component:
            if name == DUTY_INPUT_PARAMETER:
                set_pwm_duty_input_enabled(self._component, bool(value))
                value = bool(self._component.parameters.get(DUTY_INPUT_PARAMETER, False))
                self._update_display()
            elif name == THERMAL_PORT_PARAMETER:
                set_thermal_port_enabled(self._component, bool(value))
                value = bool(self._component.parameters.get(THERMAL_PORT_PARAMETER, False))
                # Legacy projects may gain new thermal fields when toggling thermal.
                if supports_electrothermal_parameters(self._component.type):
                    self._update_display()
            elif (
                name == "input_count"
                and self._component.type in (ComponentType.SUM, ComponentType.SUBTRACTOR)
            ):
                set_sum_input_count(self._component, int(value))
                value = int(self._component.parameters.get("input_count", int(value)))
            else:
                self._component.parameters[name] = value
            self.property_changed.emit(name, value)

    def _on_position_changed(self, axis: str, value: float) -> None:
        """Handle position change."""
        if self._component:
            if axis == "x":
                self._component.x = value
            else:
                self._component.y = value
            self.property_changed.emit(f"position_{axis}", value)

    def set_show_position_controls(self, show: bool) -> None:
        """Show or hide position controls section."""
        self._show_position_controls = show
        self._pos_container.setVisible(bool(show and self._component is not None))

    def set_compact_mode(self, compact: bool) -> None:
        """Enable compact layout (used by modal popup editor)."""
        self._compact_mode = compact
        if self._main_layout is None:
            return

        if compact:
            self._scroll.setMinimumHeight(240)
            self._scroll.setMaximumHeight(420)
            self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._params_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            self._main_layout.setStretchFactor(self._params_container, 0)
            self._apply_compact_scroll_limits_for_component()
        else:
            self._scroll.setMinimumHeight(270)
            self._scroll.setMaximumHeight(16777215)
            self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._params_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
            )
            self._main_layout.setStretchFactor(self._params_container, 1)

    def _apply_compact_scroll_limits_for_component(self) -> None:
        """Tune compact scroll height for components that need more vertical space."""
        if not self._compact_mode or self._component is None:
            return

        if self._component.type == ComponentType.C_BLOCK:
            # C_BLOCK typically has many fields; allow the parameters panel to
            # grow closer to the dialog action buttons.
            self._scroll.setMinimumHeight(380)
            self._scroll.setMaximumHeight(560)

    def _on_edit_waveform(self, param: str, waveform: dict) -> None:
        """Open waveform editor dialog."""
        unit = "V" if "voltage" in param.lower() else "A"
        dialog = WaveformEditorDialog(waveform, unit, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_waveform = dialog.get_waveform()
            self._on_param_changed(param, new_waveform)
            # Refresh the display
            self._update_display()

    def apply_theme(self, theme: Theme) -> None:
        """Apply active theme to the properties panel."""
        self._theme = theme
        c = theme.colors
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(c.panel_background))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        self.setStyleSheet(f"""
            QWidget#PropertiesPanelRoot {{
                background-color: {c.panel_background};
            }}
            QWidget#PropertiesSectionCard {{
                background-color: {c.panel_header};
                border: 1px solid {c.panel_border};
                border-radius: 12px;
            }}
            QWidget#PropertiesSectionCard:hover {{
                border: 1px solid {c.input_focus_border};
            }}
            QLabel {{
                color: {c.foreground};
            }}
            QLabel#PropertiesSummaryTitle {{
                color: {c.foreground};
                font-size: 13px;
                font-weight: 700;
            }}
            QLabel#PropertiesSummarySubtitle {{
                color: {c.foreground_muted};
                font-size: 11px;
            }}
            QLabel#PropertiesInfoBadge {{
                background-color: {c.tree_item_selected};
                color: {c.primary};
                border: 1px solid {c.border};
                border-radius: 10px;
                padding: 2px 8px;
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#PropertiesParamsCount {{
                color: {c.foreground_muted};
                font-size: 11px;
                font-weight: 500;
            }}
            QLabel#PropertiesTypeValue {{
                color: {c.primary};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#ChannelIndexLabel {{
                color: {c.foreground_muted};
            }}
            QLabel#WaveformTypeBadge {{
                background-color: {c.tree_item_selected};
                color: {c.primary};
                padding: 2px 8px;
                border-radius: 4px;
                font-weight: 500;
                font-size: 11px;
            }}
            QLabel#WaveformPreviewLabel {{
                color: {c.foreground_muted};
            }}
            QLabel#CBlockHintLabel {{
                color: {c.foreground_muted};
                font-size: 11px;
            }}
            QPushButton#WaveformEditButton {{
                background-color: {c.primary};
                color: {c.primary_foreground};
                border: none;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 500;
            }}
            QPushButton#WaveformEditButton:hover {{
                background-color: {c.primary_hover};
            }}
            QPushButton#WaveformEditButton:pressed {{
                background-color: {c.primary_pressed};
            }}
            QPushButton#NetPairButton {{
                background-color: {c.info};
                color: {c.primary_foreground};
                border: none;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#NetPairButton:hover {{
                background-color: {c.primary_hover};
            }}
            QPushButton#NetPairButton:disabled {{
                background-color: {c.tree_item_selected_inactive};
                color: {c.foreground_muted};
            }}
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QPlainTextEdit {{
                background-color: {c.input_background};
                border: 1px solid {c.input_border};
                border-radius: 7px;
                padding: 6px 8px;
                color: {c.foreground};
                selection-background-color: {c.primary};
                selection-color: {c.primary_foreground};
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
                border: 1px solid {c.input_focus_border};
            }}
            QCheckBox {{
                color: {c.foreground};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 4px;
                border: 1px solid {c.input_border};
                background: {c.input_background};
            }}
            QCheckBox::indicator:checked {{
                background: {c.primary};
                border: 1px solid {c.primary};
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {c.input_border};
                border-radius: 5px;
                min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {c.border};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QFormLayout QLabel {{
                color: {c.foreground_muted};
            }}
            QLabel#PropertiesEmptyState {{
                color: {c.foreground_muted};
                background-color: {c.panel_header};
                border: 1px dashed {c.panel_border};
                border-radius: 12px;
                padding: 26px;
            }}
        """)

        self._type_label.setStyleSheet(f"color: {c.foreground_muted}; font-weight: 500;")
        if self._summary_icon is not None:
            self._summary_icon.setStyleSheet(
                f"background-color: {c.input_background}; border: 1px solid {c.input_border}; "
                "border-radius: 10px;"
            )
        if self._info_header is not None:
            self._info_header.apply_theme(theme, accent_color=c.primary)
        if self._params_header is not None:
            self._params_header.apply_theme(theme, accent_color=c.success)
        if self._pos_header is not None:
            self._pos_header.apply_theme(theme, accent_color=c.warning)

        for widget in self._widgets.values():
            if isinstance(widget, SIValueWidget):
                widget.apply_theme(theme)

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode and update colors accordingly."""
        self._dark_mode = dark
        if self._theme_service is not None:
            self.apply_theme(self._theme_service.current_theme)
            return
        self.apply_theme(DARK_THEME if dark else LIGHT_THEME)
