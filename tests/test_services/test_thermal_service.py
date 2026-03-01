"""Tests for the synthetic thermal analysis service."""

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.services.thermal_service import ThermalAnalysisService


def _make_circuit(count: int = 3) -> Circuit:
    circuit = Circuit(name="thermal")
    for index in range(count):
        component = Component(type=ComponentType.MOSFET_N, name=f"M{index + 1}")
        circuit.add_component(component)
    return circuit


def test_build_result_uses_simulation_time() -> None:
    circuit = _make_circuit(2)
    electrical = SimulationResult(time=[0.0, 0.5, 1.0], signals={})
    service = ThermalAnalysisService()

    thermal = service.build_result(circuit, electrical)

    assert thermal.time == electrical.time
    assert len(thermal.devices) == 2
    assert all(len(device.stages) == 3 for device in thermal.devices)
    assert all(device.temperature_trace[-1] > thermal.ambient_temperature for device in thermal.devices)


def test_empty_circuit_returns_default_timeline() -> None:
    service = ThermalAnalysisService()

    thermal = service.build_result(None, None)

    assert thermal.devices == []
    # Default timeline is 200 samples plus the initial point
    assert len(thermal.time) == 201
