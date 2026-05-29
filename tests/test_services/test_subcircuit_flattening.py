"""Tests for the SUBCIRCUIT flattening pre-pass in CircuitConverter.

The converter must expand each SUBCIRCUIT instance into its definition's
internal primitives, translating port nets to the parent scope and
giving every non-port internal net a unique synthesized name so two
instances of the same definition don't accidentally short.

A recording fake backend stands in for pulsim so the tests stay pure
unit-level (no real simulation).
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.subcircuit import (
    SubcircuitDefinition,
    SubcircuitInstance,
    SubcircuitPort,
)
from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.services.circuit_converter import (
    CircuitConversionError,
    CircuitConverter,
)
from pulsimgui.utils.net_utils import build_node_map


# ---------------------------------------------------------------------------
# Recording fake backend — captures resistor/cap/inductor stamps so the
# tests can assert post-flatten topology without needing real pulsim.
# ---------------------------------------------------------------------------
class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.resistor_calls: list[dict[str, Any]] = []
        self.capacitor_calls: list[dict[str, Any]] = []
        self.inductor_calls: list[dict[str, Any]] = []
        self.voltage_source_calls: list[dict[str, Any]] = []

    def add_node(self, name: str) -> int:
        if name in self.nodes:
            return self.nodes[name]
        idx = len(self.nodes)
        self.nodes[name] = idx
        return idx

    def add_resistor(self, name: str, n1: int, n2: int, resistance: float) -> None:
        self.resistor_calls.append(
            {"name": name, "n1": n1, "n2": n2, "resistance": resistance}
        )

    def add_capacitor(
        self, name: str, n1: int, n2: int, C: float, c0: float = 0.0
    ) -> None:
        self.capacitor_calls.append(
            {"name": name, "n1": n1, "n2": n2, "C": C, "c0": c0}
        )

    def add_inductor(
        self, name: str, n1: int, n2: int, L: float, i0: float = 0.0
    ) -> None:
        self.inductor_calls.append(
            {"name": name, "n1": n1, "n2": n2, "L": L, "i0": i0}
        )

    def add_voltage_source(
        self, name: str, npos: int, nneg: int, value: float
    ) -> None:
        self.voltage_source_calls.append(
            {"name": name, "npos": npos, "nneg": nneg, "value": value}
        )

    def _name_of(self, node_id: int) -> str:
        if node_id == -1:
            return "gnd"
        for nm, idx in self.nodes.items():
            if idx == node_id:
                return nm
        raise KeyError(node_id)


class _FakeBackend:
    Circuit = _FakeCircuit


# ---------------------------------------------------------------------------
# Helpers for building subcircuit definitions and instance payloads
# ---------------------------------------------------------------------------
def _build_two_terminal_r_definition(
    name: str = "RPair",
    resistance: float = 100.0,
    port_a_position: tuple[float, float] = (-40.0, 0.0),
    port_b_position: tuple[float, float] = (40.0, 0.0),
) -> SubcircuitDefinition:
    """A subcircuit with a single resistor between two ports A and B.

    The internal layout:
        port A pin0 ──[ R1 ]── port B pin1
    """
    inner = Circuit(name=name)
    r1 = Component(
        type=ComponentType.RESISTOR,
        name="R_inner",
        x=0.0,
        y=0.0,
        parameters={"resistance": resistance},
    )
    inner.add_component(r1)

    # Wire R1.pin0 → an internal net "A_net" (will be exposed via port A)
    # Wire R1.pin1 → an internal net "B_net" (will be exposed via port B)
    # We use the explicit WireConnection metadata so build_node_map can
    # union the wire endpoints with the right pins without needing
    # geometric coincidence.
    wire_a = Wire(
        segments=[
            WireSegment(
                x1=r1.get_pin_position(0)[0],
                y1=r1.get_pin_position(0)[1],
                x2=r1.get_pin_position(0)[0] - 40,
                y2=r1.get_pin_position(0)[1],
            )
        ],
        start_connection=WireConnection(component_id=r1.id, pin_index=0),
    )
    wire_b = Wire(
        segments=[
            WireSegment(
                x1=r1.get_pin_position(1)[0],
                y1=r1.get_pin_position(1)[1],
                x2=r1.get_pin_position(1)[0] + 40,
                y2=r1.get_pin_position(1)[1],
            )
        ],
        start_connection=WireConnection(component_id=r1.id, pin_index=1),
    )
    inner.add_wire(wire_a)
    inner.add_wire(wire_b)

    # Resolve internal net names via the same builder the flattener uses.
    node_map = build_node_map(inner)
    net_a = node_map[(str(r1.id), 0)]
    net_b = node_map[(str(r1.id), 1)]

    defn = SubcircuitDefinition(
        name=name,
        circuit=inner,
        ports=[
            SubcircuitPort(
                name="A",
                internal_node=net_a,
                pin_index=0,
                x=port_a_position[0],
                y=port_a_position[1],
            ),
            SubcircuitPort(
                name="B",
                internal_node=net_b,
                pin_index=1,
                x=port_b_position[0],
                y=port_b_position[1],
            ),
        ],
    )
    return defn


def _build_rl_series_definition(
    name: str = "RLSeries",
    r_value: float = 50.0,
    l_value: float = 10e-3,
) -> SubcircuitDefinition:
    """Series R+L subcircuit with the mid-point left as an INTERNAL net.

    Internal layout:
        port A pin0 ──[ R ]── mid_net ──[ L ]── port B pin1

    Only A and B are exposed as ports. ``mid_net`` is non-port and must
    receive a unique synthesized name during flattening.
    """
    inner = Circuit(name=name)
    r = Component(
        type=ComponentType.RESISTOR,
        name="R_inner",
        x=0.0,
        y=0.0,
        parameters={"resistance": r_value},
    )
    l = Component(
        type=ComponentType.INDUCTOR,
        name="L_inner",
        x=100.0,
        y=0.0,
        parameters={"inductance": l_value},
    )
    inner.add_component(r)
    inner.add_component(l)

    # Mid-point wire: R.pin1 ↔ L.pin0
    mid_wire = Wire(
        segments=[
            WireSegment(
                x1=r.get_pin_position(1)[0],
                y1=r.get_pin_position(1)[1],
                x2=l.get_pin_position(0)[0],
                y2=l.get_pin_position(0)[1],
            )
        ],
        start_connection=WireConnection(component_id=r.id, pin_index=1),
        end_connection=WireConnection(component_id=l.id, pin_index=0),
    )
    inner.add_wire(mid_wire)

    # Stub wires to anchor port nets so the boundary nets are explicit
    a_wire = Wire(
        segments=[
            WireSegment(
                x1=r.get_pin_position(0)[0],
                y1=r.get_pin_position(0)[1],
                x2=r.get_pin_position(0)[0] - 40,
                y2=r.get_pin_position(0)[1],
            )
        ],
        start_connection=WireConnection(component_id=r.id, pin_index=0),
    )
    b_wire = Wire(
        segments=[
            WireSegment(
                x1=l.get_pin_position(1)[0],
                y1=l.get_pin_position(1)[1],
                x2=l.get_pin_position(1)[0] + 40,
                y2=l.get_pin_position(1)[1],
            )
        ],
        start_connection=WireConnection(component_id=l.id, pin_index=1),
    )
    inner.add_wire(a_wire)
    inner.add_wire(b_wire)

    node_map = build_node_map(inner)
    net_a = node_map[(str(r.id), 0)]
    net_b = node_map[(str(l.id), 1)]

    defn = SubcircuitDefinition(
        name=name,
        circuit=inner,
        ports=[
            SubcircuitPort(name="A", internal_node=net_a, pin_index=0),
            SubcircuitPort(name="B", internal_node=net_b, pin_index=1),
        ],
    )
    return defn


def _build_three_port_definition(
    name: str = "ThreePort",
) -> SubcircuitDefinition:
    """A subcircuit with 3 ports — two resistors sharing a common node.

    Internal layout (star configuration):
        port A pin0 ──[ R1 ]── common ──[ R2 ]── port B pin1
                                     │
                                  port C pin2 (direct tap on ``common``)

    Used to verify multi-port flattening. The ``common`` net is exposed
    via port C, so after flattening all three resistor terminals
    connected to ``common`` route to the same external net.
    """
    inner = Circuit(name=name)
    r1 = Component(
        type=ComponentType.RESISTOR,
        name="R1_inner",
        x=0.0,
        y=0.0,
        parameters={"resistance": 10.0},
    )
    r2 = Component(
        type=ComponentType.RESISTOR,
        name="R2_inner",
        x=100.0,
        y=0.0,
        parameters={"resistance": 20.0},
    )
    inner.add_component(r1)
    inner.add_component(r2)

    # Common-net wire connecting R1.pin1 ↔ R2.pin0
    common_wire = Wire(
        segments=[
            WireSegment(
                x1=r1.get_pin_position(1)[0],
                y1=r1.get_pin_position(1)[1],
                x2=r2.get_pin_position(0)[0],
                y2=r2.get_pin_position(0)[1],
            )
        ],
        start_connection=WireConnection(component_id=r1.id, pin_index=1),
        end_connection=WireConnection(component_id=r2.id, pin_index=0),
    )
    inner.add_wire(common_wire)

    node_map = build_node_map(inner)
    net_a = node_map[(str(r1.id), 0)]
    net_common = node_map[(str(r1.id), 1)]
    net_b = node_map[(str(r2.id), 1)]
    assert net_common == node_map[(str(r2.id), 0)]

    defn = SubcircuitDefinition(
        name=name,
        circuit=inner,
        ports=[
            SubcircuitPort(name="A", internal_node=net_a, pin_index=0),
            SubcircuitPort(name="B", internal_node=net_b, pin_index=1),
            SubcircuitPort(name="C", internal_node=net_common, pin_index=2),
        ],
    )
    return defn


def _instance_payload(
    instance_id: str,
    instance_name: str,
    definition_id: str,
    pin_nodes: list[str],
) -> dict[str, Any]:
    """Build a serialized SUBCIRCUIT instance payload for the converter."""
    return {
        "id": instance_id,
        "type": "SUBCIRCUIT",
        "name": instance_name,
        "x": 0.0,
        "y": 0.0,
        "rotation": 0,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": {},
        "pins": [],
        "pin_nodes": list(pin_nodes),
        "subcircuit_id": definition_id,
    }


# ---------------------------------------------------------------------------
# Single-level flattening
# ---------------------------------------------------------------------------
def test_single_instance_expands_to_internal_resistor() -> None:
    """One SUBCIRCUIT instance with a single inner R must produce
    exactly one resistor stamp on the external nets."""
    defn = _build_two_terminal_r_definition(resistance=250.0)
    defn_id = str(defn.id)

    instance_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                instance_id,
                "U1",
                defn_id,
                pin_nodes=["EXT_A", "EXT_B"],
            )
        ],
        "node_map": {instance_id: ["EXT_A", "EXT_B"]},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake_circuit = converter.build(circuit_data)

    # No SUBCIRCUIT entries should remain in the components list
    remaining_subckts = [
        c for c in circuit_data["components"] if c.get("type") == "SUBCIRCUIT"
    ]
    assert remaining_subckts == []

    # The instance's node_map row should be gone
    assert instance_id not in circuit_data["node_map"]

    # Exactly one resistor stamped on the right external nets
    assert len(fake_circuit.resistor_calls) == 1
    call = fake_circuit.resistor_calls[0]
    assert call["resistance"] == pytest.approx(250.0)
    # Both pin nets must resolve to the external nodes the instance was
    # wired to (converter normalizes with an "N" prefix).
    assert {call["n1"], call["n2"]} == {
        fake_circuit.nodes["NEXT_A"],
        fake_circuit.nodes["NEXT_B"],
    }
    # The internal resistor name should be namespaced by the instance.
    assert call["name"].startswith("U1__")


# ---------------------------------------------------------------------------
# Two instances of the same definition: distinct internal nets, no shorts
# ---------------------------------------------------------------------------
def test_two_instances_same_definition_keep_internal_nets_distinct() -> None:
    """Two SUBCIRCUITs sharing a definition must produce two separate
    resistors, each on its own pair of external nets."""
    defn = _build_two_terminal_r_definition(resistance=470.0)
    defn_id = str(defn.id)

    inst_a = str(uuid4())
    inst_b = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(inst_a, "UA", defn_id, ["A1", "A2"]),
            _instance_payload(inst_b, "UB", defn_id, ["B1", "B2"]),
        ],
        "node_map": {
            inst_a: ["A1", "A2"],
            inst_b: ["B1", "B2"],
        },
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake_circuit = converter.build(circuit_data)

    assert len(fake_circuit.resistor_calls) == 2
    pairs = {
        frozenset({call["n1"], call["n2"]}) for call in fake_circuit.resistor_calls
    }
    expected_a = frozenset(
        {fake_circuit.nodes["NA1"], fake_circuit.nodes["NA2"]}
    )
    expected_b = frozenset(
        {fake_circuit.nodes["NB1"], fake_circuit.nodes["NB2"]}
    )
    assert pairs == {expected_a, expected_b}

    # Component names carry the instance prefix so the netlist is
    # debuggable. Both instances must produce distinct names.
    names = {call["name"] for call in fake_circuit.resistor_calls}
    assert len(names) == 2
    assert any(name.startswith("UA__") for name in names)
    assert any(name.startswith("UB__") for name in names)


# ---------------------------------------------------------------------------
# Multi-port subcircuit
# ---------------------------------------------------------------------------
def test_multi_port_subcircuit_routes_each_port_to_correct_external_net() -> None:
    """A subcircuit with 3 ports must route each internal-port net to
    the corresponding external net on the instance."""
    defn = _build_three_port_definition()
    defn_id = str(defn.id)

    inst_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                inst_id,
                "U3",
                defn_id,
                pin_nodes=["NET_A", "NET_B", "NET_C"],
            )
        ],
        "node_map": {inst_id: ["NET_A", "NET_B", "NET_C"]},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake_circuit = converter.build(circuit_data)

    assert len(fake_circuit.resistor_calls) == 2

    a = fake_circuit.nodes["NNET_A"]
    b = fake_circuit.nodes["NNET_B"]
    c = fake_circuit.nodes["NNET_C"]

    # Both resistors must share node C (the common-net port). R1 connects
    # A↔C, R2 connects C↔B.
    pairs = {
        frozenset({call["n1"], call["n2"]}) for call in fake_circuit.resistor_calls
    }
    assert pairs == {frozenset({a, c}), frozenset({c, b})}


# ---------------------------------------------------------------------------
# Internal non-port net: must get a unique synthesized name per instance
# ---------------------------------------------------------------------------
def test_internal_non_port_net_is_unique_per_instance() -> None:
    """Two RL-series instances must NOT share their internal mid-point
    net — each gets a synthesized name keyed off the instance UUID."""
    defn = _build_rl_series_definition()
    defn_id = str(defn.id)

    inst_a = str(uuid4())
    inst_b = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(inst_a, "RLa", defn_id, ["A_IN", "A_OUT"]),
            _instance_payload(inst_b, "RLb", defn_id, ["B_IN", "B_OUT"]),
        ],
        "node_map": {
            inst_a: ["A_IN", "A_OUT"],
            inst_b: ["B_IN", "B_OUT"],
        },
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake_circuit = converter.build(circuit_data)

    # 2 resistors + 2 inductors total
    assert len(fake_circuit.resistor_calls) == 2
    assert len(fake_circuit.inductor_calls) == 2

    # For each instance, the resistor and inductor share exactly one
    # node (the mid-point). The mid-point of UA must be DIFFERENT from
    # the mid-point of UB.
    def shared_mid(r_call: dict, l_call: dict) -> int:
        r_nodes = {r_call["n1"], r_call["n2"]}
        l_nodes = {l_call["n1"], l_call["n2"]}
        shared = r_nodes & l_nodes
        assert len(shared) == 1, f"R/L should share exactly 1 node, got {shared}"
        return next(iter(shared))

    # Pair up R and L from the same instance via the namespaced name prefix.
    by_instance: dict[str, dict[str, dict]] = {}
    for call in fake_circuit.resistor_calls:
        prefix = call["name"].split("__", 1)[0]
        by_instance.setdefault(prefix, {})["R"] = call
    for call in fake_circuit.inductor_calls:
        prefix = call["name"].split("__", 1)[0]
        by_instance.setdefault(prefix, {})["L"] = call

    assert set(by_instance.keys()) == {"RLa", "RLb"}
    mid_a = shared_mid(by_instance["RLa"]["R"], by_instance["RLa"]["L"])
    mid_b = shared_mid(by_instance["RLb"]["R"], by_instance["RLb"]["L"])
    assert mid_a != mid_b, "Internal mid-points must NOT collide between instances"

    # Neither mid-point may resolve to one of the external A/B/C nets.
    external_node_ids = {
        fake_circuit.nodes["NA_IN"],
        fake_circuit.nodes["NA_OUT"],
        fake_circuit.nodes["NB_IN"],
        fake_circuit.nodes["NB_OUT"],
    }
    assert mid_a not in external_node_ids
    assert mid_b not in external_node_ids


# ---------------------------------------------------------------------------
# Nested subcircuits — definition A contains an instance of definition B
# ---------------------------------------------------------------------------
def test_nested_subcircuits_expand_recursively() -> None:
    """When subcircuit A contains an instance of subcircuit B, the
    flattening pass must recurse so the parent circuit ends up with
    B's primitives correctly translated all the way through."""
    # Build the inner B definition — a single resistor between A and B ports.
    inner_b = _build_two_terminal_r_definition(name="InnerR", resistance=33.0)
    inner_b_id = str(inner_b.id)

    # Build the outer A definition — its internal circuit holds ONE
    # SUBCIRCUIT instance of B, plus two stub wires marking the two
    # external ports.
    outer_a_circuit = Circuit(name="OuterA")
    nested_instance = SubcircuitInstance(
        type=ComponentType.SUBCIRCUIT,
        name="B_inside_A",
        x=0.0,
        y=0.0,
        subcircuit_id=inner_b.id,
        pins=inner_b.get_pins(),
    )
    outer_a_circuit.add_component(nested_instance)

    # Stub wires so the two pin endpoints become distinct nets and we
    # can record them as A's external ports.
    pin0_pos = nested_instance.get_pin_position(0)
    pin1_pos = nested_instance.get_pin_position(1)
    stub_a = Wire(
        segments=[
            WireSegment(
                x1=pin0_pos[0],
                y1=pin0_pos[1],
                x2=pin0_pos[0] - 40,
                y2=pin0_pos[1],
            )
        ],
        start_connection=WireConnection(
            component_id=nested_instance.id, pin_index=0
        ),
    )
    stub_b = Wire(
        segments=[
            WireSegment(
                x1=pin1_pos[0],
                y1=pin1_pos[1],
                x2=pin1_pos[0] + 40,
                y2=pin1_pos[1],
            )
        ],
        start_connection=WireConnection(
            component_id=nested_instance.id, pin_index=1
        ),
    )
    outer_a_circuit.add_wire(stub_a)
    outer_a_circuit.add_wire(stub_b)

    # Resolve the OUTER definition's port nets via the same builder.
    outer_node_map = build_node_map(outer_a_circuit)
    outer_net_a = outer_node_map[(str(nested_instance.id), 0)]
    outer_net_b = outer_node_map[(str(nested_instance.id), 1)]

    outer_def = SubcircuitDefinition(
        name="OuterA",
        circuit=outer_a_circuit,
        ports=[
            SubcircuitPort(name="A", internal_node=outer_net_a, pin_index=0),
            SubcircuitPort(name="B", internal_node=outer_net_b, pin_index=1),
        ],
    )
    outer_def_id = str(outer_def.id)

    # The parent circuit holds one instance of OuterA.
    parent_instance_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                parent_instance_id,
                "TOP",
                outer_def_id,
                pin_nodes=["TOP_IN", "TOP_OUT"],
            )
        ],
        "node_map": {parent_instance_id: ["TOP_IN", "TOP_OUT"]},
        "node_aliases": {},
        "subcircuits": {
            outer_def_id: outer_def.to_dict(),
            inner_b_id: inner_b.to_dict(),
        },
    }

    converter = CircuitConverter(_FakeBackend)
    fake_circuit = converter.build(circuit_data)

    # The flattened netlist must have exactly one inner resistor stamped
    # between TOP_IN and TOP_OUT — proving both levels of expansion ran.
    assert len(fake_circuit.resistor_calls) == 1
    call = fake_circuit.resistor_calls[0]
    assert call["resistance"] == pytest.approx(33.0)
    assert {call["n1"], call["n2"]} == {
        fake_circuit.nodes["NTOP_IN"],
        fake_circuit.nodes["NTOP_OUT"],
    }
    # No SUBCIRCUIT entries remain
    remaining_subckts = [
        c for c in circuit_data["components"] if c.get("type") == "SUBCIRCUIT"
    ]
    assert remaining_subckts == []


# ---------------------------------------------------------------------------
# Cycle detection
# ---------------------------------------------------------------------------
def test_self_referencing_subcircuit_raises_circuit_conversion_error() -> None:
    """Definition A whose internal circuit contains an instance of A
    itself must trigger a clear ``CircuitConversionError``."""
    # Build A's internal circuit holding a SUBCIRCUIT instance of A.
    # We construct the instance with a placeholder ``subcircuit_id``,
    # then patch it to the real definition ID once the definition is
    # built (chicken-and-egg: the instance needs the ID, but the ID is
    # generated only when the definition is instantiated).
    inner_circuit = Circuit(name="CycleA")
    self_ref = SubcircuitInstance(
        type=ComponentType.SUBCIRCUIT,
        name="recursion",
        x=0.0,
        y=0.0,
        subcircuit_id=None,  # patched below
        pins=[],
    )
    inner_circuit.add_component(self_ref)

    defn = SubcircuitDefinition(
        name="CycleA",
        circuit=inner_circuit,
        ports=[],
    )
    # Patch the nested instance to reference its own definition.
    self_ref.subcircuit_id = defn.id

    defn_id = str(defn.id)

    parent_instance_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                parent_instance_id, "U", defn_id, pin_nodes=[]
            )
        ],
        "node_map": {parent_instance_id: []},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    with pytest.raises(CircuitConversionError, match="Recursive subcircuit"):
        converter.build(circuit_data)


def test_indirect_cycle_a_to_b_to_a_raises() -> None:
    """Definition A contains B and B contains A — the converter must
    detect this and raise."""
    a_circuit = Circuit(name="A_cycle")
    b_circuit = Circuit(name="B_cycle")

    a_def = SubcircuitDefinition(name="A_cycle", circuit=a_circuit, ports=[])
    b_def = SubcircuitDefinition(name="B_cycle", circuit=b_circuit, ports=[])

    # A's internal circuit holds an instance of B
    a_to_b = SubcircuitInstance(
        type=ComponentType.SUBCIRCUIT,
        name="b_in_a",
        x=0.0,
        y=0.0,
        subcircuit_id=b_def.id,
        pins=[],
    )
    a_circuit.add_component(a_to_b)

    # B's internal circuit holds an instance of A
    b_to_a = SubcircuitInstance(
        type=ComponentType.SUBCIRCUIT,
        name="a_in_b",
        x=0.0,
        y=0.0,
        subcircuit_id=a_def.id,
        pins=[],
    )
    b_circuit.add_component(b_to_a)

    a_id = str(a_def.id)
    b_id = str(b_def.id)

    parent_instance_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                parent_instance_id, "TOP", a_id, pin_nodes=[]
            )
        ],
        "node_map": {parent_instance_id: []},
        "node_aliases": {},
        "subcircuits": {
            a_id: a_def.to_dict(),
            b_id: b_def.to_dict(),
        },
    }

    converter = CircuitConverter(_FakeBackend)
    with pytest.raises(CircuitConversionError, match="Recursive subcircuit"):
        converter.build(circuit_data)


# ---------------------------------------------------------------------------
# Missing definition surfaces a clear error
# ---------------------------------------------------------------------------
def test_missing_subcircuit_definition_raises() -> None:
    """An instance pointing at a non-existent definition must trigger a
    ``CircuitConversionError`` so the GUI can show a precise message."""
    parent_instance_id = str(uuid4())
    bogus_def_id = str(uuid4())
    circuit_data = {
        "components": [
            _instance_payload(
                parent_instance_id, "U_missing", bogus_def_id, pin_nodes=["X", "Y"]
            )
        ],
        "node_map": {parent_instance_id: ["X", "Y"]},
        "node_aliases": {},
        "subcircuits": {},  # empty — definition is missing
    }

    converter = CircuitConverter(_FakeBackend)
    with pytest.raises(CircuitConversionError, match="unknown"):
        converter.build(circuit_data)
