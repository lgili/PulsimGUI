"""Tests for backend abstraction layer types."""

from __future__ import annotations

import pytest

from pulsimgui.services.backend_types import (
    ACResult,
    ACSettings,
    BackendVersion,
    ConvergenceInfo,
    DCResult,
    DCSettings,
    FosterStage,
    IterationRecord,
    LossBreakdown,
    MIN_BACKEND_API,
    ProblematicVariable,
    ThermalDeviceResult,
    ThermalResult,
    ThermalSettings,
    TransientResult,
    TransientSettings,
)


class TestBackendVersion:
    """Tests for BackendVersion class."""

    def test_from_string_basic(self):
        """Parse a basic version string."""
        version = BackendVersion.from_string("0.2.1")
        assert version.major == 0
        assert version.minor == 2
        assert version.patch == 1
        assert version.api_version == 1

    def test_from_string_with_api_version(self):
        """Parse version string with API version suffix."""
        version = BackendVersion.from_string("1.0.0+api3")
        assert version.major == 1
        assert version.minor == 0
        assert version.patch == 0
        assert version.api_version == 3

    def test_from_string_with_prerelease(self):
        """Parse version string with prerelease suffix."""
        version = BackendVersion.from_string("0.3.0-beta")
        assert version.major == 0
        assert version.minor == 3
        assert version.patch == 0

    def test_from_string_two_parts(self):
        """Parse version string with only major.minor."""
        version = BackendVersion.from_string("1.5")
        assert version.major == 1
        assert version.minor == 5
        assert version.patch == 0

    def test_from_string_invalid(self):
        """Invalid version strings should raise ValueError."""
        with pytest.raises(ValueError):
            BackendVersion.from_string("invalid")

        with pytest.raises(ValueError):
            BackendVersion.from_string("1")

    def test_is_compatible_with_same_version(self):
        """Same version should be compatible."""
        v1 = BackendVersion(0, 2, 0, api_version=1)
        v2 = BackendVersion(0, 2, 0, api_version=1)
        assert v1.is_compatible_with(v2)

    def test_is_compatible_with_newer_version(self):
        """Newer version should be compatible with older required."""
        current = BackendVersion(0, 3, 0, api_version=1)
        required = BackendVersion(0, 2, 0, api_version=1)
        assert current.is_compatible_with(required)

    def test_is_compatible_with_older_version(self):
        """Older version should NOT be compatible with newer required."""
        current = BackendVersion(0, 1, 0, api_version=1)
        required = BackendVersion(0, 2, 0, api_version=1)
        assert not current.is_compatible_with(required)

    def test_is_compatible_with_higher_api(self):
        """Higher API version should be compatible."""
        current = BackendVersion(0, 2, 0, api_version=2)
        required = BackendVersion(0, 2, 0, api_version=1)
        assert current.is_compatible_with(required)

    def test_is_compatible_with_lower_api(self):
        """Lower API version should NOT be compatible."""
        current = BackendVersion(0, 2, 0, api_version=1)
        required = BackendVersion(0, 2, 0, api_version=2)
        assert not current.is_compatible_with(required)

    def test_str_basic(self):
        """String representation without API version."""
        version = BackendVersion(1, 2, 3, api_version=1)
        assert str(version) == "1.2.3"

    def test_str_with_api(self):
        """String representation with API version."""
        version = BackendVersion(1, 2, 3, api_version=2)
        assert str(version) == "1.2.3+api2"

    def test_min_backend_api_exists(self):
        """MIN_BACKEND_API constant should be defined."""
        assert MIN_BACKEND_API is not None
        assert isinstance(MIN_BACKEND_API, BackendVersion)


class TestConvergenceInfo:
    """Tests for ConvergenceInfo class."""

    def test_default_values(self):
        """Default values should indicate non-converged state."""
        info = ConvergenceInfo(converged=False)
        assert not info.converged
        assert info.iterations == 0
        assert info.final_residual == 0.0
        assert info.strategy_used == "newton"
        assert info.history == []
        assert info.problematic_variables == []

    def test_trend_unknown_with_insufficient_history(self):
        """Trend should be unknown with less than 3 history entries."""
        info = ConvergenceInfo(converged=False, history=[
            IterationRecord(0, 1.0),
            IterationRecord(1, 0.5),
        ])
        assert info.trend == "unknown"

    def test_trend_converging(self):
        """Trend should be converging when residual decreases."""
        info = ConvergenceInfo(converged=False, history=[
            IterationRecord(0, 1.0),
            IterationRecord(1, 0.5),
            IterationRecord(2, 0.1),
        ])
        assert info.trend == "converging"

    def test_trend_diverging(self):
        """Trend should be diverging when residual increases."""
        info = ConvergenceInfo(converged=False, history=[
            IterationRecord(0, 0.1),
            IterationRecord(1, 0.5),
            IterationRecord(2, 1.0),
        ])
        assert info.trend == "diverging"

    def test_trend_stalling(self):
        """Trend should be stalling when residual doesn't change much."""
        info = ConvergenceInfo(converged=False, history=[
            IterationRecord(0, 1.0),
            IterationRecord(1, 1.005),
            IterationRecord(2, 1.003),
        ])
        assert info.trend == "stalling"


class TestDCResult:
    """Tests for DCResult class."""

    def test_is_valid_with_data(self):
        """Result with data and no error should be valid."""
        result = DCResult(
            node_voltages={"V(out)": 5.0},
            convergence_info=ConvergenceInfo(converged=True),
        )
        assert result.is_valid

    def test_is_valid_with_error(self):
        """Result with error message should not be valid."""
        result = DCResult(
            error_message="Failed to converge",
            convergence_info=ConvergenceInfo(converged=False),
        )
        assert not result.is_valid

    def test_is_valid_not_converged(self):
        """Result that didn't converge should not be valid."""
        result = DCResult(
            node_voltages={"V(out)": 5.0},
            convergence_info=ConvergenceInfo(converged=False),
        )
        assert not result.is_valid


class TestACResult:
    """Tests for ACResult class."""

    def test_is_valid_with_data(self):
        """Result with frequencies should be valid."""
        result = ACResult(
            frequencies=[100, 1000, 10000],
            magnitude={"V(out)": [-3, -6, -20]},
            phase={"V(out)": [-45, -90, -135]},
        )
        assert result.is_valid

    def test_is_valid_empty(self):
        """Empty result should not be valid."""
        result = ACResult()
        assert not result.is_valid

    def test_is_valid_with_error(self):
        """Result with error should not be valid."""
        result = ACResult(
            frequencies=[100],
            error_message="AC failed",
        )
        assert not result.is_valid


class TestThermalResult:
    """Tests for ThermalResult class."""

    def test_is_valid_with_devices(self):
        """Result with devices should be valid."""
        device = ThermalDeviceResult(
            name="M1",
            junction_temperature=[25, 50, 75],
            peak_temperature=75,
            steady_state_temperature=70,
        )
        result = ThermalResult(
            time=[0, 0.001, 0.002],
            devices=[device],
        )
        assert result.is_valid

    def test_is_synthetic_flag(self):
        """is_synthetic flag should indicate placeholder data."""
        result = ThermalResult(is_synthetic=True)
        assert result.is_synthetic

    def test_total_losses(self):
        """Total losses should sum all device losses."""
        device1 = ThermalDeviceResult(
            name="M1",
            losses=LossBreakdown(conduction=2.0, switching_on=0.5),
        )
        device2 = ThermalDeviceResult(
            name="D1",
            losses=LossBreakdown(conduction=1.0),
        )
        result = ThermalResult(devices=[device1, device2])
        assert result.total_losses == 3.5

    def test_device_by_name(self):
        """device_by_name should find device or return None."""
        device = ThermalDeviceResult(name="M1")
        result = ThermalResult(devices=[device])

        assert result.device_by_name("M1") is device
        assert result.device_by_name("M2") is None


class TestThermalDeviceResult:
    """Tests for ThermalDeviceResult class."""

    def test_exceeds_limit_below(self):
        """Should not exceed limit when below."""
        device = ThermalDeviceResult(
            name="M1",
            peak_temperature=100,
            thermal_limit=150,
        )
        assert not device.exceeds_limit

    def test_exceeds_limit_above(self):
        """Should exceed limit when above."""
        device = ThermalDeviceResult(
            name="M1",
            peak_temperature=160,
            thermal_limit=150,
        )
        assert device.exceeds_limit

    def test_exceeds_limit_no_limit(self):
        """Should not exceed when no limit defined."""
        device = ThermalDeviceResult(
            name="M1",
            peak_temperature=200,
            thermal_limit=None,
        )
        assert not device.exceeds_limit

    def test_total_thermal_resistance(self):
        """Total thermal resistance should sum Foster stages."""
        device = ThermalDeviceResult(
            name="M1",
            foster_stages=[
                FosterStage(resistance=0.5, capacitance=0.001),
                FosterStage(resistance=1.0, capacitance=0.01),
                FosterStage(resistance=2.0, capacitance=0.1),
            ],
        )
        assert device.total_thermal_resistance == 3.5


class TestFosterStage:
    """Tests for FosterStage class."""

    def test_time_constant(self):
        """Time constant should be R * C."""
        stage = FosterStage(resistance=1.0, capacitance=0.01)
        assert stage.time_constant == 0.01


class TestLossBreakdown:
    """Tests for LossBreakdown class."""

    def test_total(self):
        """Total should sum all loss components."""
        losses = LossBreakdown(
            conduction=2.0,
            switching_on=0.3,
            switching_off=0.4,
            reverse_recovery=0.1,
        )
        assert losses.total == 2.8

    def test_switching_total(self):
        """Switching total should sum switching components."""
        losses = LossBreakdown(
            conduction=2.0,
            switching_on=0.3,
            switching_off=0.4,
            reverse_recovery=0.1,
        )
        assert abs(losses.switching_total - 0.8) < 1e-10


class TestTransientResult:
    """Tests for TransientResult class."""

    def test_is_valid_with_data(self):
        """Result with time data should be valid."""
        result = TransientResult(
            time=[0, 1e-6, 2e-6],
            signals={"V(out)": [0, 1, 2]},
        )
        assert result.is_valid

    def test_is_valid_empty(self):
        """Empty result should not be valid."""
        result = TransientResult()
        assert not result.is_valid


class TestSettingsDataclasses:
    """Tests for settings dataclasses."""

    def test_dc_settings_defaults(self):
        """DCSettings should have sensible defaults."""
        settings = DCSettings()
        assert settings.strategy == "auto"
        assert settings.max_iterations == 100
        assert settings.tolerance == 1e-9
        assert settings.enable_limiting is True
        assert settings.max_voltage_step == 5.0

    def test_ac_settings_defaults(self):
        """ACSettings should have sensible defaults."""
        settings = ACSettings()
        assert settings.f_start == 1.0
        assert settings.f_stop == 1e6
        assert settings.points_per_decade == 10

    def test_thermal_settings_defaults(self):
        """ThermalSettings should have sensible defaults."""
        settings = ThermalSettings()
        assert settings.ambient_temperature == 25.0
        assert settings.include_switching_losses is True
        assert settings.include_conduction_losses is True
        assert settings.thermal_network == "foster"

    def test_transient_settings_defaults(self):
        """TransientSettings should have sensible defaults."""
        settings = TransientSettings()
        assert settings.t_start == 0.0
        assert settings.t_stop == 1e-3
        assert settings.integration_method == "bdf2"
