"""Properties panel for editing component parameters."""

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
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
)

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.utils.si_prefix import parse_si_value, format_si_value


class SILineEdit(QLineEdit):
    """Line edit that accepts SI prefix notation (e.g., 10k, 4.7u)."""

    value_changed = Signal(float)

    def __init__(self, unit: str = "", parent=None):
        super().__init__(parent)
        self._unit = unit
        self._value = 0.0
        self._valid = True

        self.editingFinished.connect(self._on_editing_finished)
        self.textChanged.connect(self._validate)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, val: float) -> None:
        self._value = val
        self.setText(format_si_value(val, self._unit))

    def _validate(self) -> None:
        """Validate input and update style."""
        text = self.text().strip()
        if not text:
            self._valid = True
            self.setStyleSheet("")
            return

        try:
            parse_si_value(text)
            self._valid = True
            self.setStyleSheet("")
        except ValueError:
            self._valid = False
            self.setStyleSheet("border: 1px solid red;")

    def _on_editing_finished(self) -> None:
        """Parse value when editing is finished."""
        text = self.text().strip()
        if not text:
            return

        try:
            self._value = parse_si_value(text)
            self.setText(format_si_value(self._value, self._unit))
            self.value_changed.emit(self._value)
        except ValueError:
            # Revert to previous value
            self.setText(format_si_value(self._value, self._unit))


class PropertiesPanel(QWidget):
    """Panel for editing selected component properties."""

    property_changed = Signal(str, object)  # parameter_name, new_value
    name_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._component: Component | None = None
        self._components: list[Component] = []
        self._widgets: dict[str, QWidget] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Component info group
        info_group = QGroupBox("Component")
        info_layout = QFormLayout(info_group)

        self._type_label = QLabel("-")
        info_layout.addRow("Type:", self._type_label)

        self._name_edit = QLineEdit()
        self._name_edit.editingFinished.connect(self._on_name_changed)
        info_layout.addRow("Name:", self._name_edit)

        layout.addWidget(info_group)

        # Parameters scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._params_widget = QWidget()
        self._params_layout = QFormLayout(self._params_widget)
        self._params_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        scroll.setWidget(self._params_widget)

        layout.addWidget(scroll)

        # Position group
        pos_group = QGroupBox("Position")
        pos_layout = QFormLayout(pos_group)

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(-10000, 10000)
        self._x_spin.setDecimals(1)
        self._x_spin.valueChanged.connect(lambda v: self._on_position_changed("x", v))
        pos_layout.addRow("X:", self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(-10000, 10000)
        self._y_spin.setDecimals(1)
        self._y_spin.valueChanged.connect(lambda v: self._on_position_changed("y", v))
        pos_layout.addRow("Y:", self._y_spin)

        self._rotation_combo = QComboBox()
        self._rotation_combo.addItems(["0°", "90°", "180°", "270°"])
        self._rotation_combo.currentIndexChanged.connect(self._on_rotation_changed)
        pos_layout.addRow("Rotation:", self._rotation_combo)

        mirror_layout = QHBoxLayout()
        self._mirror_h_check = QCheckBox("H")
        self._mirror_h_check.stateChanged.connect(
            lambda: self._on_mirror_changed("h", self._mirror_h_check.isChecked())
        )
        mirror_layout.addWidget(self._mirror_h_check)

        self._mirror_v_check = QCheckBox("V")
        self._mirror_v_check.stateChanged.connect(
            lambda: self._on_mirror_changed("v", self._mirror_v_check.isChecked())
        )
        mirror_layout.addWidget(self._mirror_v_check)
        mirror_layout.addStretch()

        pos_layout.addRow("Mirror:", mirror_layout)

        layout.addWidget(pos_group)

        # No selection label
        self._no_selection_label = QLabel("No component selected")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_selection_label.setStyleSheet("color: gray;")
        layout.addWidget(self._no_selection_label)

        # Initially hide everything except no selection label
        info_group.hide()
        scroll.hide()
        pos_group.hide()

        self._info_group = info_group
        self._scroll = scroll
        self._pos_group = pos_group

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
        # Clear parameter widgets
        self._clear_params()

        if not self._component:
            self._no_selection_label.show()
            self._info_group.hide()
            self._scroll.hide()
            self._pos_group.hide()
            return

        self._no_selection_label.hide()
        self._info_group.show()
        self._scroll.show()
        self._pos_group.show()

        # Update component info
        self._type_label.setText(self._component.type.name.replace("_", " ").title())
        self._name_edit.setText(self._component.name)

        # Update position
        self._x_spin.blockSignals(True)
        self._y_spin.blockSignals(True)
        self._rotation_combo.blockSignals(True)
        self._mirror_h_check.blockSignals(True)
        self._mirror_v_check.blockSignals(True)

        self._x_spin.setValue(self._component.x)
        self._y_spin.setValue(self._component.y)
        self._rotation_combo.setCurrentIndex(self._component.rotation // 90)
        self._mirror_h_check.setChecked(self._component.mirrored_h)
        self._mirror_v_check.setChecked(self._component.mirrored_v)

        self._x_spin.blockSignals(False)
        self._y_spin.blockSignals(False)
        self._rotation_combo.blockSignals(False)
        self._mirror_h_check.blockSignals(False)
        self._mirror_v_check.blockSignals(False)

        # Create parameter widgets
        self._create_param_widgets()

    def _clear_params(self) -> None:
        """Clear all parameter widgets."""
        while self._params_layout.count():
            item = self._params_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()

    def _create_param_widgets(self) -> None:
        """Create widgets for component parameters."""
        if not self._component:
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
            # Determine unit based on parameter name
            unit = self._get_unit_for_param(name)
            edit = SILineEdit(unit)
            edit.value = value
            edit.value_changed.connect(lambda v: self._on_param_changed(name, v))
            return edit

        elif isinstance(value, str):
            edit = QLineEdit(value)
            edit.editingFinished.connect(
                lambda: self._on_param_changed(name, edit.text())
            )
            return edit

        elif isinstance(value, dict):
            # Handle waveform parameters specially
            if "type" in value:
                return self._create_waveform_widget(name, value)

        return None

    def _create_waveform_widget(self, name: str, waveform: dict) -> QWidget:
        """Create widget for waveform parameter."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Waveform type combo
        type_combo = QComboBox()
        type_combo.addItems(["DC", "Pulse", "Sine", "PWL", "PWM"])
        current_type = waveform.get("type", "dc").upper()
        if current_type == "DC":
            type_combo.setCurrentIndex(0)
        elif current_type == "PULSE":
            type_combo.setCurrentIndex(1)
        elif current_type == "SINE":
            type_combo.setCurrentIndex(2)
        elif current_type == "PWL":
            type_combo.setCurrentIndex(3)
        elif current_type == "PWM":
            type_combo.setCurrentIndex(4)

        layout.addWidget(type_combo)

        # Value edit for DC
        if waveform.get("type") == "dc":
            value_edit = SILineEdit("V")
            value_edit.value = waveform.get("value", 0)
            value_edit.value_changed.connect(
                lambda v: self._on_waveform_value_changed(name, "value", v)
            )
            layout.addWidget(value_edit)

        # Edit button for complex waveforms
        edit_btn = QPushButton("Edit Waveform...")
        edit_btn.clicked.connect(lambda: self._on_edit_waveform(name))
        layout.addWidget(edit_btn)

        return widget

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
        }
        return units.get(name, "")

    def _on_name_changed(self) -> None:
        """Handle component name change."""
        if self._component:
            new_name = self._name_edit.text()
            self._component.name = new_name
            self.name_changed.emit(new_name)

    def _on_param_changed(self, name: str, value: Any) -> None:
        """Handle parameter value change."""
        if self._component:
            self._component.parameters[name] = value
            self.property_changed.emit(name, value)

    def _on_waveform_value_changed(self, param: str, key: str, value: Any) -> None:
        """Handle waveform sub-parameter change."""
        if self._component:
            if param not in self._component.parameters:
                self._component.parameters[param] = {}
            self._component.parameters[param][key] = value
            self.property_changed.emit(param, self._component.parameters[param])

    def _on_position_changed(self, axis: str, value: float) -> None:
        """Handle position change."""
        if self._component:
            if axis == "x":
                self._component.x = value
            else:
                self._component.y = value
            self.property_changed.emit(f"position_{axis}", value)

    def _on_rotation_changed(self, index: int) -> None:
        """Handle rotation change."""
        if self._component:
            self._component.rotation = index * 90
            self.property_changed.emit("rotation", self._component.rotation)

    def _on_mirror_changed(self, axis: str, checked: bool) -> None:
        """Handle mirror change."""
        if self._component:
            if axis == "h":
                self._component.mirrored_h = checked
            else:
                self._component.mirrored_v = checked
            self.property_changed.emit(f"mirror_{axis}", checked)

    def _on_edit_waveform(self, param: str) -> None:
        """Open waveform editor dialog."""
        # TODO: Open waveform editor dialog
        pass
