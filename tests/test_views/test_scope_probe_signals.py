"""Regression tests for backend-owned probe scope signals."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.main_window import MainWindow


class _ResultHost:
    """Minimal host object required by MainWindow result helpers."""

    def __init__(self, circuit: Circuit) -> None:
        self._circuit = circuit

    def _current_circuit(self) -> Circuit:
        return self._circuit


def test_voltage_probe_uses_backend_channel_by_name() -> None:
    circuit = Circuit(name="voltage-probe-by-name")
    probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP1", x=120.0, y=120.0)
    circuit.add_component(probe)

    result = SimulationResult(
        time=[0.0, 1.0],
        signals={"VP1": [3.0, 5.0]},
    )
    host = _ResultHost(circuit)
    enriched = MainWindow._result_with_probe_signals(host, result)

    key = format_signal_key("VP", "VP1")
    assert key in enriched.signals
    assert enriched.signals[key] == [3.0, 5.0]


def test_voltage_probe_uses_backend_channel_by_component_id() -> None:
    circuit = Circuit(name="voltage-probe-by-id")
    probe = Component(type=ComponentType.VOLTAGE_PROBE_GND, name="VPG1", x=120.0, y=120.0)
    circuit.add_component(probe)

    result = SimulationResult(
        time=[0.0, 1.0],
        signals={str(probe.id): [1.2, 2.4]},
    )
    host = _ResultHost(circuit)
    enriched = MainWindow._result_with_probe_signals(host, result)

    key = format_signal_key("VP", "VPG1")
    assert key in enriched.signals
    assert enriched.signals[key] == [1.2, 2.4]


def test_voltage_probe_skips_when_backend_channel_is_missing() -> None:
    circuit = Circuit(name="voltage-probe-missing")
    probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP2", x=120.0, y=120.0)
    circuit.add_component(probe)

    result = SimulationResult(
        time=[0.0, 1.0],
        signals={"V(N1)": [0.2, 0.4]},
    )
    host = _ResultHost(circuit)
    enriched = MainWindow._result_with_probe_signals(host, result)

    assert format_signal_key("VP", "VP2") not in enriched.signals


def test_current_and_power_probes_use_backend_channels() -> None:
    circuit = Circuit(name="current-power-probes")
    current_probe = Component(type=ComponentType.CURRENT_PROBE, name="IP1", x=120.0, y=120.0)
    power_probe = Component(type=ComponentType.POWER_PROBE, name="PP1", x=220.0, y=120.0)
    current_probe.parameters["scale"] = 2.0
    power_probe.parameters["scale"] = 0.5
    circuit.add_component(current_probe)
    circuit.add_component(power_probe)

    result = SimulationResult(
        time=[0.0, 1.0],
        signals={
            "IP1": [1.0, 1.5],
            "PP1": [10.0, 20.0],
        },
    )
    host = _ResultHost(circuit)
    enriched = MainWindow._result_with_probe_signals(host, result)

    assert enriched.signals[format_signal_key("IP", "IP1")] == [2.0, 3.0]
    assert enriched.signals[format_signal_key("PP", "PP1")] == [5.0, 10.0]
