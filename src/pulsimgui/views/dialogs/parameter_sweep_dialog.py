"""Dialog for configuring parameter sweeps."""

from dataclasses import dataclass
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component
from pulsimgui.services.simulation_service import ParameterSweepSettings
from pulsimgui.views.properties import SILineEdit


@dataclass
class _SweepTarget:
    component: Component
    display_name: str
    parameters: dict[str, float]


class ParameterSweepDialog(QDialog):
    """Collects sweep parameters from the user."""

    def __init__(self, circuit: Circuit, parent=None):
        super().__init__(parent)
        self._circuit = circuit
        self._targets: List[_SweepTarget] = self._build_targets(circuit)

        self.setWindowTitle("Parameter Sweep")
        self.setMinimumWidth(420)

        self._setup_ui()
        self._populate_targets()
        self._update_parameter_combo()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        target_group = QGroupBox("Sweep Target")
        target_layout = QFormLayout(target_group)

        self._component_combo = QComboBox()
        self._component_combo.currentIndexChanged.connect(self._update_parameter_combo)
        target_layout.addRow("Component:", self._component_combo)

        self._parameter_combo = QComboBox()
        self._parameter_combo.currentTextChanged.connect(self._refresh_parameter_defaults)
        target_layout.addRow("Parameter:", self._parameter_combo)

        layout.addWidget(target_group)

        range_group = QGroupBox("Sweep Range")
        range_layout = QFormLayout(range_group)

        self._start_edit = SILineEdit("")
        range_layout.addRow("Start value:", self._start_edit)

        self._stop_edit = SILineEdit("")
        range_layout.addRow("End value:", self._stop_edit)

        self._points_spin = QSpinBox()
        self._points_spin.setRange(2, 1000)
        self._points_spin.setValue(5)
        range_layout.addRow("Points:", self._points_spin)

        self._scale_combo = QComboBox()
        self._scale_combo.addItem("Linear", "linear")
        self._scale_combo.addItem("Logarithmic", "log")
        range_layout.addRow("Spacing:", self._scale_combo)

        layout.addWidget(range_group)

        output_group = QGroupBox("Output & Execution")
        output_layout = QFormLayout(output_group)

        self._output_combo = QComboBox()
        self._output_combo.setEditable(True)
        self._output_combo.addItems(["V(out)", "V(in)", "I(R1)"])
        output_layout.addRow("Output signal:", self._output_combo)

        self._parallel_check = QCheckBox("Enable parallel execution")
        self._parallel_check.setChecked(True)
        self._parallel_check.stateChanged.connect(self._toggle_parallel_spin)
        output_layout.addRow(self._parallel_check)

        self._parallel_spin = QSpinBox()
        self._parallel_spin.setRange(1, 16)
        self._parallel_spin.setValue(4)
        output_layout.addRow("Parallel workers:", self._parallel_spin)

        layout.addWidget(output_group)

        self._empty_label = QLabel("No components with numeric parameters available.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self._accept_if_valid)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _toggle_parallel_spin(self) -> None:
        self._parallel_spin.setEnabled(self._parallel_check.isChecked())

    def _build_targets(self, circuit: Circuit) -> List[_SweepTarget]:
        targets: List[_SweepTarget] = []
        for component in circuit.components.values():
            numeric_params = {
                name: value
                for name, value in component.parameters.items()
                if isinstance(value, (int, float))
            }
            if not numeric_params:
                continue
            display = component.name or component.type.name.title()
            targets.append(_SweepTarget(component=component, display_name=display, parameters=numeric_params))
        return targets

    def _populate_targets(self) -> None:
        self._component_combo.clear()
        for target in self._targets:
            self._component_combo.addItem(target.display_name, target)
        self._empty_label.setVisible(len(self._targets) == 0)

    def _update_parameter_combo(self) -> None:
        target = self._current_target()
        self._parameter_combo.clear()
        if not target:
            self._start_edit.setEnabled(False)
            self._stop_edit.setEnabled(False)
            self._points_spin.setEnabled(False)
            self._scale_combo.setEnabled(False)
            return

        self._start_edit.setEnabled(True)
        self._stop_edit.setEnabled(True)
        self._points_spin.setEnabled(True)
        self._scale_combo.setEnabled(True)

        for name in target.parameters.keys():
            self._parameter_combo.addItem(name)

        self._refresh_parameter_defaults()

    def _current_target(self) -> _SweepTarget | None:
        data = self._component_combo.currentData()
        return data if isinstance(data, _SweepTarget) else None

    def _current_parameter_value(self) -> float:
        target = self._current_target()
        if not target:
            return 0.0
        param = self._parameter_combo.currentText()
        return float(target.parameters.get(param, 0.0))

    def _refresh_parameter_defaults(self) -> None:
        value = self._current_parameter_value()
        self._start_edit.value = float(value)
        self._stop_edit.value = float(value)

    def _accept_if_valid(self) -> None:
        if not self._current_target() or not self._parameter_combo.currentText():
            return
        self.accept()

    def get_settings(self) -> ParameterSweepSettings | None:
        target = self._current_target()
        if not target:
            return None
        parameter = self._parameter_combo.currentText()
        if not parameter:
            return None

        return ParameterSweepSettings(
            component_id=str(target.component.id),
            component_name=target.display_name,
            parameter_name=parameter,
            start_value=self._start_edit.value,
            end_value=self._stop_edit.value,
            points=self._points_spin.value(),
            scale=self._scale_combo.currentData(),
            output_signal=self._output_combo.currentText() or "V(out)",
            parallel_workers=self._parallel_spin.value() if self._parallel_check.isChecked() else 1,
            baseline_value=self._current_parameter_value(),
        )
