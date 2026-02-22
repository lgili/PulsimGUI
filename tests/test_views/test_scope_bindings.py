"""Tests for scope channel binding resolution."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    Component,
    ComponentType,
    set_thermal_port_enabled,
)
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.utils.signal_utils import format_signal_key
from pulsimgui.views.scope.bindings import build_scope_channel_bindings


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


def test_thermal_scope_channel_resolves_connected_component_temperature() -> None:
    """Thermal scope should bind channel to connected component temperature trace."""
    circuit = Circuit(name="thermal-scope")

    resistor = Component(type=ComponentType.RESISTOR, name="R1", x=100.0, y=100.0)
    set_thermal_port_enabled(resistor, True)
    scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1", x=200.0, y=109.0)
    circuit.add_component(resistor)
    circuit.add_component(scope)
    _connect_pins(circuit, resistor, 2, scope, 0)

    bindings = build_scope_channel_bindings(scope, circuit)
    assert bindings
    first = bindings[0]
    assert first.signals
    assert first.signals[0].label == "R1"
    assert first.signals[0].signal_key == format_signal_key("T", "R1")


def test_thermal_scope_does_not_fallback_to_node_temperature_signal() -> None:
    """Unconnected thermal scope channel should not generate synthetic T(node) fallback."""
    circuit = Circuit(name="thermal-scope-unconnected")
    scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1", x=200.0, y=109.0)
    circuit.add_component(scope)

    bindings = build_scope_channel_bindings(scope, circuit)
    assert bindings
    assert bindings[0].signals == []


def test_thermal_scope_ignores_non_thermal_component_pins() -> None:
    """Thermal scope should ignore normal electrical pins when TH port is disabled."""
    circuit = Circuit(name="thermal-scope-electrical-pin")
    resistor = Component(type=ComponentType.RESISTOR, name="R1", x=100.0, y=100.0)
    scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1", x=200.0, y=109.0)
    circuit.add_component(resistor)
    circuit.add_component(scope)
    _connect_pins(circuit, resistor, 1, scope, 0)

    bindings = build_scope_channel_bindings(scope, circuit)
    assert bindings
    assert bindings[0].signals == []


def test_electrical_scope_keeps_voltage_fallback_for_unconnected_channel() -> None:
    """Electrical scope regression: channel without source still keeps V(node) fallback."""
    circuit = Circuit(name="electrical-scope-unconnected")
    scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1", x=200.0, y=109.0)
    circuit.add_component(scope)

    bindings = build_scope_channel_bindings(scope, circuit)
    assert bindings
    assert bindings[0].signals
    assert bindings[0].signals[0].signal_key is not None
    assert bindings[0].signals[0].signal_key.startswith("V(")
