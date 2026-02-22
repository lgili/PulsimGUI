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


class _CircuitWithVirtual(_CircuitNoAddNode):
    def __init__(self) -> None:
        super().__init__()
        self.virtual_components: list[tuple[str, str, list[int], dict[str, float], dict[str, str]]] = []
        self.switches: list[tuple[str, int, int, bool, float, float]] = []
        self.snubbers: list[tuple[str, int, int, float, float, float]] = []

    def add_virtual_component(
        self,
        comp_type: str,
        name: str,
        nodes: list[int],
        numeric_params: dict[str, float],
        metadata: dict[str, str],
    ) -> None:
        self.virtual_components.append((comp_type, name, list(nodes), dict(numeric_params), dict(metadata)))

    def add_switch(
        self,
        name: str,
        n1: int,
        n2: int,
        closed: bool,
        g_on: float,
        g_off: float,
    ) -> None:
        self.switches.append((name, n1, n2, closed, g_on, g_off))

    def add_snubber_rc(
        self,
        name: str,
        n1: int,
        n2: int,
        resistance: float,
        capacitance: float,
        initial_voltage: float,
    ) -> None:
        self.snubbers.append((name, n1, n2, resistance, capacitance, initial_voltage))


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


def test_converter_ignores_scope_components_during_build() -> None:
    """Scope/probe blocks are GUI instrumentation and must not reach backend."""

    fake_module = SimpleNamespace(Circuit=_CircuitNoAddNode)
    converter = CircuitConverter(fake_module)

    circuit_data = {
        "components": [
            {
                "id": "scope1",
                "type": "ELECTRICAL_SCOPE",
                "name": "Scope1",
                "parameters": {"channel_count": 2},
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["1", "0"],
            },
        ],
        "node_map": {"r1": ["1", "0"]},
        "node_aliases": {"1": "OUT", "0": "0"},
    }

    converted = converter.build(circuit_data)

    assert converted.nodes == {"OUT": 1}
    assert converted.devices == [("R1", 1, 0, 1000.0)]


def test_converter_uses_virtual_component_for_unmapped_types() -> None:
    """Unmapped components should use backend virtual-component path when available."""
    fake_module = SimpleNamespace(Circuit=_CircuitWithVirtual)
    converter = CircuitConverter(fake_module)

    circuit_data = {
        "components": [
            {
                "id": "q1",
                "type": "BJT_NPN",
                "name": "Q1",
                "parameters": {
                    "beta": 120.0,
                    "enabled": True,
                    "model": "npn",
                    "notes": ["demo", "virtual"],
                },
                "pin_nodes": ["1", "2", "0"],
            }
        ],
        "node_map": {"q1": ["1", "2", "0"]},
        "node_aliases": {"1": "B", "2": "C", "0": "0"},
    }

    converted = converter.build(circuit_data)

    assert len(converted.virtual_components) == 1
    comp_type, name, nodes, numeric_params, metadata = converted.virtual_components[0]
    assert comp_type == "BJT_NPN"
    assert name == "Q1"
    assert len(nodes) == 3
    assert numeric_params["beta"] == 120.0
    assert numeric_params["enabled"] == 1.0
    assert metadata["component_type"] == "BJT_NPN"
    assert metadata["model"] == "npn"
    assert metadata["notes"] == "[\"demo\", \"virtual\"]"


def test_converter_prefers_native_switch_and_snubber_methods() -> None:
    """When backend has native methods, converter should not downgrade to virtual."""
    fake_module = SimpleNamespace(Circuit=_CircuitWithVirtual)
    converter = CircuitConverter(fake_module)

    circuit_data = {
        "components": [
            {
                "id": "s1",
                "type": "SWITCH",
                "name": "S1",
                "parameters": {"closed": True, "g_on": 2e6, "g_off": 1e-10},
                "pin_nodes": ["1", "2"],
            },
            {
                "id": "sn1",
                "type": "SNUBBER_RC",
                "name": "SN1",
                "parameters": {"resistance": 220.0, "capacitance": 4.7e-8, "initial_voltage": 0.2},
                "pin_nodes": ["2", "0"],
            },
        ],
        "node_map": {"s1": ["1", "2"], "sn1": ["2", "0"]},
        "node_aliases": {"1": "IN", "2": "SW", "0": "0"},
    }

    converted = converter.build(circuit_data)

    assert len(converted.switches) == 1
    assert converted.switches[0][0] == "S1"
    assert len(converted.snubbers) == 1
    assert converted.snubbers[0][0] == "SN1"
    assert converted.virtual_components == []


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
