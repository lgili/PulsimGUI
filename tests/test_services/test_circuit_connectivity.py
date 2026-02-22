"""Connectivity and converter regression tests."""

from __future__ import annotations

from types import SimpleNamespace

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment
from pulsimgui.services.circuit_converter import CircuitConverter
from pulsimgui.utils.net_utils import build_node_map


class _CircuitNoAddNode:
    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.devices: list[tuple[str, int, int, float]] = []

    @staticmethod
    def ground() -> int:
        return 0

    def get_node(self, name: str) -> int:
        idx = self.nodes.get(name)
        if idx is None:
            idx = len(self.nodes) + 1
            self.nodes[name] = idx
        return idx

    def add_resistor(self, name: str, n1: int, n2: int, value: float) -> None:
        self.devices.append((name, n1, n2, value))


def test_converter_falls_back_to_get_node_when_add_node_is_missing() -> None:
    """Circuit conversion should work when backend Circuit has no add_node method."""

    fake_module = SimpleNamespace(Circuit=_CircuitNoAddNode)
    converter = CircuitConverter(fake_module)

    circuit_data = {
        "components": [
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 2200.0},
                "pin_nodes": ["1", "0"],
            }
        ],
        "node_map": {"r1": ["1", "0"]},
        "node_aliases": {"1": "OUT", "0": "0"},
    }

    converted = converter.build(circuit_data)

    assert converted.nodes == {"OUT": 1}
    assert converted.devices == [("R1", 1, 0, 2200.0)]


def test_build_node_map_merges_split_wires_on_shared_endpoint() -> None:
    """Split wires touching at a point should be treated as one electrical net."""

    circuit = Circuit(name="wire-merge")

    r1 = Component(
        type=ComponentType.RESISTOR,
        name="R1",
        x=100.0,
        y=100.0,
        parameters={"resistance": 1000.0},
    )
    r2 = Component(
        type=ComponentType.RESISTOR,
        name="R2",
        x=220.0,
        y=100.0,
        parameters={"resistance": 1000.0},
    )
    circuit.add_component(r1)
    circuit.add_component(r2)

    # R1 pin 1 is at (130, 100), R2 pin 0 is at (190, 100).
    # Two wire objects meet at (160, 100), so they should form one net.
    wire_a = Wire(segments=[WireSegment(130.0, 100.0, 160.0, 100.0)])
    wire_b = Wire(segments=[WireSegment(160.0, 100.0, 190.0, 100.0)])
    circuit.add_wire(wire_a)
    circuit.add_wire(wire_b)

    node_map = build_node_map(circuit)

    r1_out = node_map[(str(r1.id), 1)]
    r2_in = node_map[(str(r2.id), 0)]
    assert r1_out == r2_in
