"""Tests for the thermal analysis service with backend integration."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.thermal_service import (
    ThermalAnalysisService,
    ThermalResult,
    ThermalDeviceResult,
    ThermalStage,
)
from pulsimgui.services.backend_types import (
    ThermalResult as BackendThermalResult,
    ThermalDeviceResult as BackendThermalDeviceResult,
    FosterStage,
    LossBreakdown,
)


def _make_circuit(count: int = 3) -> Circuit:
    circuit = Circuit(name="thermal")
    for index in range(count):
        component = Component(type=ComponentType.MOSFET_N, name=f"M{index + 1}")
        circuit.add_component(component)
    return circuit


def _make_mock_backend(has_thermal: bool = True, return_error: bool = False):
    """Create a mock backend for testing."""
    mock_backend = MagicMock()
    mock_backend.has_capability.return_value = has_thermal

    if return_error:
        backend_result = BackendThermalResult(
            error_message="Test error",
            is_synthetic=True,
        )
    else:
        backend_result = BackendThermalResult(
            time=[0.0, 0.5, 1.0],
            devices=[
                BackendThermalDeviceResult(
                    name="M1",
                    junction_temperature=[25.0, 50.0, 75.0],
                    peak_temperature=75.0,
                    steady_state_temperature=70.0,
                    losses=LossBreakdown(conduction=5.0, switching_on=1.0, switching_off=0.5),
                    foster_stages=[
                        FosterStage(resistance=0.5, capacitance=0.01),
                        FosterStage(resistance=0.3, capacitance=0.02),
                    ],
                ),
            ],
            ambient_temperature=25.0,
            is_synthetic=False,
        )
    mock_backend.run_thermal.return_value = backend_result
    return mock_backend


class TestSyntheticThermalAnalysis:
    """Tests for synthetic thermal data generation."""

    def test_build_result_uses_simulation_time(self) -> None:
        circuit = _make_circuit(2)
        electrical = SimulationResult(time=[0.0, 0.5, 1.0], signals={})
        service = ThermalAnalysisService()

        thermal = service.build_result(circuit, electrical)

        assert thermal.time == electrical.time
        assert len(thermal.devices) == 2
        assert all(len(device.stages) == 3 for device in thermal.devices)
        assert all(
            device.temperature_trace[-1] > thermal.ambient_temperature
            for device in thermal.devices
        )

    def test_empty_circuit_returns_default_timeline(self) -> None:
        service = ThermalAnalysisService()

        thermal = service.build_result(None, None)

        assert thermal.devices == []
        # Default timeline is 200 samples plus the initial point
        assert len(thermal.time) == 201

    def test_synthetic_result_has_is_synthetic_flag(self) -> None:
        """Verify synthetic results are marked as such."""
        circuit = _make_circuit(1)
        service = ThermalAnalysisService()

        thermal = service.build_result(circuit, None)

        assert thermal.is_synthetic is True

    def test_synthetic_result_has_no_error(self) -> None:
        """Verify synthetic results have no error message."""
        circuit = _make_circuit(1)
        service = ThermalAnalysisService()

        thermal = service.build_result(circuit, None)

        assert thermal.error_message == ""

    def test_empty_result_is_synthetic(self) -> None:
        """Verify empty results are marked as synthetic."""
        service = ThermalAnalysisService()

        thermal = service.build_result(None, None)

        assert thermal.is_synthetic is True


class TestBackendIntegration:
    """Tests for backend thermal analysis integration."""

    def test_uses_backend_when_available(self) -> None:
        """Test that backend is used when thermal capability is available."""
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=True)
        service = ThermalAnalysisService(backend=mock_backend)

        # Need to provide circuit_data for backend path
        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        # Should have called backend
        mock_backend.run_thermal.assert_called_once()
        # Result should not be synthetic
        assert thermal.is_synthetic is False

    def test_backend_result_conversion(self) -> None:
        """Test that backend results are properly converted."""
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=True)
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        assert len(thermal.devices) == 1
        device = thermal.devices[0]
        assert device.component_name == "M1"
        assert device.peak_temperature == 75.0
        assert device.conduction_loss == 5.0
        assert device.switching_loss == 1.5  # 1.0 + 0.5
        assert len(device.stages) == 2

    def test_fallback_to_synthetic_when_no_thermal_capability(self) -> None:
        """Test fallback to synthetic when backend lacks thermal."""
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=False)
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None)

        # Should NOT have called backend
        mock_backend.run_thermal.assert_not_called()
        # Result should be synthetic
        assert thermal.is_synthetic is True

    def test_fallback_to_synthetic_on_backend_error(self) -> None:
        """Test fallback to synthetic when backend returns error."""
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=True, return_error=True)
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        # Should have called backend (which returned error)
        mock_backend.run_thermal.assert_called_once()
        # Result should be synthetic (fallback)
        assert thermal.is_synthetic is True

    def test_fallback_to_synthetic_on_exception(self) -> None:
        """Test fallback to synthetic when backend throws exception."""
        circuit = _make_circuit(1)
        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.side_effect = RuntimeError("Backend crash")
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        # Result should be synthetic (fallback)
        assert thermal.is_synthetic is True

    def test_backend_property_setter(self) -> None:
        """Test that backend can be set after initialization."""
        service = ThermalAnalysisService()
        assert service.backend is None

        mock_backend = _make_mock_backend()
        service.backend = mock_backend

        assert service.backend is mock_backend


class TestThermalResult:
    """Tests for ThermalResult dataclass."""

    def test_total_losses_calculation(self) -> None:
        """Test total losses aggregation."""
        devices = [
            ThermalDeviceResult(
                component_id="1",
                component_name="M1",
                conduction_loss=5.0,
                switching_loss=2.0,
            ),
            ThermalDeviceResult(
                component_id="2",
                component_name="M2",
                conduction_loss=3.0,
                switching_loss=1.5,
            ),
        ]
        result = ThermalResult(devices=devices)

        assert result.total_losses() == 11.5

    def test_device_names(self) -> None:
        """Test device names extraction."""
        devices = [
            ThermalDeviceResult(component_id="1", component_name="M1"),
            ThermalDeviceResult(component_id="2", component_name="D1"),
        ]
        result = ThermalResult(devices=devices)

        assert result.device_names() == ["M1", "D1"]


class TestThermalDeviceResult:
    """Tests for ThermalDeviceResult dataclass."""

    def test_total_loss(self) -> None:
        """Test total loss calculation."""
        device = ThermalDeviceResult(
            component_id="1",
            component_name="M1",
            conduction_loss=5.0,
            switching_loss=2.0,
        )

        assert device.total_loss == 7.0

    def test_peak_temperature(self) -> None:
        """Test peak temperature extraction."""
        device = ThermalDeviceResult(
            component_id="1",
            component_name="M1",
            temperature_trace=[25.0, 50.0, 75.0, 60.0],
        )

        assert device.peak_temperature == 75.0

    def test_peak_temperature_empty_trace(self) -> None:
        """Test peak temperature with empty trace."""
        device = ThermalDeviceResult(
            component_id="1",
            component_name="M1",
            temperature_trace=[],
        )

        assert device.peak_temperature == 0.0
