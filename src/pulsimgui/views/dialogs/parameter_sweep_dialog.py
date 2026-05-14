"""Dialog for configuring parameter sweeps (Wave-4 sub-A 1.3 upgrade).

The dialog now hosts two tabs:

* **Range** — the original single-parameter linear/log range sweep. Same
  ``ParameterSweepSettings`` it always produced.
* **Monte Carlo** — multi-parameter Monte-Carlo with non-uniform
  distributions (uniform / log-uniform / normal / cartesian) and a
  metric selector matching ``pulsim.sweep.metrics``. Returns a
  :class:`MonteCarloSweepSettings`.

The caller chooses what to do by reading :meth:`get_mode` and either
:meth:`get_settings` (range mode) or :meth:`get_monte_carlo_settings`
(MC mode). Both modes coexist; switching tabs does not destroy the
other tab's state, so users can configure both and decide at OK time.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component
from pulsimgui.services.monte_carlo_sweep import (
    MonteCarloMetric,
    MonteCarloParameter,
    MonteCarloSweepSettings,
)
from pulsimgui.services.simulation_service import ParameterSweepSettings
from pulsimgui.views.properties import SILineEdit


_DISTRIBUTIONS = ("uniform", "log_uniform", "normal", "cartesian")
_METRIC_KINDS = ("steady_state", "peak", "rms", "settling_time")


@dataclass
class _SweepTarget:
    component: Component
    display_name: str
    parameters: dict[str, float]


class ParameterSweepDialog(QDialog):
    """Collects sweep parameters from the user."""

    MODE_RANGE = "range"
    MODE_MONTE_CARLO = "monte_carlo"

    def __init__(self, circuit: Circuit, parent: QWidget | None = None):
        super().__init__(parent)
        self._circuit = circuit
        self._targets: list[_SweepTarget] = self._build_targets(circuit)
        self._mode: str = self.MODE_RANGE

        self.setWindowTitle("Parameter Sweep")
        self.setMinimumWidth(560)

        self._setup_ui()
        self._populate_range_targets()
        self._update_parameter_combo()
        self._mc_seed_initial_row()

    # ------------------------------------------------------------------
    # Top-level construction
    # ------------------------------------------------------------------
    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_range_tab(), "Range")
        self._tabs.addTab(self._build_monte_carlo_tab(), "Monte Carlo")
        self._tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tabs)

        self._empty_label = QLabel("No components with numeric parameters available.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setWordWrap(True)
        layout.addWidget(self._empty_label)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._accept_if_valid)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    # ------------------------------------------------------------------
    # Tab 1 — Range (preserves the prior single-parameter behaviour)
    # ------------------------------------------------------------------
    def _build_range_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

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
        layout.addStretch(1)
        return tab

    # ------------------------------------------------------------------
    # Tab 2 — Monte Carlo (new for wave-4 sub-A 1.3)
    # ------------------------------------------------------------------
    def _build_monte_carlo_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        help_label = QLabel(
            "Add one row per swept parameter. Each row picks a distribution and its bounds. "
            "Metrics use the pulsim.sweep.metrics catalog (rms / peak / steady_state / "
            "settling_time)."
        )
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        # Parameters table
        self._mc_table = QTableWidget(0, 5)
        self._mc_table.setHorizontalHeaderLabels(
            ["Component", "Parameter", "Distribution", "Low / μ", "High / σ"]
        )
        header = self._mc_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._mc_table.setMinimumHeight(140)
        layout.addWidget(self._mc_table)

        row_btns = QHBoxLayout()
        add_btn = QPushButton("+ Add row")
        add_btn.clicked.connect(self._mc_add_row)
        rm_btn = QPushButton("− Remove selected")
        rm_btn.clicked.connect(self._mc_remove_selected)
        row_btns.addWidget(add_btn)
        row_btns.addWidget(rm_btn)
        row_btns.addStretch(1)
        layout.addLayout(row_btns)

        # Metrics + sample-count section
        cfg_group = QGroupBox("Run configuration")
        cfg_layout = QFormLayout(cfg_group)

        self._mc_metric_kind = QComboBox()
        for kind in _METRIC_KINDS:
            self._mc_metric_kind.addItem(kind)
        cfg_layout.addRow("Metric:", self._mc_metric_kind)

        self._mc_metric_channel = QComboBox()
        self._mc_metric_channel.setEditable(True)
        self._mc_metric_channel.addItems(["V(out)", "V(in)", "I(R1)"])
        cfg_layout.addRow("Channel:", self._mc_metric_channel)

        self._mc_samples_spin = QSpinBox()
        self._mc_samples_spin.setRange(1, 100000)
        self._mc_samples_spin.setValue(64)
        cfg_layout.addRow("Samples:", self._mc_samples_spin)

        self._mc_seed_spin = QSpinBox()
        self._mc_seed_spin.setRange(-1, 2**31 - 1)
        self._mc_seed_spin.setValue(-1)
        self._mc_seed_spin.setSpecialValueText("auto")
        cfg_layout.addRow("Seed:", self._mc_seed_spin)

        self._mc_workers_spin = QSpinBox()
        self._mc_workers_spin.setRange(0, 32)
        self._mc_workers_spin.setValue(0)
        self._mc_workers_spin.setSpecialValueText("serial")
        cfg_layout.addRow("Workers:", self._mc_workers_spin)

        layout.addWidget(cfg_group)
        layout.addStretch(1)
        return tab

    # ------------------------------------------------------------------
    # Range-tab support
    # ------------------------------------------------------------------
    def _on_tab_changed(self, index: int) -> None:
        self._mode = self.MODE_RANGE if index == 0 else self.MODE_MONTE_CARLO

    def _toggle_parallel_spin(self) -> None:
        self._parallel_spin.setEnabled(self._parallel_check.isChecked())

    def _build_targets(self, circuit: Circuit) -> list[_SweepTarget]:
        targets: list[_SweepTarget] = []
        for component in circuit.components.values():
            numeric_params = {
                name: value
                for name, value in component.parameters.items()
                if isinstance(value, (int, float))
            }
            if not numeric_params:
                continue
            display = component.name or component.type.name.title()
            targets.append(
                _SweepTarget(
                    component=component,
                    display_name=display,
                    parameters=numeric_params,
                )
            )
        return targets

    def _populate_range_targets(self) -> None:
        self._component_combo.clear()
        for target in self._targets:
            self._component_combo.addItem(target.display_name, target)
        self._empty_label.setVisible(len(self._targets) == 0)

    def _update_parameter_combo(self) -> None:
        target = self._current_target()
        self._parameter_combo.clear()
        enabled = bool(target)
        self._start_edit.setEnabled(enabled)
        self._stop_edit.setEnabled(enabled)
        self._points_spin.setEnabled(enabled)
        self._scale_combo.setEnabled(enabled)
        if not target:
            return
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

    # ------------------------------------------------------------------
    # Monte-Carlo-tab support
    # ------------------------------------------------------------------
    def _mc_seed_initial_row(self) -> None:
        """Drop a single empty row in so the table is never zero-rows on open."""
        if self._targets:
            self._mc_add_row()

    def _mc_add_row(self) -> None:
        if not self._targets:
            return
        row = self._mc_table.rowCount()
        self._mc_table.insertRow(row)

        comp_combo = QComboBox()
        for target in self._targets:
            comp_combo.addItem(target.display_name, target)
        comp_combo.currentIndexChanged.connect(
            lambda _idx, r=row: self._mc_refresh_parameter_combo(r)
        )
        self._mc_table.setCellWidget(row, 0, comp_combo)

        param_combo = QComboBox()
        self._mc_table.setCellWidget(row, 1, param_combo)
        self._mc_refresh_parameter_combo(row)

        dist_combo = QComboBox()
        for kind in _DISTRIBUTIONS:
            dist_combo.addItem(kind)
        self._mc_table.setCellWidget(row, 2, dist_combo)

        low_spin = QDoubleSpinBox()
        low_spin.setDecimals(9)
        low_spin.setRange(-1e15, 1e15)
        low_spin.setValue(0.0)
        self._mc_table.setCellWidget(row, 3, low_spin)

        high_spin = QDoubleSpinBox()
        high_spin.setDecimals(9)
        high_spin.setRange(-1e15, 1e15)
        high_spin.setValue(1.0)
        self._mc_table.setCellWidget(row, 4, high_spin)

    def _mc_refresh_parameter_combo(self, row: int) -> None:
        comp_combo = self._mc_table.cellWidget(row, 0)
        param_combo = self._mc_table.cellWidget(row, 1)
        if not isinstance(comp_combo, QComboBox) or not isinstance(
            param_combo, QComboBox
        ):
            return
        target = comp_combo.currentData()
        param_combo.clear()
        if isinstance(target, _SweepTarget):
            for name in target.parameters.keys():
                param_combo.addItem(name)

    def _mc_remove_selected(self) -> None:
        for row in sorted(
            {idx.row() for idx in self._mc_table.selectedIndexes()}, reverse=True
        ):
            self._mc_table.removeRow(row)

    # ------------------------------------------------------------------
    # Validation + acceptance
    # ------------------------------------------------------------------
    def _accept_if_valid(self) -> None:
        if self._mode == self.MODE_RANGE:
            if not self._current_target() or not self._parameter_combo.currentText():
                return
        else:
            settings = self._build_monte_carlo_settings()
            if settings is None:
                return
            ok, _ = settings.is_runnable()
            if not ok:
                return
        self.accept()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_mode(self) -> str:
        return self._mode

    def get_settings(self) -> ParameterSweepSettings | None:
        """Return range-mode settings (None if MC mode is active)."""
        if self._mode != self.MODE_RANGE:
            return None
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
            parallel_workers=self._parallel_spin.value()
            if self._parallel_check.isChecked()
            else 1,
            baseline_value=self._current_parameter_value(),
        )

    def get_monte_carlo_settings(self) -> MonteCarloSweepSettings | None:
        """Return Monte-Carlo settings (None if range mode is active)."""
        if self._mode != self.MODE_MONTE_CARLO:
            return None
        return self._build_monte_carlo_settings()

    # ------------------------------------------------------------------
    # MC settings collector
    # ------------------------------------------------------------------
    def _build_monte_carlo_settings(self) -> MonteCarloSweepSettings | None:
        rows: list[MonteCarloParameter] = []
        for row in range(self._mc_table.rowCount()):
            comp_combo = self._mc_table.cellWidget(row, 0)
            param_combo = self._mc_table.cellWidget(row, 1)
            dist_combo = self._mc_table.cellWidget(row, 2)
            low_spin = self._mc_table.cellWidget(row, 3)
            high_spin = self._mc_table.cellWidget(row, 4)
            if not all(
                isinstance(w, QComboBox)
                for w in (comp_combo, param_combo, dist_combo)
            ):
                continue
            target = comp_combo.currentData()
            if not isinstance(target, _SweepTarget):
                continue
            param_name = param_combo.currentText()
            if not param_name:
                continue
            dist = dist_combo.currentText()
            low = low_spin.value() if isinstance(low_spin, QDoubleSpinBox) else 0.0
            high = high_spin.value() if isinstance(high_spin, QDoubleSpinBox) else 1.0
            if dist == "normal":
                # Column 3 = mu, column 4 = sigma.
                params = {"mu": float(low), "sigma": float(high)}
            elif dist == "cartesian":
                # Tiny convention: treat low/high as a 2-point cartesian
                # list. Users wanting full lists can edit MC in code today.
                params = {"values": (float(low), float(high))}
            else:
                params = {"low": float(low), "high": float(high)}
            rows.append(
                MonteCarloParameter(
                    component_id=str(target.component.id),
                    component_name=target.display_name,
                    parameter_name=param_name,
                    distribution=dist,
                    params=params,
                )
            )

        if not rows:
            return None

        seed_value = self._mc_seed_spin.value()
        seed = None if seed_value < 0 else int(seed_value)

        return MonteCarloSweepSettings(
            parameters=rows,
            metrics=[
                MonteCarloMetric(
                    kind=self._mc_metric_kind.currentText(),
                    channel=self._mc_metric_channel.currentText() or "V(out)",
                )
            ],
            n_samples=int(self._mc_samples_spin.value()),
            seed=seed,
            n_workers=int(self._mc_workers_spin.value()),
        )
