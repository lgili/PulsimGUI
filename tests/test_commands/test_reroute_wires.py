"""Tests for RerouteAllWiresCommand (the 'Tidy Wires' action).

Re-routes every wire as clean orthogonal paths via the WireRouter
without moving components, and is fully undoable.
"""
from __future__ import annotations

from pulsimgui.commands.wire_commands import RerouteAllWiresCommand
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment


def _is_orthogonal(wire: Wire) -> bool:
    return all(
        abs(s.x2 - s.x1) < 1e-6 or abs(s.y2 - s.y1) < 1e-6
        for s in wire.segments
    )


def _make_circuit_with_diagonal_wire() -> tuple[Circuit, Wire]:
    circuit = Circuit()
    circuit.add_component(Component(type=ComponentType.RESISTOR, x=0.0, y=0.0))
    circuit.add_component(Component(type=ComponentType.RESISTOR, x=200.0, y=120.0))
    wire = Wire(segments=[WireSegment(20.0, 0.0, 180.0, 120.0)])  # diagonal
    circuit.add_wire(wire)
    return circuit, wire


def test_reroute_makes_wire_orthogonal() -> None:
    circuit, wire = _make_circuit_with_diagonal_wire()
    assert not _is_orthogonal(wire)  # starts diagonal

    RerouteAllWiresCommand(circuit).execute()

    routed = circuit.wires[wire.id]
    assert _is_orthogonal(routed)
    assert len(routed.segments) >= 1
    # Endpoints (on-grid) are preserved through routing.
    assert routed.start_point == (20.0, 0.0)
    assert routed.end_point == (180.0, 120.0)


def test_reroute_is_undoable() -> None:
    circuit, wire = _make_circuit_with_diagonal_wire()
    original = [(s.x1, s.y1, s.x2, s.y2) for s in wire.segments]

    cmd = RerouteAllWiresCommand(circuit)
    cmd.execute()
    assert _is_orthogonal(circuit.wires[wire.id])

    cmd.undo()
    restored = [(s.x1, s.y1, s.x2, s.y2) for s in circuit.wires[wire.id].segments]
    assert restored == original


def test_reroute_empty_circuit_is_safe() -> None:
    circuit = Circuit()
    RerouteAllWiresCommand(circuit).execute()  # no wires → no-op, no error


def test_reroute_already_orthogonal_stays_orthogonal() -> None:
    circuit = Circuit()
    circuit.add_component(Component(type=ComponentType.RESISTOR, x=0.0, y=0.0))
    circuit.add_component(Component(type=ComponentType.RESISTOR, x=200.0, y=0.0))
    wire = Wire(segments=[WireSegment(20.0, 0.0, 180.0, 0.0)])  # straight H
    circuit.add_wire(wire)

    RerouteAllWiresCommand(circuit).execute()
    assert _is_orthogonal(circuit.wires[wire.id])
    assert circuit.wires[wire.id].start_point == (20.0, 0.0)
    assert circuit.wires[wire.id].end_point == (180.0, 0.0)


def test_description() -> None:
    assert RerouteAllWiresCommand(Circuit()).description == "Auto-route wires"
