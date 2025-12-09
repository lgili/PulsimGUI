"""Properties panel for editing component parameters."""

from functools import partial
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
    QFrame,
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


class SectionHeader(QWidget):
    """A styled section header with icon and title - modern card style."""

    def __init__(self, icon_name: str, title: str, icon_color: str = "#3b82f6", parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_color = icon_color

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.setSpacing(10)

        # Icon with background circle
        icon_container = QWidget()
        icon_container.setFixedSize(28, 28)
        icon_container.setStyleSheet(f"""
            background-color: {icon_color}15;
            border-radius: 14px;
        """)
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(6, 6, 6, 6)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(16, 16)
        icon = IconService.get_icon(icon_name, icon_color)
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(16, 16))
        icon_layout.addWidget(self._icon_label)
        layout.addWidget(icon_container)

        # Title
        self._title_label = QLabel(title)
        self._title_label.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            letter-spacing: 0.3px;
        """)
        layout.addWidget(self._title_label)

        layout.addStretch()

    def set_dark_mode(self, dark: bool) -> None:
        """Update colors for dark mode."""
        # Icon colors adjust slightly for dark mode
        icon = IconService.get_icon(self._icon_name, self._icon_color)
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(16, 16))


class SIValueWidget(QWidget):
    """Widget with line edit for SI value and fixed unit label."""

    value_changed = Signal(float)

    def __init__(self, unit: str = "", parent=None):
        super().__init__(parent)
        self._unit = unit
        self._value = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._edit = QLineEdit()
        self._edit.setMinimumWidth(80)
        self._edit.editingFinished.connect(self._on_editing_finished)
        self._edit.textChanged.connect(self._validate)
        layout.addWidget(self._edit)

        if unit:
            self._unit_label = QLabel(unit)
            self._unit_label.setMinimumWidth(20)
            layout.addWidget(self._unit_label)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, val: float) -> None:
        self._value = val
        # Format without unit in the text field
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
                # Format nicely - remove trailing zeros
                if scaled == int(scaled):
                    return f"{int(scaled)}{prefix}"
                else:
                    return f"{scaled:.3g}{prefix}"

        return f"{val:.3g}"

    def _validate(self) -> None:
        """Validate input and update style."""
        text = self._edit.text().strip()
        if not text:
            self._edit.setStyleSheet("")
            return

        try:
            parse_si_value(text)
            self._edit.setStyleSheet("")
        except ValueError:
            self._edit.setStyleSheet("border: 1px solid red;")

    def _on_editing_finished(self) -> None:
        """Parse value when editing is finished."""
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
            # Revert to previous value
            self._edit.setText(self._format_value(self._value))


class PropertiesPanel(QWidget):
    """Panel for editing selected component properties."""

    property_changed = Signal(str, object)  # parameter_name, new_value
    name_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._component: Component | None = None
        self._components: list[Component] = []
        self._widgets: dict[str, QWidget] = {}
        self._scope_channel_layout = None
        self._mux_channel_layout = None
        self._demux_channel_layout = None

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the panel UI with modern card-based design."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(16)

        # Component info section - styled as a card
        self._info_container = QWidget()
        self._info_container.setStyleSheet("""
            QWidget {
                background-color: transparent;
            }
        """)
        info_container_layout = QVBoxLayout(self._info_container)
        info_container_layout.setContentsMargins(0, 0, 0, 0)
        info_container_layout.setSpacing(8)

        info_header = SectionHeader("info", "Component Info", "#3b82f6")
        info_container_layout.addWidget(info_header)

        info_form = QWidget()
        info_layout = QFormLayout(info_form)
        info_layout.setContentsMargins(12, 8, 12, 12)
        info_layout.setSpacing(12)
        info_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        info_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self._type_label = QLabel("-")
        self._type_label.setStyleSheet("color: #6b7280; font-size: 12px; font-weight: 500;")
        info_layout.addRow("Type:", self._type_label)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Component name")
        self._name_edit.editingFinished.connect(self._on_name_changed)
        info_layout.addRow("Name:", self._name_edit)

        info_container_layout.addWidget(info_form)
        layout.addWidget(self._info_container)

        # Parameters section header
        self._params_header = SectionHeader("sliders", "Parameters")
        layout.addWidget(self._params_header)

        # Parameters scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._params_widget = QWidget()
        self._params_layout = QFormLayout(self._params_widget)
        self._params_layout.setContentsMargins(4, 4, 4, 8)
        self._params_layout.setSpacing(6)
        self._params_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        self._params_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        scroll.setWidget(self._params_widget)

        layout.addWidget(scroll)

        # Position section
        self._pos_container = QWidget()
        pos_container_layout = QVBoxLayout(self._pos_container)
        pos_container_layout.setContentsMargins(0, 0, 0, 0)
        pos_container_layout.setSpacing(4)

        pos_header = SectionHeader("move", "Transform")
        pos_container_layout.addWidget(pos_header)

        pos_form = QWidget()
        pos_layout = QFormLayout(pos_form)
        pos_layout.setContentsMargins(4, 4, 4, 8)
        pos_layout.setSpacing(6)
        pos_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # Position row with X and Y side by side
        pos_row = QWidget()
        pos_row_layout = QHBoxLayout(pos_row)
        pos_row_layout.setContentsMargins(0, 0, 0, 0)
        pos_row_layout.setSpacing(8)

        self._x_spin = QDoubleSpinBox()
        self._x_spin.setRange(-10000, 10000)
        self._x_spin.setDecimals(1)
        self._x_spin.setPrefix("X: ")
        self._x_spin.valueChanged.connect(lambda v: self._on_position_changed("x", v))
        pos_row_layout.addWidget(self._x_spin)

        self._y_spin = QDoubleSpinBox()
        self._y_spin.setRange(-10000, 10000)
        self._y_spin.setDecimals(1)
        self._y_spin.setPrefix("Y: ")
        self._y_spin.valueChanged.connect(lambda v: self._on_position_changed("y", v))
        pos_row_layout.addWidget(self._y_spin)

        pos_layout.addRow("Position:", pos_row)

        self._rotation_combo = QComboBox()
        self._rotation_combo.addItems(["0°", "90°", "180°", "270°"])
        self._rotation_combo.currentIndexChanged.connect(self._on_rotation_changed)
        pos_layout.addRow("Rotation:", self._rotation_combo)

        mirror_layout = QHBoxLayout()
        mirror_layout.setSpacing(12)
        self._mirror_h_check = QCheckBox("Horizontal")
        self._mirror_h_check.stateChanged.connect(
            lambda: self._on_mirror_changed("h", self._mirror_h_check.isChecked())
        )
        mirror_layout.addWidget(self._mirror_h_check)

        self._mirror_v_check = QCheckBox("Vertical")
        self._mirror_v_check.stateChanged.connect(
            lambda: self._on_mirror_changed("v", self._mirror_v_check.isChecked())
        )
        mirror_layout.addWidget(self._mirror_v_check)
        mirror_layout.addStretch()

        pos_layout.addRow("Mirror:", mirror_layout)

        pos_container_layout.addWidget(pos_form)
        layout.addWidget(self._pos_container)

        layout.addStretch()

        # No selection label
        self._no_selection_label = QLabel("No component selected")
        self._no_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_selection_label.setStyleSheet(
            "color: #9ca3af; font-size: 12px; padding: 40px 20px;"
        )
        layout.addWidget(self._no_selection_label)

        # Initially hide everything except no selection label
        self._info_container.hide()
        self._params_header.hide()
        scroll.hide()
        self._pos_container.hide()

        self._scroll = scroll

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
            self._info_container.hide()
            self._params_header.hide()
            self._scroll.hide()
            self._pos_container.hide()
            return

        self._no_selection_label.hide()
        self._info_container.show()
        self._params_header.show()
        self._scroll.show()
        self._pos_container.show()

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
            # Determine unit based on parameter name
            unit = self._get_unit_for_param(name)
            widget = SIValueWidget(unit)
            widget.value = value
            widget.value_changed.connect(lambda v: self._on_param_changed(name, v))
            return widget

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
        self._params_layout.addRow("Channel Count:", count_spin)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._scope_channel_layout = layout
        self._params_layout.addRow("Channels:", container)
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

            row_layout.addWidget(QLabel(f"Input {idx + 1}"))

            label_edit = QLineEdit(channel.get("label", ""))
            label_edit.setPlaceholderText("Trace name")
            label_edit.editingFinished.connect(
                partial(self._on_scope_channel_label_changed, idx, label_edit)
            )
            row_layout.addWidget(label_edit)

            overlay_check = QCheckBox("Overlay")
            overlay_check.setChecked(channel.get("overlay", False))
            overlay_check.toggled.connect(
                partial(self._on_scope_channel_overlay_changed, idx, overlay_check)
            )
            row_layout.addWidget(overlay_check)

            row_layout.addStretch()
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

    def _on_scope_channel_overlay_changed(self, index: int, checkbox: QCheckBox) -> None:
        if not self._component:
            return

        channels = self._component.parameters.get("channels", [])
        if index >= len(channels):
            return

        new_value = checkbox.isChecked()
        if channels[index].get("overlay") != new_value:
            channels[index]["overlay"] = new_value
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
        self._params_layout.addRow("Channels:", container)
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
        self._params_layout.addRow("Channels:", container)
        self._rebuild_demux_channel_rows()

    def _rebuild_mux_channel_rows(self) -> None:
        if not (self._mux_channel_layout and self._component):
            return

        self._clear_dynamic_layout(self._mux_channel_layout)
        labels = self._component.parameters.get("channel_labels", [])
        ordering = self._component.parameters.get("ordering", [])
        count = len(labels)

        for idx, label in enumerate(labels):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            row_layout.addWidget(QLabel(f"In {idx + 1}"))

            edit = QLineEdit(label)
            edit.setPlaceholderText("Label")
            edit.editingFinished.connect(
                partial(self._on_bus_channel_label_changed, "mux", idx, edit)
            )
            row_layout.addWidget(edit)

            order_spin = QSpinBox()
            order_spin.setRange(0, max(0, count - 1))
            order_spin.setValue(ordering[idx] if idx < len(ordering) else idx)
            order_spin.valueChanged.connect(
                partial(self._on_bus_channel_order_changed, "mux", idx, order_spin)
            )
            row_layout.addWidget(order_spin)

            row_layout.addStretch()
            self._mux_channel_layout.addWidget(row)

    def _rebuild_demux_channel_rows(self) -> None:
        if not (self._demux_channel_layout and self._component):
            return

        self._clear_dynamic_layout(self._demux_channel_layout)
        labels = self._component.parameters.get("channel_labels", [])
        ordering = self._component.parameters.get("ordering", [])
        count = len(labels)

        for idx, label in enumerate(labels):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(6)

            row_layout.addWidget(QLabel(f"Out {idx + 1}"))

            edit = QLineEdit(label)
            edit.setPlaceholderText("Label")
            edit.editingFinished.connect(
                partial(self._on_bus_channel_label_changed, "demux", idx, edit)
            )
            row_layout.addWidget(edit)

            order_spin = QSpinBox()
            order_spin.setRange(0, max(0, count - 1))
            order_spin.setValue(ordering[idx] if idx < len(ordering) else idx)
            order_spin.valueChanged.connect(
                partial(self._on_bus_channel_order_changed, "demux", idx, order_spin)
            )
            row_layout.addWidget(order_spin)

            row_layout.addStretch()
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

    def _on_bus_channel_order_changed(self, kind: str, index: int, spin: QSpinBox) -> None:
        if not self._component:
            return

        ordering = self._component.parameters.get("ordering", [])
        if index >= len(ordering):
            return

        new_value = spin.value()
        if ordering[index] != new_value:
            ordering[index] = new_value
            self.property_changed.emit("ordering", ordering)

    # --- Utilities ----------------------------------------------------------------

    @staticmethod
    def _clear_dynamic_layout(layout: QVBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

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
            value_widget = SIValueWidget("V")
            value_widget.value = waveform.get("value", 0)
            value_widget.value_changed.connect(
                lambda v: self._on_waveform_value_changed(name, "value", v)
            )
            layout.addWidget(value_widget)

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
            "frequency": "Hz",
            "amplitude": "V",
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
