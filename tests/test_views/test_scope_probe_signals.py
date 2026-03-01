"""Regression tests for probe-derived scope signals."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.utils.net_utils import build_node_map
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.main_window import MainWindow


def _connect_pins(
    circuit: Circuit,
    left: Component,
    left_pin: int,
    right: Component,
    right_pin: int,
) -> None:
    x1, y1 = left.get_pin_position(left_pin)
    x2, y2 = right.get_pin_position(right_pin)
    circuit.add_wire(Wire(segments=[WireSegment(x1, y1, x2, y2)]))


class _ResultHost:
    """Minimal host object required by MainWindow result helpers."""

    def __init__(self, circuit: Circuit) -> None:
        self._circuit = circuit

    def _current_circuit(self) -> Circuit:
        return self._circuit


def _bind_result_helpers(host: _ResultHost) -> None:
    host._probe_node_series = MainWindow._probe_node_series.__get__(host, _ResultHost)


def test_voltage_probe_keeps_signal_when_plus_pin_is_ground_reference() -> None:
    """VP signal should still be generated when the probe plus pin sits on GND."""
    circuit = Circuit(name="voltage-probe-gnd-plus")
    probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP1", x=120.0, y=120.0)
    ground = Component(type=ComponentType.GROUND, name="GND1", x=60.0, y=130.0)
    resistor = Component(type=ComponentType.RESISTOR, name="R1", x=210.0, y=130.0)
    circuit.add_component(probe)
    circuit.add_component(ground)
    circuit.add_component(resistor)

    _connect_pins(circuit, probe, 0, ground, 0)   # + on ground
    _connect_pins(circuit, probe, 1, resistor, 0)  # - on non-ground node

    node_map = build_node_map(circuit)
    minus_node = node_map[(str(probe.id), 1)]

    # Simulate backend output that does not expose V(0), only non-ground nodes.
    result = SimulationResult(
        time=[0.0, 1.0],
        signals={f"V(N{minus_node})": [3.0, 5.0]},
    )
    host = _ResultHost(circuit)
    _bind_result_helpers(host)

    enriched = MainWindow._result_with_probe_signals(host, result)

    key = format_signal_key("VP", "VP1")
    assert key in enriched.signals
    assert enriched.signals[key] == [-3.0, -5.0]


def test_voltage_probe_resolves_raw_backend_voltage_key_without_n_prefix() -> None:
    """VP generation should accept raw V(node_id) keys returned by compatibility backends."""
    circuit = Circuit(name="voltage-probe-raw-key")
    probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP2", x=120.0, y=120.0)
    resistor = Component(type=ComponentType.RESISTOR, name="R1", x=210.0, y=130.0)
    circuit.add_component(probe)
    circuit.add_component(resistor)

    _connect_pins(circuit, probe, 0, resistor, 0)  # + on non-ground node

    node_map = build_node_map(circuit)
    plus_node = node_map[(str(probe.id), 0)]

    result = SimulationResult(
        time=[0.0, 1.0],
        signals={f"V({plus_node})": [2.0, 4.0]},
    )
    host = _ResultHost(circuit)
    _bind_result_helpers(host)

    enriched = MainWindow._result_with_probe_signals(host, result)

    key = format_signal_key("VP", "VP2")
    assert key in enriched.signals
    assert enriched.signals[key] == [2.0, 4.0]
