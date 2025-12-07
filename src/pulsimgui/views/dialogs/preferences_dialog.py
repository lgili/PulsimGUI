"""Preferences dialog for application settings."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QFormLayout,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QDialogButtonBox,
    QGroupBox,
    QLabel,
)

from pulsimgui.services.settings_service import SettingsService


class PreferencesDialog(QDialog):
    """Dialog for editing application preferences."""

    def __init__(self, settings: SettingsService, parent=None):
        super().__init__(parent)
        self._settings = settings

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
        return widget

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
