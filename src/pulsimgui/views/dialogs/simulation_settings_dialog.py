"""Simulation settings dialog."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QGroupBox,
    QDialogButtonBox,
    QLabel,
    QCheckBox,
)

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.views.properties import SILineEdit


class SimulationSettingsDialog(QDialog):
    """Dialog for configuring simulation settings."""

    def __init__(
        self,
        settings: SimulationSettings,
        backend_info: BackendInfo | None = None,
        backend_warning: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._backend_info = backend_info
        self._backend_warning = backend_warning

        self.setWindowTitle("Simulation Settings")
        self.setMinimumSize(450, 400)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        if self._backend_info or self._backend_warning:
            layout.addWidget(self._create_backend_banner())

        # Tab widget
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Tabs
        self._tabs.addTab(self._create_transient_tab(), "Transient")
        self._tabs.addTab(self._create_solver_tab(), "Solver")
        self._tabs.addTab(self._create_output_tab(), "Output")

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _create_backend_banner(self) -> QWidget:
        group = QGroupBox("Backend Status")
        form = QFormLayout(group)

        self._backend_name_label = QLabel("-")
        form.addRow("Backend:", self._backend_name_label)

        self._backend_version_label = QLabel("-")
        form.addRow("Version:", self._backend_version_label)

        self._backend_status_label = QLabel("-")
        self._backend_status_label.setWordWrap(True)
        form.addRow("Status:", self._backend_status_label)

        self._backend_capabilities_label = QLabel("-")
        self._backend_capabilities_label.setWordWrap(True)
        form.addRow("Capabilities:", self._backend_capabilities_label)

        warning_text = self._backend_warning or ""
        self._backend_warning_label = QLabel(warning_text)
        self._backend_warning_label.setWordWrap(True)
        self._backend_warning_label.setStyleSheet("color: #b35a00;")
        self._backend_warning_label.setVisible(bool(warning_text))
        form.addRow("Warning:", self._backend_warning_label)

        self._refresh_backend_banner()
        return group

    def _refresh_backend_banner(self) -> None:
        info = self._backend_info
        if not info:
            self._backend_name_label.setText("No backend detected")
            self._backend_version_label.setText("-")
            self._backend_status_label.setText(self._backend_warning or "Install Pulsim to enable simulations.")
            self._backend_capabilities_label.setText("-")
            return

        self._backend_name_label.setText(info.name or info.identifier)
        self._backend_version_label.setText(info.version or "-")
        status = info.message or info.status or "available"
        self._backend_status_label.setText(status)
        capabilities = ", ".join(sorted(info.capabilities)) if info.capabilities else "-"
        self._backend_capabilities_label.setText(capabilities)

    def _create_transient_tab(self) -> QWidget:
        """Create transient simulation settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Time settings group
        time_group = QGroupBox("Time Settings")
        time_layout = QFormLayout(time_group)

        self._t_start_edit = SILineEdit("s")
        time_layout.addRow("Start time:", self._t_start_edit)

        self._t_stop_edit = SILineEdit("s")
        time_layout.addRow("Stop time:", self._t_stop_edit)

        self._t_step_edit = SILineEdit("s")
        time_layout.addRow("Time step:", self._t_step_edit)

        layout.addWidget(time_group)

        # Quick presets
        preset_group = QGroupBox("Quick Presets")
        preset_layout = QHBoxLayout(preset_group)

        from functools import partial

        presets = [
            ("1µs", 1e-6),
            ("10µs", 10e-6),
            ("100µs", 100e-6),
            ("1ms", 1e-3),
            ("10ms", 10e-3),
            ("100ms", 100e-3),
        ]

        for name, duration in presets:
            from PySide6.QtWidgets import QPushButton

            btn = QPushButton(name)
            btn.clicked.connect(partial(self._set_duration_preset, duration))
            preset_layout.addWidget(btn)

        layout.addWidget(preset_group)

        layout.addStretch()
        return widget

    def _create_solver_tab(self) -> QWidget:
        """Create solver settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Solver selection group
        solver_group = QGroupBox("Integration Method")
        solver_layout = QFormLayout(solver_group)

        self._solver_combo = QComboBox()
        self._solver_combo.addItems(["Auto", "RK4 (Fixed Step)", "RK45 (Adaptive)", "BDF (Stiff)"])
        solver_layout.addRow("Method:", self._solver_combo)

        # Solver description
        self._solver_desc = QLabel("")
        self._solver_desc.setWordWrap(True)
        self._solver_desc.setStyleSheet("color: gray; font-size: 11px;")
        solver_layout.addRow(self._solver_desc)
        self._solver_combo.currentIndexChanged.connect(self._update_solver_description)

        layout.addWidget(solver_group)

        # Newton solver settings group
        newton_group = QGroupBox("Newton Solver")
        newton_layout = QFormLayout(newton_group)

        self._max_iterations_spin = QSpinBox()
        self._max_iterations_spin.setRange(10, 500)
        self._max_iterations_spin.setValue(50)
        self._max_iterations_spin.setToolTip("Maximum Newton iterations per timestep")
        newton_layout.addRow("Max iterations:", self._max_iterations_spin)

        self._voltage_limiting_check = QCheckBox("Enable voltage limiting")
        self._voltage_limiting_check.setChecked(True)
        self._voltage_limiting_check.setToolTip("Limit voltage changes to prevent divergence")
        newton_layout.addRow(self._voltage_limiting_check)

        self._max_voltage_step_spin = QDoubleSpinBox()
        self._max_voltage_step_spin.setRange(0.1, 100.0)
        self._max_voltage_step_spin.setValue(5.0)
        self._max_voltage_step_spin.setSuffix(" V")
        self._max_voltage_step_spin.setToolTip("Maximum voltage change per iteration")
        newton_layout.addRow("Max voltage step:", self._max_voltage_step_spin)

        self._voltage_limiting_check.toggled.connect(self._max_voltage_step_spin.setEnabled)

        layout.addWidget(newton_group)

        # DC Strategy group
        dc_group = QGroupBox("DC Operating Point Strategy")
        dc_layout = QFormLayout(dc_group)

        self._dc_strategy_combo = QComboBox()
        self._dc_strategy_combo.addItems([
            "Auto",
            "Direct Newton",
            "GMIN Stepping",
            "Source Stepping",
            "Pseudo-Transient",
        ])
        self._dc_strategy_combo.setToolTip("Strategy for finding DC operating point")
        dc_layout.addRow("Strategy:", self._dc_strategy_combo)

        # DC strategy description
        self._dc_strategy_desc = QLabel("")
        self._dc_strategy_desc.setWordWrap(True)
        self._dc_strategy_desc.setStyleSheet("color: gray; font-size: 11px;")
        dc_layout.addRow(self._dc_strategy_desc)
        self._dc_strategy_combo.currentIndexChanged.connect(self._update_dc_strategy_description)

        # GMIN parameters (shown only when GMIN strategy selected)
        self._gmin_widget = QWidget()
        gmin_layout = QFormLayout(self._gmin_widget)
        gmin_layout.setContentsMargins(0, 0, 0, 0)

        self._gmin_initial_spin = QDoubleSpinBox()
        self._gmin_initial_spin.setDecimals(6)
        self._gmin_initial_spin.setRange(1e-6, 1.0)
        self._gmin_initial_spin.setValue(1e-3)
        self._gmin_initial_spin.setToolTip("Initial GMIN conductance value")
        gmin_layout.addRow("GMIN initial:", self._gmin_initial_spin)

        self._gmin_final_spin = QDoubleSpinBox()
        self._gmin_final_spin.setDecimals(15)
        self._gmin_final_spin.setRange(1e-15, 1e-6)
        self._gmin_final_spin.setValue(1e-12)
        self._gmin_final_spin.setToolTip("Final GMIN conductance value")
        gmin_layout.addRow("GMIN final:", self._gmin_final_spin)

        dc_layout.addRow(self._gmin_widget)
        self._gmin_widget.setVisible(False)

        self._dc_strategy_combo.currentIndexChanged.connect(self._on_dc_strategy_changed)

        layout.addWidget(dc_group)

        # Tolerances group
        tol_group = QGroupBox("Tolerances")
        tol_layout = QFormLayout(tol_group)

        self._max_step_edit = SILineEdit("s")
        tol_layout.addRow("Max step size:", self._max_step_edit)

        self._rel_tol_spin = QDoubleSpinBox()
        self._rel_tol_spin.setDecimals(6)
        self._rel_tol_spin.setRange(1e-10, 1e-1)
        self._rel_tol_spin.setValue(1e-4)
        self._rel_tol_spin.setSingleStep(1e-5)
        tol_layout.addRow("Relative tolerance:", self._rel_tol_spin)

        self._abs_tol_spin = QDoubleSpinBox()
        self._abs_tol_spin.setDecimals(9)
        self._abs_tol_spin.setRange(1e-12, 1e-3)
        self._abs_tol_spin.setValue(1e-6)
        self._abs_tol_spin.setSingleStep(1e-7)
        tol_layout.addRow("Absolute tolerance:", self._abs_tol_spin)

        layout.addWidget(tol_group)

        layout.addStretch()
        return widget

    def _update_dc_strategy_description(self) -> None:
        """Update DC strategy description based on selection."""
        descriptions = [
            "Automatically select the best strategy based on circuit complexity.",
            "Direct Newton-Raphson iteration. Fast for simple circuits.",
            "Gradually reduce GMIN conductance. Good for circuits with semiconductor junctions.",
            "Gradually ramp voltage/current sources. Helps with strongly nonlinear circuits.",
            "Use time-stepping to find DC point. Best for very difficult circuits.",
        ]
        idx = self._dc_strategy_combo.currentIndex()
        self._dc_strategy_desc.setText(descriptions[idx] if idx < len(descriptions) else "")

    def _on_dc_strategy_changed(self, index: int) -> None:
        """Show/hide GMIN parameters based on strategy."""
        # GMIN Stepping is index 2
        self._gmin_widget.setVisible(index == 2)
        self._update_dc_strategy_description()

    def _create_output_tab(self) -> QWidget:
        """Create output settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Output points group
        output_group = QGroupBox("Output Settings")
        output_layout = QFormLayout(output_group)

        self._output_points_spin = QSpinBox()
        self._output_points_spin.setRange(100, 1000000)
        self._output_points_spin.setValue(10000)
        self._output_points_spin.setSingleStep(1000)
        output_layout.addRow("Output points:", self._output_points_spin)

        # Calculate effective step
        self._effective_step_label = QLabel("")
        output_layout.addRow("Effective step:", self._effective_step_label)

        self._output_points_spin.valueChanged.connect(self._update_effective_step)
        self._t_stop_edit.value_changed.connect(lambda _: self._update_effective_step())
        self._t_start_edit.value_changed.connect(lambda _: self._update_effective_step())

        layout.addWidget(output_group)

        # Data saving options
        save_group = QGroupBox("Data Saving")
        save_layout = QFormLayout(save_group)

        self._save_all_check = QCheckBox("Save all node voltages")
        self._save_all_check.setChecked(True)
        save_layout.addRow(self._save_all_check)

        self._save_currents_check = QCheckBox("Save branch currents")
        self._save_currents_check.setChecked(True)
        save_layout.addRow(self._save_currents_check)

        self._save_power_check = QCheckBox("Save power dissipation")
        self._save_power_check.setChecked(False)
        save_layout.addRow(self._save_power_check)

        layout.addWidget(save_group)

        layout.addStretch()
        return widget

    def _load_settings(self) -> None:
        """Load current settings into UI."""
        self._t_start_edit.value = self._settings.t_start
        self._t_stop_edit.value = self._settings.t_stop
        self._t_step_edit.value = self._settings.t_step

        solver_map = {"auto": 0, "rk4": 1, "rk45": 2, "bdf": 3}
        self._solver_combo.setCurrentIndex(solver_map.get(self._settings.solver, 0))

        self._max_step_edit.value = self._settings.max_step
        self._rel_tol_spin.setValue(self._settings.rel_tol)
        self._abs_tol_spin.setValue(self._settings.abs_tol)

        # Newton solver settings
        self._max_iterations_spin.setValue(self._settings.max_newton_iterations)
        self._voltage_limiting_check.setChecked(self._settings.enable_voltage_limiting)
        self._max_voltage_step_spin.setValue(self._settings.max_voltage_step)
        self._max_voltage_step_spin.setEnabled(self._settings.enable_voltage_limiting)

        # DC strategy settings
        dc_strategy_map = {"auto": 0, "direct": 1, "gmin": 2, "source": 3, "pseudo": 4}
        self._dc_strategy_combo.setCurrentIndex(dc_strategy_map.get(self._settings.dc_strategy, 0))
        self._gmin_initial_spin.setValue(self._settings.gmin_initial)
        self._gmin_final_spin.setValue(self._settings.gmin_final)

        self._output_points_spin.setValue(self._settings.output_points)

        self._update_solver_description()
        self._update_dc_strategy_description()
        self._on_dc_strategy_changed(self._dc_strategy_combo.currentIndex())
        self._update_effective_step()

    def _on_accept(self) -> None:
        """Apply settings and close."""
        self._settings.t_start = self._t_start_edit.value
        self._settings.t_stop = self._t_stop_edit.value
        self._settings.t_step = self._t_step_edit.value

        solver_map = {0: "auto", 1: "rk4", 2: "rk45", 3: "bdf"}
        self._settings.solver = solver_map.get(self._solver_combo.currentIndex(), "auto")

        self._settings.max_step = self._max_step_edit.value
        self._settings.rel_tol = self._rel_tol_spin.value()
        self._settings.abs_tol = self._abs_tol_spin.value()

        # Newton solver settings
        self._settings.max_newton_iterations = self._max_iterations_spin.value()
        self._settings.enable_voltage_limiting = self._voltage_limiting_check.isChecked()
        self._settings.max_voltage_step = self._max_voltage_step_spin.value()

        # DC strategy settings
        dc_strategy_map = {0: "auto", 1: "direct", 2: "gmin", 3: "source", 4: "pseudo"}
        self._settings.dc_strategy = dc_strategy_map.get(self._dc_strategy_combo.currentIndex(), "auto")
        self._settings.gmin_initial = self._gmin_initial_spin.value()
        self._settings.gmin_final = self._gmin_final_spin.value()

        self._settings.output_points = self._output_points_spin.value()

        self.accept()

    def _set_duration_preset(self, duration: float) -> None:
        """Set stop time to a preset duration."""
        self._t_start_edit.value = 0
        self._t_stop_edit.value = duration
        self._t_step_edit.value = duration / 1000
        self._update_effective_step()

    def _update_solver_description(self) -> None:
        """Update solver description based on selection."""
        descriptions = [
            "Automatically select the best solver based on circuit characteristics.",
            "Fixed-step 4th order Runge-Kutta. Fast for non-stiff circuits.",
            "Adaptive step Runge-Kutta-Fehlberg. Good accuracy with automatic step control.",
            "Backward Differentiation Formula. Best for stiff circuits with fast/slow dynamics.",
        ]
        idx = self._solver_combo.currentIndex()
        self._solver_desc.setText(descriptions[idx] if idx < len(descriptions) else "")

    def _update_effective_step(self) -> None:
        """Update effective step display."""
        duration = self._t_stop_edit.value - self._t_start_edit.value
        points = self._output_points_spin.value()
        if points > 0 and duration > 0:
            step = duration / points
            from pulsimgui.utils.si_prefix import format_si_value

            self._effective_step_label.setText(format_si_value(step, "s"))
        else:
            self._effective_step_label.setText("-")

    def get_settings(self) -> SimulationSettings:
        """Get the configured settings."""
        return self._settings
