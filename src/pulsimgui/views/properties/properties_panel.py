"""Properties panel for editing component parameters."""

from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QColor, QPalette
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QLabel,
    QGroupBox,
    QScrollArea,
    QPushButton,
    QSpinBox,
    QDoubleSpinBox,
    QFrame,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QStackedWidget,
    QSizePolicy,
)

from pulsimgui.models.component import (
    Component,
    ComponentType,
    SCOPE_CHANNEL_LIMITS,
    MUX_CHANNEL_LIMITS,
    set_scope_channel_count,
    set_mux_input_count,
    set_demux_output_count,
)
from pulsimgui.utils.si_prefix import parse_si_value, format_si_value
from pulsimgui.resources.icons import IconService
from pulsimgui.views.library.library_panel import create_component_icon
from pulsimgui.services.theme_service import (
    ThemeService,
    Theme,
    LIGHT_THEME,
    DARK_THEME,
)


class SectionHeader(QWidget):
    """A styled section header with icon and title."""

    def __init__(self, icon_name: str, title: str, icon_color: str = "#3b82f6", parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_color = icon_color
        self._color_bar: QFrame | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(8)

        # Color bar
        self._color_bar = QFrame()
        self._color_bar.setFixedSize(3, 18)
        layout.addWidget(self._color_bar)

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
        if theme is None:
            self._title_label.setStyleSheet("font-weight: 600; font-size: 12px;")
            return
        self._title_label.setStyleSheet(
            f"font-weight: 600; font-size: 12px; color: {theme.colors.foreground};"
        )


class AutoSelectLineEdit(QLineEdit):
    """LineEdit that auto-selects all text when focused."""

    def focusInEvent(self, event):
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
        return self._value

    @value.setter
    def value(self, val: float) -> None:
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
    flip_requested = Signal(str)  # "h" or "v"
    rotate_requested = Signal(int)  # degrees

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
        self._main_layout: QVBoxLayout | None = None
        self._show_position_controls = False
        self._compact_mode = False
        self._dark_mode = False
        self._info_header: SectionHeader | None = None
        self._params_header: SectionHeader | None = None
        self._pos_header: SectionHeader | None = None
        self._transform_label: QLabel | None = None
        self._summary_icon: QLabel | None = None
        self._summary_title: QLabel | None = None
        self._summary_subtitle: QLabel | None = None

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
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)

        # Component info section
        self._info_container = QWidget()
        self._info_container.setObjectName("PropertiesSectionCard")
        info_layout = QVBoxLayout(self._info_container)
        info_layout.setContentsMargins(8, 6, 8, 8)
        info_layout.setSpacing(8)

        self._info_header = SectionHeader("info", "Component", "#3b82f6")
        info_layout.addWidget(self._info_header)

        summary = QWidget()
        summary_layout = QHBoxLayout(summary)
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        self._summary_icon = QLabel()
        self._summary_icon.setFixedSize(38, 38)
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

        # Type and name
        form = QWidget()
        form_layout = QFormLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(8)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._type_label = QLabel("-")
        form_layout.addRow("Type:", self._type_label)

        self._name_edit = AutoSelectLineEdit()
        self._name_edit.setPlaceholderText("Component name")
        self._name_edit.returnPressed.connect(self._on_name_changed)
        self._name_edit.editingFinished.connect(self._on_name_changed)
        form_layout.addRow("Name:", self._name_edit)

        info_layout.addWidget(form)

        # Transform buttons (rotate, flip)
        transform_widget = QWidget()
        transform_layout = QHBoxLayout(transform_widget)
        transform_layout.setContentsMargins(0, 4, 0, 0)
        transform_layout.setSpacing(6)

        self._transform_label = QLabel("Transform:")
        transform_layout.addWidget(self._transform_label)

        self._rotate_ccw_btn = IconButton("rotate-ccw", "Rotate Left (R)")
        self._rotate_ccw_btn.clicked.connect(lambda: self._on_rotate(-90))
        transform_layout.addWidget(self._rotate_ccw_btn)

        self._rotate_cw_btn = IconButton("rotate-cw", "Rotate Right (Shift+R)")
        self._rotate_cw_btn.clicked.connect(lambda: self._on_rotate(90))
        transform_layout.addWidget(self._rotate_cw_btn)

        self._flip_h_btn = IconButton("flip-horizontal", "Flip Horizontal (H)")
        self._flip_h_btn.clicked.connect(lambda: self._on_flip("h"))
        transform_layout.addWidget(self._flip_h_btn)

        self._flip_v_btn = IconButton("flip-vertical", "Flip Vertical (V)")
        self._flip_v_btn.clicked.connect(lambda: self._on_flip("v"))
        transform_layout.addWidget(self._flip_v_btn)

        transform_layout.addStretch()
        info_layout.addWidget(transform_widget)

        layout.addWidget(self._info_container)

        # Parameters section
        self._params_container = QWidget()
        self._params_container.setObjectName("PropertiesSectionCard")
        params_container_layout = QVBoxLayout(self._params_container)
        params_container_layout.setContentsMargins(8, 6, 8, 8)
        params_container_layout.setSpacing(8)

        self._params_header = SectionHeader("sliders", "Parameters", "#10b981")
        params_container_layout.addWidget(self._params_header)

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
        self._params_layout.setHorizontalSpacing(10)
        self._params_layout.setVerticalSpacing(8)
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
        pos_layout.setContentsMargins(8, 6, 8, 8)
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
            return

        self._no_selection_label.hide()
        self._info_container.show()
        self._params_container.show()
        self._pos_container.setVisible(self._show_position_controls)

        # Update component info
        type_name = self._component.type.name.replace("_", " ").title()
        self._type_label.setText(type_name)
        self._name_edit.setText(self._component.name)
        if self._summary_title is not None:
            self._summary_title.setText(self._component.name or type_name)
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

        # Update flip button states
        self._flip_h_btn.set_active(self._component.mirrored_h)
        self._flip_v_btn.set_active(self._component.mirrored_v)

        # Update position
        self._x_spin.blockSignals(True)
        self._y_spin.blockSignals(True)

        self._x_spin.setValue(self._component.x)
        self._y_spin.setValue(self._component.y)

        self._x_spin.blockSignals(False)
        self._y_spin.blockSignals(False)

        # Create parameter widgets
        self._create_param_widgets()
        if self._theme is not None:
            self.apply_theme(self._theme)

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

        params = self._component.parameters

        for name, value in params.items():
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
            "ron": "Ω",
            "roff": "Ω",
            "rs": "Ω",
            "rds_on": "Ω",
            "lm": "H",
            "frequency": "Hz",
            "amplitude": "V",
        }
        return units.get(name, "")

    def _on_name_changed(self) -> None:
        """Handle component name change."""
        if self._component:
            new_name = self._name_edit.text()
            if self._component.name != new_name:
                self._component.name = new_name
                self.name_changed.emit(new_name)

    def _on_param_changed(self, name: str, value: Any) -> None:
        """Handle parameter value change."""
        if self._component:
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
            self._scroll.setMinimumHeight(190)
            self._scroll.setMaximumHeight(310)
            self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self._params_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
            )
            self._main_layout.setStretchFactor(self._params_container, 0)
        else:
            self._scroll.setMinimumHeight(270)
            self._scroll.setMaximumHeight(16777215)
            self._scroll.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._params_container.setSizePolicy(
                QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
            )
            self._main_layout.setStretchFactor(self._params_container, 1)

    def _on_rotate(self, degrees: int) -> None:
        """Handle rotation button click."""
        if self._component:
            new_rotation = (self._component.rotation + degrees) % 360
            self._component.rotation = new_rotation
            self.rotate_requested.emit(degrees)
            self.property_changed.emit("rotation", new_rotation)

    def _on_flip(self, axis: str) -> None:
        """Handle flip button click."""
        if self._component:
            if axis == "h":
                self._component.mirrored_h = not self._component.mirrored_h
                self._flip_h_btn.set_active(self._component.mirrored_h)
            else:
                self._component.mirrored_v = not self._component.mirrored_v
                self._flip_v_btn.set_active(self._component.mirrored_v)
            self.flip_requested.emit(axis)
            self.property_changed.emit(f"mirror_{axis}",
                self._component.mirrored_h if axis == "h" else self._component.mirrored_v)

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
                border-radius: 8px;
            }}
            QLabel {{
                color: {c.foreground};
            }}
            QLabel#PropertiesSummaryTitle {{
                color: {c.foreground};
                font-size: 12px;
                font-weight: 600;
            }}
            QLabel#PropertiesSummarySubtitle {{
                color: {c.foreground_muted};
                font-size: 11px;
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
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit {{
                background-color: {c.input_background};
                border: 1px solid {c.input_border};
                border-radius: 4px;
                padding: 5px 6px;
                color: {c.foreground};
                selection-background-color: {c.primary};
                selection-color: {c.primary_foreground};
            }}
            QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTextEdit:focus {{
                border: 1px solid {c.input_focus_border};
            }}
            QCheckBox {{
                color: {c.foreground};
                spacing: 6px;
            }}
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            QFormLayout QLabel {{
                color: {c.foreground_muted};
            }}
        """)

        self._type_label.setStyleSheet(f"color: {c.foreground_muted}; font-weight: 500;")
        self._no_selection_label.setStyleSheet(f"color: {c.foreground_muted}; padding: 40px;")
        if self._summary_icon is not None:
            self._summary_icon.setStyleSheet(
                f"background-color: {c.input_background}; border: 1px solid {c.input_border}; "
                "border-radius: 6px;"
            )
        if self._transform_label is not None:
            self._transform_label.setStyleSheet(f"color: {c.foreground_muted};")

        if self._info_header is not None:
            self._info_header.apply_theme(theme, accent_color=c.primary)
        if self._params_header is not None:
            self._params_header.apply_theme(theme, accent_color=c.success)
        if self._pos_header is not None:
            self._pos_header.apply_theme(theme, accent_color=c.warning)

        button_icon = c.icon_default
        self._rotate_ccw_btn.apply_theme(theme, icon_color=button_icon)
        self._rotate_cw_btn.apply_theme(theme, icon_color=button_icon)
        self._flip_h_btn.apply_theme(theme, icon_color=button_icon)
        self._flip_v_btn.apply_theme(theme, icon_color=button_icon)
        self._flip_h_btn.set_active(bool(self._component and self._component.mirrored_h))
        self._flip_v_btn.set_active(bool(self._component and self._component.mirrored_v))

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
