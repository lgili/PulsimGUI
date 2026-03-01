"""Preferences dialog for application settings."""

from pathlib import Path

from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.backend_runtime_service import (
    DEFAULT_BACKEND_TARGET_VERSION,
    BackendRuntimeConfig,
)
from pulsimgui.services.settings_service import SettingsService
from pulsimgui.services.simulation_service import SimulationService


class PreferencesDialog(QDialog):
    """Dialog for editing application preferences."""

    def __init__(
        self,
        settings: SettingsService,
        simulation_service: SimulationService | None,
        parent=None,
    ):
        super().__init__(parent)
        self._settings = settings
        self._simulation_service = simulation_service
        self._backend_infos: dict[str, BackendInfo] = {}

        self.setWindowTitle("Preferences")
        self.setMinimumSize(500, 400)

        self._setup_ui()
        self._load_settings()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Tab widget for categories
        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # Add tabs
        self._tabs.addTab(self._create_general_tab(), "General")
        self._tabs.addTab(self._create_editor_tab(), "Editor")
        self._tabs.addTab(self._create_simulation_tab(), "Simulation")

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self._apply_settings
        )
        layout.addWidget(button_box)

    def _create_general_tab(self) -> QWidget:
        """Create the General settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Appearance group
        appearance_group = QGroupBox("Appearance")
        appearance_layout = QFormLayout(appearance_group)

        self._theme_combo = QComboBox()
        self._theme_combo.addItem("Light", "light")
        self._theme_combo.addItem("Dark", "dark")
        self._theme_combo.addItem("Modern Dark", "modern_dark")
        appearance_layout.addRow("Theme:", self._theme_combo)

        layout.addWidget(appearance_group)

        # Projects group
        projects_group = QGroupBox("Projects")
        projects_layout = QFormLayout(projects_group)

        # Default project location
        location_layout = QHBoxLayout()
        self._project_location_edit = QLineEdit()
        self._project_location_edit.setReadOnly(True)
        location_layout.addWidget(self._project_location_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_project_location)
        location_layout.addWidget(browse_btn)

        projects_layout.addRow("Default location:", location_layout)

        layout.addWidget(projects_group)

        # Auto-save group
        autosave_group = QGroupBox("Auto-save")
        autosave_layout = QFormLayout(autosave_group)

        self._autosave_checkbox = QCheckBox("Enable auto-save")
        autosave_layout.addRow(self._autosave_checkbox)

        self._autosave_interval_spin = QSpinBox()
        self._autosave_interval_spin.setRange(1, 60)
        self._autosave_interval_spin.setSuffix(" minutes")
        autosave_layout.addRow("Interval:", self._autosave_interval_spin)

        layout.addWidget(autosave_group)

        layout.addStretch()
        return widget

    def _create_editor_tab(self) -> QWidget:
        """Create the Editor settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # Grid group
        grid_group = QGroupBox("Grid")
        grid_layout = QFormLayout(grid_group)

        self._show_grid_checkbox = QCheckBox("Show grid")
        grid_layout.addRow(self._show_grid_checkbox)

        self._snap_grid_checkbox = QCheckBox("Snap to grid")
        grid_layout.addRow(self._snap_grid_checkbox)

        self._grid_size_spin = QDoubleSpinBox()
        self._grid_size_spin.setRange(0.5, 50.0)
        self._grid_size_spin.setDecimals(1)
        self._grid_size_spin.setSuffix(" mm")
        grid_layout.addRow("Grid size:", self._grid_size_spin)

        layout.addWidget(grid_group)

        # Components group
        components_group = QGroupBox("Components")
        components_layout = QFormLayout(components_group)

        self._show_labels_checkbox = QCheckBox("Show component labels")
        self._show_labels_checkbox.setChecked(True)
        components_layout.addRow(self._show_labels_checkbox)

        self._show_values_checkbox = QCheckBox("Show component values")
        self._show_values_checkbox.setChecked(True)
        components_layout.addRow(self._show_values_checkbox)

        layout.addWidget(components_group)

        layout.addStretch()
        return widget

    def _create_simulation_tab(self) -> QWidget:
        """Create the Simulation settings tab."""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        backend_group = QGroupBox("Backend")
        backend_layout = QFormLayout(backend_group)

        self._backend_combo = QComboBox()
        self._backend_combo.currentIndexChanged.connect(self._on_backend_selection_changed)
        backend_layout.addRow("Active backend:", self._backend_combo)

        self._backend_version_label = QLabel("-")
        backend_layout.addRow("Version:", self._backend_version_label)

        self._backend_status_label = QLabel("-")
        self._backend_status_label.setWordWrap(True)
        backend_layout.addRow("Status:", self._backend_status_label)

        self._backend_location_label = QLabel("-")
        self._backend_location_label.setWordWrap(True)
        backend_layout.addRow("Location:", self._backend_location_label)

        self._backend_capabilities_label = QLabel("-")
        self._backend_capabilities_label.setWordWrap(True)
        backend_layout.addRow("Capabilities:", self._backend_capabilities_label)

        layout.addWidget(backend_group)

        runtime_group = QGroupBox("Backend Runtime")
        runtime_layout = QFormLayout(runtime_group)

        self._backend_source_combo = QComboBox()
        self._backend_source_combo.addItem("PyPI", "pypi")
        self._backend_source_combo.addItem("Local PulsimCore checkout", "local")
        self._backend_source_combo.currentIndexChanged.connect(self._on_runtime_source_changed)
        runtime_layout.addRow("Source:", self._backend_source_combo)

        self._backend_target_version_edit = QLineEdit()
        self._backend_target_version_edit.setPlaceholderText(
            f"e.g. {DEFAULT_BACKEND_TARGET_VERSION} (or {DEFAULT_BACKEND_TARGET_VERSION.lstrip('v')})"
        )
        runtime_layout.addRow("Target version:", self._backend_target_version_edit)

        local_layout = QHBoxLayout()
        self._backend_local_path_edit = QLineEdit()
        self._backend_local_path_edit.setPlaceholderText("Path to PulsimCore checkout")
        local_layout.addWidget(self._backend_local_path_edit)
        self._backend_local_path_btn = QPushButton("Browse...")
        self._backend_local_path_btn.clicked.connect(self._browse_backend_local_path)
        local_layout.addWidget(self._backend_local_path_btn)
        self._backend_local_path_widget = QWidget()
        self._backend_local_path_widget.setLayout(local_layout)
        runtime_layout.addRow("Local path:", self._backend_local_path_widget)

        self._backend_auto_sync_check = QCheckBox("Auto-sync backend on startup")
        runtime_layout.addRow(self._backend_auto_sync_check)

        self._backend_install_button = QPushButton("Install / Update Backend")
        self._backend_install_button.clicked.connect(self._on_install_backend_runtime)
        runtime_layout.addRow(self._backend_install_button)

        self._backend_runtime_status_label = QLabel("-")
        self._backend_runtime_status_label.setWordWrap(True)
        runtime_layout.addRow("Runtime status:", self._backend_runtime_status_label)

        layout.addWidget(runtime_group)

        # Solver group
        solver_group = QGroupBox("Solver")
        solver_layout = QFormLayout(solver_group)

        self._solver_combo = QComboBox()
        self._solver_combo.addItems(["Auto", "RK4", "RK45", "BDF"])
        solver_layout.addRow("Default solver:", self._solver_combo)

        self._max_step_spin = QDoubleSpinBox()
        self._max_step_spin.setRange(0.001, 1000.0)
        self._max_step_spin.setDecimals(3)
        self._max_step_spin.setSuffix(" us")
        self._max_step_spin.setValue(1.0)
        solver_layout.addRow("Max step size:", self._max_step_spin)

        layout.addWidget(solver_group)

        # Output group
        output_group = QGroupBox("Output")
        output_layout = QFormLayout(output_group)

        self._output_points_spin = QSpinBox()
        self._output_points_spin.setRange(100, 100000)
        self._output_points_spin.setValue(10000)
        output_layout.addRow("Output points:", self._output_points_spin)

        layout.addWidget(output_group)

        layout.addStretch()

        self._populate_backend_options()
        return widget

    def _populate_backend_options(self) -> None:
        if not hasattr(self, "_backend_combo"):
            return

        self._backend_combo.blockSignals(True)
        self._backend_combo.clear()

        if not self._simulation_service:
            self._backend_combo.addItem("Demo backend", "placeholder")
            self._backend_combo.setEnabled(False)
            self._apply_backend_details(None)
            self._backend_combo.blockSignals(False)
            return

        infos = self._simulation_service.available_backends
        self._backend_infos = {info.identifier: info for info in infos}

        for info in infos:
            self._backend_combo.addItem(info.label(), info.identifier)

        active_id = self._simulation_service.backend_info.identifier
        index = next(
            (idx for idx in range(self._backend_combo.count()) if self._backend_combo.itemData(idx) == active_id),
            0,
        )
        self._backend_combo.setCurrentIndex(index)
        self._backend_combo.setEnabled(not self._simulation_service.is_running)

        active_info = self._backend_infos.get(active_id, self._simulation_service.backend_info)
        self._apply_backend_details(active_info)
        self._backend_combo.blockSignals(False)

    def _apply_backend_details(self, info: BackendInfo | None) -> None:
        if info is None:
            self._backend_version_label.setText("-")
            self._backend_status_label.setText("Simulation service unavailable")
            self._backend_location_label.setText("-")
            self._backend_capabilities_label.setText("-")
            return

        self._backend_version_label.setText(info.version or "-")
        status_text = info.message or info.status or "-"
        self._backend_status_label.setText(status_text)
        self._backend_location_label.setText(info.location or "-")
        capabilities = ", ".join(sorted(info.capabilities)) if info.capabilities else "-"
        self._backend_capabilities_label.setText(capabilities)

    def _on_backend_selection_changed(self, index: int) -> None:
        if not self._simulation_service or index < 0:
            return
        identifier = self._backend_combo.itemData(index)
        if not identifier:
            return

        current_id = self._simulation_service.backend_info.identifier
        if identifier == current_id:
            info = self._backend_infos.get(identifier, self._simulation_service.backend_info)
            self._apply_backend_details(info)
            return

        try:
            info = self._simulation_service.set_backend_preference(identifier)
        except Exception as exc:  # pragma: no cover - UI feedback only
            QMessageBox.warning(self, "Backend Selection", str(exc))
            self._populate_backend_options()
            return

        self._backend_infos[identifier] = info
        self._apply_backend_details(info)
        self._backend_combo.setEnabled(not self._simulation_service.is_running)

    def _on_runtime_source_changed(self, index: int) -> None:
        source = self._backend_source_combo.itemData(index) if index >= 0 else "pypi"
        is_local = source == "local"
        self._backend_local_path_widget.setVisible(is_local)

    def _browse_backend_local_path(self) -> None:
        initial = self._backend_local_path_edit.text() or str(Path.cwd())
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select PulsimCore Checkout",
            initial,
        )
        if directory:
            self._backend_local_path_edit.setText(directory)

    def _runtime_config_from_ui(self) -> BackendRuntimeConfig:
        return BackendRuntimeConfig(
            target_version=self._backend_target_version_edit.text().strip(),
            source=self._backend_source_combo.currentData() or "pypi",
            local_path=self._backend_local_path_edit.text().strip(),
            auto_sync=self._backend_auto_sync_check.isChecked(),
        )

    def _on_install_backend_runtime(self) -> None:
        if not self._simulation_service:
            QMessageBox.warning(self, "Backend Runtime", "Simulation service unavailable.")
            return

        config = self._runtime_config_from_ui()
        if config.normalized_source == "local" and not config.local_path.strip():
            QMessageBox.warning(self, "Backend Runtime", "Select a local PulsimCore path first.")
            return

        self._backend_runtime_status_label.setText("Installing backend...")
        QApplication.processEvents()

        self._backend_install_button.setEnabled(False)
        try:
            result = self._simulation_service.install_backend_runtime(config, force=True)
        finally:
            self._backend_install_button.setEnabled(True)

        self._backend_runtime_status_label.setText(result.message)
        if result.success:
            QMessageBox.information(
                self,
                "Backend Runtime",
                (
                    f"{result.message}\n\n"
                    "If a previous backend version was already loaded, restart PulsimGui "
                    "to guarantee the new version is active."
                ),
            )
            self._populate_backend_options()
        else:
            QMessageBox.warning(self, "Backend Runtime", result.message)

    def _load_settings(self) -> None:
        """Load current settings into UI."""
        # General - find theme by data
        theme = self._settings.get_theme()
        for i in range(self._theme_combo.count()):
            if self._theme_combo.itemData(i) == theme:
                self._theme_combo.setCurrentIndex(i)
                break

        self._project_location_edit.setText(self._settings.get_default_project_location())
        self._autosave_checkbox.setChecked(self._settings.get_auto_save_enabled())
        self._autosave_interval_spin.setValue(self._settings.get_auto_save_interval())

        # Editor
        self._show_grid_checkbox.setChecked(self._settings.get_show_grid())
        self._snap_grid_checkbox.setChecked(self._settings.get_snap_to_grid())
        self._grid_size_spin.setValue(self._settings.get_grid_size())

        # Simulation defaults
        sim_settings = self._settings.get_simulation_settings()
        solver_map = {"auto": 0, "rk4": 1, "rk45": 2, "bdf": 3}
        self._solver_combo.setCurrentIndex(solver_map.get(sim_settings.get("solver", "auto"), 0))
        self._max_step_spin.setValue(float(sim_settings.get("max_step", 1e-6)) * 1e6)
        self._output_points_spin.setValue(int(sim_settings.get("output_points", 10000)))

        runtime_settings = self._settings.get_backend_runtime_settings()
        source = runtime_settings.get("source", "pypi")
        source_index = next(
            (idx for idx in range(self._backend_source_combo.count()) if self._backend_source_combo.itemData(idx) == source),
            0,
        )
        self._backend_source_combo.setCurrentIndex(source_index)
        self._backend_target_version_edit.setText(str(runtime_settings.get("target_version", "") or ""))

        local_path = str(runtime_settings.get("local_path", "") or "")
        if not local_path:
            local_path = self._suggest_local_backend_path()
        self._backend_local_path_edit.setText(local_path)
        self._backend_auto_sync_check.setChecked(bool(runtime_settings.get("auto_sync", False)))
        self._on_runtime_source_changed(self._backend_source_combo.currentIndex())

    def _apply_settings(self) -> None:
        """Apply settings without closing dialog."""
        # General - get theme from combo data
        theme = self._theme_combo.currentData()
        self._settings.set_theme(theme)

        self._settings.set_default_project_location(self._project_location_edit.text())
        self._settings.set_auto_save_enabled(self._autosave_checkbox.isChecked())
        self._settings.set_auto_save_interval(self._autosave_interval_spin.value())

        # Editor
        self._settings.set_show_grid(self._show_grid_checkbox.isChecked())
        self._settings.set_snap_to_grid(self._snap_grid_checkbox.isChecked())
        self._settings.set_grid_size(self._grid_size_spin.value())

        # Simulation defaults
        solver_map = {0: "auto", 1: "rk4", 2: "rk45", 3: "bdf"}
        self._settings.set_simulation_settings(
            {
                "solver": solver_map.get(self._solver_combo.currentIndex(), "auto"),
                "max_step": self._max_step_spin.value() * 1e-6,
                "output_points": self._output_points_spin.value(),
            }
        )

        runtime_config = self._runtime_config_from_ui()
        self._settings.set_backend_runtime_settings(runtime_config.to_dict())
        if self._simulation_service:
            self._simulation_service.update_backend_runtime_config(runtime_config)

    def _suggest_local_backend_path(self) -> str:
        """Best-effort suggestion for a sibling PulsimCore checkout."""
        cwd = Path.cwd()
        candidates = [cwd / "PulsimCore", cwd.parent / "PulsimCore"]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        return ""

    def _on_accept(self) -> None:
        """Handle OK button."""
        self._apply_settings()
        self.accept()

    def _browse_project_location(self) -> None:
        """Browse for default project location."""
        directory = QFileDialog.getExistingDirectory(
            self,
            "Select Default Project Location",
            self._project_location_edit.text(),
        )
        if directory:
            self._project_location_edit.setText(directory)
