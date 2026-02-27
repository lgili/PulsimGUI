"""Tests for solver options in SimulationSettingsDialog."""

from unittest.mock import MagicMock, patch

import pytest

from pulsimgui.services.backend_adapter import BackendInfo
from pulsimgui.services.simulation_service import SimulationSettings
from pulsimgui.services.backend_types import DCSettings
from pulsimgui.views.dialogs.simulation_settings_dialog import SimulationSettingsDialog


class TestUIValueChanges:
    """Tests for UI loading and saving settings correctly."""

    def test_dialog_loads_default_settings(self, qapp) -> None:
        """Test that dialog loads default settings into UI."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        # Check transient settings
        assert dialog._t_start_edit.value == 0.0
        assert dialog._t_stop_edit.value == 1e-3
        assert dialog._t_step_edit.value == 1e-6

        # Check solver settings
        assert dialog._solver_combo.currentIndex() == 0  # auto
        assert dialog._max_iterations_spin.value() == 50
        assert not dialog._voltage_limiting_check.isChecked()
        assert dialog._max_voltage_step_spin.value() == 5.0
        assert dialog._transient_robust_mode_check.isChecked()
        assert dialog._transient_auto_regularize_check.isChecked()

        # Check DC strategy
        assert dialog._dc_strategy_combo.currentIndex() == 0  # auto
        assert dialog._gmin_initial_spin.value() == 1e-3
        assert dialog._gmin_final_spin.value() == 1e-12
        assert dialog._source_steps_spin.value() == 10

        # Check tolerances
        assert dialog._rel_tol_spin.value() == 1e-4
        assert dialog._abs_tol_spin.value() == 1e-6

        # Check output
        assert dialog._output_points_spin.value() == 10000

    def test_dialog_loads_custom_settings(self, qapp) -> None:
        """Test that dialog loads custom settings correctly."""
        settings = SimulationSettings(
            t_start=1e-6,
            t_stop=5e-3,
            t_step=5e-6,
            solver="rk4",
            max_newton_iterations=100,
            enable_voltage_limiting=False,
            max_voltage_step=10.0,
            dc_strategy="source",
            gmin_initial=1e-2,
            gmin_final=1e-15,
            dc_source_steps=42,
            transient_robust_mode=False,
            transient_auto_regularize=False,
            rel_tol=1e-5,
            abs_tol=1e-9,
            output_points=5000,
        )
        dialog = SimulationSettingsDialog(settings)

        # Check transient settings
        assert dialog._t_start_edit.value == 1e-6
        assert dialog._t_stop_edit.value == 5e-3
        assert dialog._t_step_edit.value == 5e-6

        # Check solver settings
        assert dialog._solver_combo.currentIndex() == 1  # rk4
        assert dialog._max_iterations_spin.value() == 100
        assert not dialog._voltage_limiting_check.isChecked()
        assert dialog._max_voltage_step_spin.value() == 10.0
        assert not dialog._transient_robust_mode_check.isChecked()
        assert not dialog._transient_auto_regularize_check.isChecked()

        # Check DC strategy (source is index 3)
        assert dialog._dc_strategy_combo.currentIndex() == 3
        assert dialog._gmin_initial_spin.value() == 1e-2
        assert dialog._gmin_final_spin.value() == 1e-15
        assert dialog._source_steps_spin.value() == 42
        assert dialog._gmin_widget.isHidden()
        assert not dialog._source_widget.isHidden()

        # Check tolerances
        assert dialog._rel_tol_spin.value() == 1e-5
        assert dialog._abs_tol_spin.value() == 1e-9

        # Check output
        assert dialog._output_points_spin.value() == 5000

    def test_dialog_saves_settings_on_accept(self, qapp) -> None:
        """Test that dialog saves UI values back to settings."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        # Modify UI values
        dialog._t_start_edit.value = 0.0
        dialog._t_stop_edit.value = 10e-3
        dialog._t_step_edit.value = 10e-6
        dialog._solver_combo.setCurrentIndex(2)  # rk45
        dialog._max_iterations_spin.setValue(75)
        dialog._voltage_limiting_check.setChecked(False)
        dialog._max_voltage_step_spin.setValue(8.0)
        dialog._dc_strategy_combo.setCurrentIndex(3)  # source
        dialog._source_steps_spin.setValue(37)
        dialog._transient_robust_mode_check.setChecked(False)
        dialog._transient_auto_regularize_check.setChecked(True)
        dialog._gmin_initial_spin.setValue(5e-3)
        dialog._gmin_final_spin.setValue(1e-10)
        dialog._rel_tol_spin.setValue(1e-6)
        dialog._abs_tol_spin.setValue(1e-8)
        dialog._output_points_spin.setValue(20000)

        # Simulate accept
        dialog._on_accept()

        # Check settings were updated
        assert settings.t_stop == pytest.approx(10e-3)
        assert settings.t_step == pytest.approx(10e-6)
        assert settings.solver == "rk45"
        assert settings.max_newton_iterations == 75
        assert settings.enable_voltage_limiting is False
        assert settings.max_voltage_step == 8.0
        assert settings.dc_strategy == "source"
        assert settings.dc_source_steps == 37
        assert settings.transient_robust_mode is False
        assert settings.transient_auto_regularize is False
        assert settings.gmin_initial == 5e-3
        assert settings.gmin_final == 1e-10
        assert settings.rel_tol == 1e-6
        assert settings.abs_tol == 1e-8
        assert settings.output_points == 20000

    def test_accept_commits_pending_si_text_without_focus_change(self, qapp) -> None:
        """OK should commit edited SI text even if the field still has focus."""
        settings = SimulationSettings(t_stop=1e-3, max_step=1e-6)
        dialog = SimulationSettingsDialog(settings)

        # Simulate typing new values but not leaving the field.
        dialog._t_stop_edit._edit.setText("2m")
        dialog._max_step_edit._edit.setText("25u")

        dialog._on_accept()

        assert settings.t_stop == pytest.approx(2e-3)
        assert settings.max_step == pytest.approx(25e-6)

    def test_all_solver_types_load_correctly(self, qapp) -> None:
        """Test that all solver types are loaded correctly."""
        solver_map = {"auto": 0, "rk4": 1, "rk45": 2, "bdf": 3}
        for solver_name, expected_index in solver_map.items():
            settings = SimulationSettings(solver=solver_name)
            dialog = SimulationSettingsDialog(settings)
            assert dialog._solver_combo.currentIndex() == expected_index

    def test_all_dc_strategies_load_correctly(self, qapp) -> None:
        """Test that all DC strategies are loaded correctly."""
        strategy_map = {"auto": 0, "direct": 1, "gmin": 2, "source": 3, "pseudo": 4}
        for strategy_name, expected_index in strategy_map.items():
            settings = SimulationSettings(dc_strategy=strategy_name)
            dialog = SimulationSettingsDialog(settings)
            assert dialog._dc_strategy_combo.currentIndex() == expected_index

    def test_gmin_widget_visibility_on_strategy_change(self, qapp) -> None:
        """Test that GMIN widget visibility changes with strategy."""
        settings = SimulationSettings(dc_strategy="auto")
        dialog = SimulationSettingsDialog(settings)

        # Initially hidden (auto strategy) - use isHidden() since dialog not shown
        assert dialog._gmin_widget.isHidden()

        # Change to GMIN strategy
        dialog._dc_strategy_combo.setCurrentIndex(2)  # gmin
        assert not dialog._gmin_widget.isHidden()
        assert dialog._source_widget.isHidden()

        # Change to source strategy
        dialog._dc_strategy_combo.setCurrentIndex(3)  # source
        assert dialog._gmin_widget.isHidden()
        assert not dialog._source_widget.isHidden()

        # Change back to auto
        dialog._dc_strategy_combo.setCurrentIndex(0)  # auto
        assert dialog._gmin_widget.isHidden()

    def test_voltage_step_enabled_with_limiting(self, qapp) -> None:
        """Test that max voltage step is enabled/disabled with limiting checkbox."""
        settings = SimulationSettings(enable_voltage_limiting=True)
        dialog = SimulationSettingsDialog(settings)

        assert dialog._max_voltage_step_spin.isEnabled()

        # Disable limiting
        dialog._voltage_limiting_check.setChecked(False)
        assert not dialog._max_voltage_step_spin.isEnabled()

        # Re-enable limiting
        dialog._voltage_limiting_check.setChecked(True)
        assert dialog._max_voltage_step_spin.isEnabled()

    def test_backend_info_displayed(self, qapp) -> None:
        """Test that backend info is displayed in the dialog."""
        settings = SimulationSettings()
        backend_info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="0.3.0",
            status="available",
            capabilities={"dc", "ac", "transient", "thermal"},
        )
        dialog = SimulationSettingsDialog(settings, backend_info=backend_info)

        assert dialog._backend_name_label.text() == "Pulsim"
        assert dialog._backend_version_label.text() == "0.3.0"
        assert "ac" in dialog._backend_capabilities_label.text()

    def test_backend_warning_displayed(self, qapp) -> None:
        """Test that backend warning is displayed when provided."""
        settings = SimulationSettings()
        warning = "Backend version is outdated"
        dialog = SimulationSettingsDialog(
            settings, backend_warning=warning
        )

        assert dialog._backend_warning_label.text() == warning
        # Use isHidden() since dialog not shown yet
        assert not dialog._backend_warning_label.isHidden()


class TestPersistence:
    """Tests for settings persistence to user preferences."""

    def test_settings_survive_dialog_roundtrip(self, qapp) -> None:
        """Test that settings survive dialog close and reopen."""
        # Create initial settings
        settings = SimulationSettings(
            solver="bdf",
            max_newton_iterations=80,
            dc_strategy="pseudo",
        )

        # Open dialog, modify, and accept
        dialog1 = SimulationSettingsDialog(settings)
        dialog1._solver_combo.setCurrentIndex(1)  # rk4
        dialog1._max_iterations_spin.setValue(120)
        dialog1._dc_strategy_combo.setCurrentIndex(1)  # direct
        dialog1._on_accept()

        # Check settings updated
        assert settings.solver == "rk4"
        assert settings.max_newton_iterations == 120
        assert settings.dc_strategy == "direct"

        # Open another dialog with same settings
        dialog2 = SimulationSettingsDialog(settings)

        # Values should persist
        assert dialog2._solver_combo.currentIndex() == 1  # rk4
        assert dialog2._max_iterations_spin.value() == 120
        assert dialog2._dc_strategy_combo.currentIndex() == 1  # direct

    def test_get_settings_returns_modified_settings(self, qapp) -> None:
        """Test that get_settings returns the modified settings object."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        dialog._max_iterations_spin.setValue(200)
        dialog._on_accept()

        returned_settings = dialog.get_settings()
        assert returned_settings is settings
        assert returned_settings.max_newton_iterations == 200

    def test_settings_not_modified_on_reject(self, qapp) -> None:
        """Test that settings are not modified when dialog is rejected."""
        original_iterations = 50
        settings = SimulationSettings(max_newton_iterations=original_iterations)
        dialog = SimulationSettingsDialog(settings)

        # Modify UI but don't accept
        dialog._max_iterations_spin.setValue(200)

        # Settings should still have original value (not calling _on_accept)
        assert settings.max_newton_iterations == original_iterations


class TestBackendReceivesOptions:
    """Tests for DCSettings being built correctly from SimulationSettings."""

    def test_dc_settings_from_simulation_settings_default(self) -> None:
        """Test DCSettings creation with default SimulationSettings values."""
        sim_settings = SimulationSettings()

        dc_settings = DCSettings(
            strategy=sim_settings.dc_strategy,
            max_iterations=sim_settings.max_newton_iterations,
            enable_limiting=sim_settings.enable_voltage_limiting,
            max_voltage_step=sim_settings.max_voltage_step,
            gmin_initial=sim_settings.gmin_initial,
            gmin_final=sim_settings.gmin_final,
        )

        assert dc_settings.strategy == "auto"
        assert dc_settings.max_iterations == 50
        assert dc_settings.enable_limiting is False
        assert dc_settings.max_voltage_step == 5.0
        assert dc_settings.gmin_initial == 1e-3
        assert dc_settings.gmin_final == 1e-12

    def test_dc_settings_from_simulation_settings_custom(self) -> None:
        """Test DCSettings creation with custom SimulationSettings values."""
        sim_settings = SimulationSettings(
            dc_strategy="gmin",
            max_newton_iterations=100,
            enable_voltage_limiting=False,
            max_voltage_step=10.0,
            gmin_initial=5e-3,
            gmin_final=1e-15,
        )

        dc_settings = DCSettings(
            strategy=sim_settings.dc_strategy,
            max_iterations=sim_settings.max_newton_iterations,
            enable_limiting=sim_settings.enable_voltage_limiting,
            max_voltage_step=sim_settings.max_voltage_step,
            gmin_initial=sim_settings.gmin_initial,
            gmin_final=sim_settings.gmin_final,
        )

        assert dc_settings.strategy == "gmin"
        assert dc_settings.max_iterations == 100
        assert dc_settings.enable_limiting is False
        assert dc_settings.max_voltage_step == 10.0
        assert dc_settings.gmin_initial == 5e-3
        assert dc_settings.gmin_final == 1e-15

    def test_all_dc_strategies_map_correctly(self) -> None:
        """Test that all DC strategy strings map correctly."""
        strategies = ["auto", "direct", "gmin", "source", "pseudo"]
        for strategy in strategies:
            sim_settings = SimulationSettings(dc_strategy=strategy)
            dc_settings = DCSettings(strategy=sim_settings.dc_strategy)
            assert dc_settings.strategy == strategy

    def test_backend_build_dc_options_integration(self) -> None:
        """Test that PulsimBackend._build_dc_options uses DCSettings correctly."""
        from unittest.mock import MagicMock

        # Create mock module with NewtonOptions
        mock_module = MagicMock()
        mock_opts = MagicMock()
        mock_opts.max_iterations = 0
        mock_opts.tolerance = 0.0
        mock_opts.enable_limiting = False
        mock_opts.max_voltage_step = 0.0
        mock_module.NewtonOptions.return_value = mock_opts

        dc_settings = DCSettings(
            strategy="direct",
            max_iterations=75,
            tolerance=1e-10,
            enable_limiting=True,
            max_voltage_step=7.5,
        )

        # Import and create backend
        from pulsimgui.services.backend_adapter import PulsimBackend, BackendInfo

        backend_info = BackendInfo(
            identifier="test",
            name="Test",
            version="1.0.0",
            status="test",
        )
        backend = PulsimBackend(mock_module, backend_info)

        # Build options
        opts = backend._build_dc_options(dc_settings)

        # Verify the options were set
        assert opts.max_iterations == 75
        assert opts.tolerance == 1e-10
        assert opts.enable_limiting is True
        assert opts.max_voltage_step == 7.5


class TestSolverDescriptions:
    """Tests for solver description updates."""

    def test_solver_description_updates_on_selection(self, qapp) -> None:
        """Test that solver description updates when selection changes."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        # Check each solver has a description
        for index in range(dialog._solver_combo.count()):
            dialog._solver_combo.setCurrentIndex(index)
            assert len(dialog._solver_desc.text()) > 0

    def test_dc_strategy_description_updates_on_selection(self, qapp) -> None:
        """Test that DC strategy description updates when selection changes."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        # Check each strategy has a description
        for index in range(dialog._dc_strategy_combo.count()):
            dialog._dc_strategy_combo.setCurrentIndex(index)
            assert len(dialog._dc_strategy_desc.text()) > 0


class TestPresetButtons:
    """Tests for duration preset buttons."""

    def test_duration_preset_updates_time_settings(self, qapp) -> None:
        """Test that duration preset buttons update time settings."""
        settings = SimulationSettings()
        dialog = SimulationSettingsDialog(settings)

        # Set a preset duration
        dialog._set_duration_preset(10e-3)  # 10ms

        assert dialog._t_start_edit.value == 0.0
        assert dialog._t_stop_edit.value == 10e-3
        assert dialog._t_step_edit.value == 10e-3 / 1000  # 10us


class TestEffectiveStepCalculation:
    """Tests for effective step calculation."""

    def test_effective_step_calculated_correctly(self, qapp) -> None:
        """Test that effective step is calculated from duration and points."""
        settings = SimulationSettings(t_start=0.0, t_stop=1e-3, output_points=1000)
        dialog = SimulationSettingsDialog(settings)

        # Effective step is 1ms / 1000 = 1e-6s = 1µs = 1000ns
        # The SI formatter may show different representations
        label_text = dialog._effective_step_label.text()
        # Check that a numeric value is displayed with a unit
        assert any(char.isdigit() for char in label_text)
        assert "s" in label_text  # seconds unit

    def test_effective_step_updates_on_output_points_change(self, qapp) -> None:
        """Test that effective step updates when output points change."""
        settings = SimulationSettings(t_start=0.0, t_stop=1e-3, output_points=1000)
        dialog = SimulationSettingsDialog(settings)

        initial_text = dialog._effective_step_label.text()

        dialog._output_points_spin.setValue(2000)

        # Label should have changed (smaller step)
        assert dialog._effective_step_label.text() != initial_text
