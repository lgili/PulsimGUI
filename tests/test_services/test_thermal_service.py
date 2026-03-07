"""Tests for backend-only thermal analysis service."""

from unittest.mock import MagicMock

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.backend_types import (
    FosterStage,
    LossBreakdown,
)
from pulsimgui.services.backend_types import (
    ThermalDeviceResult as BackendThermalDeviceResult,
)
from pulsimgui.services.backend_types import (
    ThermalResult as BackendThermalResult,
)
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.thermal_service import (
    ThermalAnalysisService,
    ThermalDeviceResult,
    ThermalResult,
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
            is_synthetic=False,
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
                    thermal_limit=90.0,
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


class TestBackendRequirement:
    """Thermal analysis must fail explicitly without real backend support."""

    def test_build_result_fails_without_backend(self) -> None:
        circuit = _make_circuit(1)
        service = ThermalAnalysisService()

        thermal = service.build_result(circuit, None)

        assert thermal.is_synthetic is False
        assert thermal.error_message
        assert "not configured" in thermal.error_message.lower()

    def test_build_result_fails_for_empty_circuit(self) -> None:
        service = ThermalAnalysisService()

        thermal = service.build_result(None, None)

        assert thermal.is_synthetic is False
        assert thermal.error_message
        assert "no components" in thermal.error_message.lower()
        assert len(thermal.time) == 201

    def test_fails_when_backend_has_no_thermal_capability(self) -> None:
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=False)
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None)

        mock_backend.run_thermal.assert_not_called()
        assert thermal.is_synthetic is False
        assert "not supported" in thermal.error_message.lower()

    def test_fails_with_placeholder_backend_even_if_it_reports_thermal_capability(self) -> None:
        circuit = _make_circuit(1)
        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.info = type(
            "Info",
            (),
            {"identifier": "placeholder", "status": "placeholder"},
        )()
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        mock_backend.run_thermal.assert_not_called()
        assert thermal.is_synthetic is False
        assert "unavailable" in thermal.error_message.lower()

    def test_fails_when_backend_returns_error(self) -> None:
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=True, return_error=True)
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        mock_backend.run_thermal.assert_called_once()
        assert thermal.is_synthetic is False
        assert "test error" in thermal.error_message.lower()

    def test_fails_when_backend_throws_exception(self) -> None:
        circuit = _make_circuit(1)
        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.side_effect = RuntimeError("Backend crash")
        service = ThermalAnalysisService(backend=mock_backend)

        thermal = service.build_result(circuit, None, circuit_data={"components": []})

        assert thermal.is_synthetic is False
        assert "backend crash" in thermal.error_message.lower()


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
        assert thermal.error_message == ""

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
        assert device.steady_state_temperature == 70.0
        assert device.conduction_loss == 5.0
        assert device.switching_loss == 1.5  # 1.0 + 0.5
        assert device.switching_loss_on == 1.0
        assert device.switching_loss_off == 0.5
        assert device.reverse_recovery_loss == 0.0
        assert device.thermal_limit == 90.0
        assert device.exceeds_limit is False
        assert len(device.stages) == 2

    def test_backend_property_setter(self) -> None:
        """Test that backend can be set after initialization."""
        service = ThermalAnalysisService()
        assert service.backend is None

        mock_backend = _make_mock_backend()
        service.backend = mock_backend

        assert service.backend is mock_backend

    def test_service_forwards_thermal_settings_to_backend(self) -> None:
        """Runtime thermal controls should be forwarded when calling backend."""
        circuit = _make_circuit(1)
        mock_backend = _make_mock_backend(has_thermal=True)
        service = ThermalAnalysisService(backend=mock_backend)
        service.ambient_temperature = 55.0
        service.include_switching_losses = False
        service.include_conduction_losses = True
        service.thermal_network = "cauer"

        service.build_result(circuit, None, circuit_data={"components": []})

        assert mock_backend.run_thermal.called
        args, _kwargs = mock_backend.run_thermal.call_args
        settings = args[2]
        assert settings.ambient_temperature == 55.0
        assert settings.include_switching_losses is False
        assert settings.include_conduction_losses is True
        assert settings.thermal_network == "cauer"

    def test_component_identity_maps_backend_id_to_gui_name(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "MainSwitch"
        comp_id = str(component.id)

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            time=[0.0, 1.0],
            devices=[
                BackendThermalDeviceResult(
                    name=comp_id,
                    junction_temperature=[25.0, 55.0],
                    peak_temperature=55.0,
                    steady_state_temperature=55.0,
                    losses=LossBreakdown(conduction=1.0),
                    foster_stages=[FosterStage(resistance=0.5, capacitance=0.01)],
                )
            ],
            ambient_temperature=25.0,
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        thermal = service.build_result(
            circuit,
            SimulationResult(time=[0.0, 1.0], signals={}),
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "MainSwitch", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        assert thermal.error_message == ""
        assert len(thermal.devices) == 1
        assert thermal.devices[0].component_id == comp_id
        assert thermal.devices[0].component_name == "MainSwitch"

    def test_component_identity_maps_backend_default_name_when_component_has_no_name(self) -> None:
        circuit = Circuit(name="unnamed-thermal")
        component = Component(type=ComponentType.MOSFET_N, name="")
        circuit.add_component(component)
        comp_id = str(component.id)
        backend_default_name = f"{component.type.name}_{comp_id[:6]}"

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            time=[0.0, 1.0],
            devices=[
                BackendThermalDeviceResult(
                    name=backend_default_name,
                    junction_temperature=[25.0, 60.0],
                    peak_temperature=60.0,
                    steady_state_temperature=60.0,
                    losses=LossBreakdown(conduction=1.0),
                    foster_stages=[FosterStage(resistance=0.5, capacitance=0.01)],
                )
            ],
            ambient_temperature=25.0,
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        thermal = service.build_result(
            circuit,
            SimulationResult(time=[0.0, 1.0], signals={}),
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        assert thermal.error_message == ""
        assert len(thermal.devices) == 1
        assert thermal.devices[0].component_id == comp_id
        assert thermal.devices[0].component_name == "Mosfet N"

    def test_backend_error_is_reported_when_native_thermal_api_unavailable(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "M1"
        comp_id = str(component.id)

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            error_message="No compatible native thermal API available for this backend version.",
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        electrical = SimulationResult(
            time=[0.0, 1.0],
            signals={},
            statistics={
                "component_electrothermal": [
                    {
                        "component_name": "M1",
                        "thermal_enabled": True,
                        "conduction": 2.0,
                        "turn_on": 0.5,
                        "turn_off": 0.25,
                        "final_temperature": 78.0,
                        "peak_temperature": 81.0,
                    }
                ],
                "thermal_ambient": 25.0,
            },
        )

        thermal = service.build_result(
            circuit,
            electrical,
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "M1", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        assert "no compatible native thermal api" in thermal.error_message.lower()
        assert thermal.is_synthetic is False
        assert len(thermal.devices) == 0

    def test_transient_telemetry_bypasses_native_thermal_api_requirement(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "M1"
        component.parameters["thermal_limit"] = 120.0
        comp_id = str(component.id)

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            error_message="No compatible native thermal API available for this backend version.",
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        electrical = SimulationResult(
            time=[0.0, 1.0, 2.0],
            signals={"T(M1)": [25.0, 40.0, 55.0]},
            statistics={
                "component_electrothermal": [
                    {
                        "component_name": "M1",
                        "thermal_enabled": True,
                        "conduction": 2.0,
                        "turn_on": 0.5,
                        "turn_off": 0.25,
                        "reverse_recovery": 0.1,
                        "final_temperature": 55.0,
                        "peak_temperature": 55.0,
                    }
                ],
                "thermal_summary": {"ambient": 25.0},
            },
        )

        thermal = service.build_result(
            circuit,
            electrical,
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "M1", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        mock_backend.run_thermal.assert_not_called()
        assert thermal.error_message == ""
        assert thermal.is_synthetic is False
        assert len(thermal.devices) == 1
        device = thermal.devices[0]
        assert device.component_id == comp_id
        assert device.component_name == "M1"
        assert device.temperature_trace == [25.0, 40.0, 55.0]
        assert device.conduction_loss == 2.0
        assert device.switching_loss_on == 0.5
        assert device.switching_loss_off == 0.25
        assert device.reverse_recovery_loss == 0.1
        assert device.switching_loss == 0.85
        assert device.total_loss == 2.85
        assert device.thermal_limit == 120.0
        assert len(device.stages) == 1
        assert device.stages[0].resistance == 1.0
        assert device.stages[0].capacitance == 0.1

    def test_transient_telemetry_uses_staged_component_thermal_network_parameters(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "M1"
        component.parameters.update(
            {
                "thermal_enabled": True,
                "thermal_network": "foster",
                "thermal_rth_stages": "0.2,0.3",
                "thermal_cth_stages": "0.01,0.02",
                "thermal_rth": 9.9,
                "thermal_cth": 9.9,
            }
        )

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            error_message="No compatible native thermal API available for this backend version.",
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        electrical = SimulationResult(
            time=[0.0, 1.0, 2.0],
            signals={"T(M1)": [25.0, 35.0, 45.0]},
            statistics={
                "component_electrothermal": [
                    {
                        "component_name": "M1",
                        "thermal_enabled": True,
                        "conduction": 1.0,
                        "turn_on": 0.2,
                        "turn_off": 0.1,
                        "reverse_recovery": 0.0,
                        "final_temperature": 45.0,
                        "peak_temperature": 45.0,
                    }
                ]
            },
        )

        thermal = service.build_result(circuit, electrical, circuit_data=None)

        mock_backend.run_thermal.assert_not_called()
        assert thermal.error_message == ""
        assert len(thermal.devices) == 1
        stages = thermal.devices[0].stages
        assert len(stages) == 2
        assert stages[0].resistance == 0.2
        assert stages[0].capacitance == 0.01
        assert stages[1].resistance == 0.3
        assert stages[1].capacitance == 0.02

    def test_backend_error_does_not_use_transient_summary_as_thermal_trace(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "M1"
        comp_id = str(component.id)

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            error_message="native thermal unavailable",
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        electrical = SimulationResult(
            time=[0.0, 1.0, 2.0],
            signals={},
            statistics={
                "thermal_summary": {
                    "ambient": 24.0,
                    "device_temperatures": [
                        {
                            "device_name": "M1",
                            "final_temperature": 67.0,
                            "peak_temperature": 70.0,
                            "average_temperature": 64.0,
                        }
                    ],
                }
            },
        )

        thermal = service.build_result(
            circuit,
            electrical,
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "M1", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        assert "native thermal unavailable" in thermal.error_message.lower()
        assert thermal.ambient_temperature == service.ambient_temperature
        assert len(thermal.devices) == 0

    def test_native_thermal_result_without_time_is_aligned_to_electrical_timeline(self) -> None:
        circuit = _make_circuit(1)
        component = next(iter(circuit.components.values()))
        component.name = "M1"
        comp_id = str(component.id)

        mock_backend = MagicMock()
        mock_backend.has_capability.return_value = True
        mock_backend.run_thermal.return_value = BackendThermalResult(
            time=[],
            devices=[
                BackendThermalDeviceResult(
                    name="M1",
                    junction_temperature=[25.0, 50.0],
                    peak_temperature=50.0,
                    steady_state_temperature=50.0,
                    losses=LossBreakdown(conduction=1.0),
                    foster_stages=[],
                )
            ],
            ambient_temperature=25.0,
            is_synthetic=False,
        )

        service = ThermalAnalysisService(backend=mock_backend)
        electrical = SimulationResult(
            time=[0.0, 1.0, 2.0, 3.0],
            signals={},
            statistics={},
        )

        thermal = service.build_result(
            circuit,
            electrical,
            circuit_data={
                "components": [
                    {"id": comp_id, "name": "M1", "type": component.type.name, "parameters": {}}
                ]
            },
        )

        assert thermal.error_message == ""
        assert thermal.time == [0.0, 1.0, 2.0, 3.0]
        assert len(thermal.devices) == 1
        assert len(thermal.devices[0].temperature_trace) == 4


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
