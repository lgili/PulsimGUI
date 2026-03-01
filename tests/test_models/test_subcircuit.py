"""Tests for subcircuit helpers."""

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.models.subcircuit import (
    BoundaryPortCandidate,
    create_subcircuit_from_selection,
    detect_boundary_ports,
)


def _build_simple_circuit() -> tuple[Circuit, Component, Component]:
    circuit = Circuit(name="main")

    r1 = Component(type=ComponentType.RESISTOR, name="R1", x=0.0, y=0.0)
    r2 = Component(type=ComponentType.RESISTOR, name="R2", x=100.0, y=0.0)

    circuit.add_component(r1)
    circuit.add_component(r2)

    wire = Wire()
    # Connect R1 pin 1 to R2 pin 0 using the current pin layout coordinates.
    r1_pin_1 = r1.get_pin_position(1)
    r2_pin_0 = r2.get_pin_position(0)
    wire.segments.append(
        WireSegment(
            x1=r1_pin_1[0],
            y1=r1_pin_1[1],
            x2=r2_pin_0[0],
            y2=r2_pin_0[1],
        )
    )
    circuit.add_wire(wire)

    return circuit, r1, r2


def test_detect_boundary_ports_identifies_external_nodes():
    circuit, r1, _ = _build_simple_circuit()

    ports = detect_boundary_ports(circuit, [r1.id])

    assert len(ports) == 1
    candidate = ports[0]
    assert candidate.internal_refs[0][0] == r1.id
    assert candidate.anchor_point == r1.get_pin_position(1)
    assert candidate.name.startswith("R2.")


def test_create_subcircuit_from_selection_uses_candidates():
    circuit, r1, _ = _build_simple_circuit()
    candidates = detect_boundary_ports(circuit, [r1.id])

    definition, ports, center = create_subcircuit_from_selection(
        circuit,
        selected_component_ids=[r1.id],
        selected_wire_ids=[],
        name="Half",
        description="Half bridge leg",
        symbol_size=(80, 60),
        boundary_ports=candidates,
    )

    assert definition.name == "Half"
    assert definition.description == "Half bridge leg"
    assert len(definition.circuit.components) == 1
    assert len(ports) == 1

    # Pin should remain aligned with original anchor point
    pin = ports[0]
    assert round(pin.x, 3) == round(r1.get_pin_position(1)[0], 3)
    assert round(pin.y, 3) == 0.0

    # Center should match original component position
    assert round(center[0], 3) == 0.0
    assert round(center[1], 3) == 0.0
