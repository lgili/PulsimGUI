"""Integration tests: subcircuit definitions built with
SUBCIRCUIT_PORT markers flatten correctly through the converter.

The contract being pinned:
  * Markers themselves never appear in the flattened netlist — they
    are bridging metadata, not devices.
  * Each marker's connected net (inside the body) gets bridged to the
    external net wired to the matching pin on the outer
    SubcircuitInstance.
  * Backward compat: definitions built the old way (no markers,
    explicit ``SubcircuitPort.internal_node`` strings) still work.

The fake backend matches the one used by the rest of the flattening
suite — see ``test_subcircuit_flattening.py``.
"""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType, Pin
from pulsimgui.models.subcircuit import (
    SubcircuitDefinition,
    sync_definition_ports_from_markers,
)
from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.services.circuit_converter import CircuitConverter


# ---------------------------------------------------------------------------
# Fake backend — shared shape with the existing flattening suite.
# ---------------------------------------------------------------------------
class _FakeCircuit:
    @staticmethod
    def ground() -> int:
        return -1

    def __init__(self) -> None:
        self.nodes: dict[str, int] = {}
        self.resistor_calls: list[dict[str, Any]] = []

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

    # Stubs the converter looks for but the marker test doesn't exercise
    def add_capacitor(self, *args, **kwargs) -> None: ...
    def add_inductor(self, *args, **kwargs) -> None: ...
    def add_voltage_source(self, *args, **kwargs) -> None: ...

    def get_node_name(self, node_id: int) -> str:
        for nm, idx in self.nodes.items():
            if idx == node_id:
                return nm
        raise KeyError(node_id)


class _FakeBackend:
    Circuit = _FakeCircuit


def _instance_payload(
    instance_id: str,
    instance_name: str,
    definition_id: str,
    pin_nodes: list[str],
) -> dict[str, Any]:
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


def _build_r_definition_with_markers(resistance: float = 100.0) -> SubcircuitDefinition:
    """Two-terminal resistor definition built using SUBCIRCUIT_PORT
    markers instead of static SubcircuitPort entries.

    Internal layout:
        [PORT marker A] ──wire── [R left pin]   [R right pin] ──wire── [PORT marker B]
    """
    body = Circuit(name="RPair")
    r = Component(
        type=ComponentType.RESISTOR,
        name="R_inner",
        x=0.0, y=0.0,
        parameters={"resistance": resistance},
        pins=[Pin(0, "1", -25, 0), Pin(1, "2", 25, 0)],
    )
    # Marker on the left side. side=left → pin sits at (marker.x + 40, 0).
    # We position the marker so the pin lands at (-25, 0) (R's left pin).
    pa = Component(
        type=ComponentType.SUBCIRCUIT_PORT,
        name="X_A",
        x=-65, y=0,
        parameters={"port_name": "A", "side": "left"},
    )
    # side=right → marker pin sits at (marker.x - 40, 0). Position so
    # the pin lands at (+25, 0) (R's right pin).
    pb = Component(
        type=ComponentType.SUBCIRCUIT_PORT,
        name="X_B",
        x=65, y=0,
        parameters={"port_name": "B", "side": "right"},
    )
    body.add_component(r)
    body.add_component(pa)
    body.add_component(pb)

    # Connect explicitly via WireConnection so build_node_map unions
    # the marker pin with R's pin regardless of grid snap.
    body.add_wire(Wire(
        segments=[WireSegment(-25, 0, -25, 0)],
        start_connection=WireConnection(component_id=r.id, pin_index=0),
        end_connection=WireConnection(component_id=pa.id, pin_index=0),
    ))
    body.add_wire(Wire(
        segments=[WireSegment(25, 0, 25, 0)],
        start_connection=WireConnection(component_id=r.id, pin_index=1),
        end_connection=WireConnection(component_id=pb.id, pin_index=0),
    ))

    defn = SubcircuitDefinition(name="R_marker_def", circuit=body)
    sync_definition_ports_from_markers(defn)
    return defn


def test_marker_definition_flattens_to_resistor_on_external_nets() -> None:
    """A definition whose ports come from markers must produce the
    same flat netlist as the static-port version — one resistor on
    the two external nets wired to the instance."""
    defn = _build_r_definition_with_markers(resistance=470.0)
    defn_id = str(defn.id)

    # Sanity: the markers were turned into ports
    assert {p.name for p in defn.ports} == {"A", "B"}
    # And the internal_node fields are populated (otherwise the
    # bridge would be a no-op).
    for p in defn.ports:
        assert p.internal_node, f"port {p.name} has empty internal_node"

    instance_id = str(uuid4())
    # Pin order in instance.pin_nodes must match definition.ports
    # pin_index order. Let's read them in the order the converter sees:
    ports_by_index = sorted(defn.ports, key=lambda p: p.pin_index)
    # External nets per port — picked arbitrarily, the test only cares
    # that each one shows up on the right side of the resistor stamp.
    ext_nets = {ports_by_index[0].name: "EXT_A",
                ports_by_index[1].name: "EXT_B"}
    pin_nodes = [ext_nets[p.name] for p in ports_by_index]

    circuit_data = {
        "components": [
            _instance_payload(instance_id, "U1", defn_id, pin_nodes=pin_nodes)
        ],
        "node_map": {instance_id: list(pin_nodes)},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake = converter.build(circuit_data)

    # The SUBCIRCUIT instance is gone from the components list.
    assert not any(c.get("type") == "SUBCIRCUIT" for c in circuit_data["components"])

    # Exactly one resistor — the SUBCIRCUIT_PORT markers must NOT
    # have leaked into the flat netlist as devices.
    assert len(fake.resistor_calls) == 1
    call = fake.resistor_calls[0]
    assert call["resistance"] == pytest.approx(470.0)

    # Stamped on the right external nets.
    assert {call["n1"], call["n2"]} == {
        fake.nodes["NEXT_A"],
        fake.nodes["NEXT_B"],
    }
    # No extra synthesized devices from the markers either.
    assert all(
        c.get("type") != "SUBCIRCUIT_PORT"
        for c in circuit_data["components"]
    )


def test_marker_payload_does_not_emit_subcircuit_port_devices() -> None:
    """Belt-and-suspenders: even if the user opens an older project
    file and the converter receives a payload that still includes
    marker components inside the flattened output, those markers
    must be dropped. (This guards against future refactors that
    accidentally route markers through the per-component emission
    loop instead of the early-skip branch.)"""
    defn = _build_r_definition_with_markers(resistance=100.0)
    defn_id = str(defn.id)

    instance_id = str(uuid4())
    ports_by_index = sorted(defn.ports, key=lambda p: p.pin_index)
    pin_nodes = ["L", "R"]
    if ports_by_index[0].name != "A":
        # In case sync emitted ports in a different order, normalize
        pin_nodes = ["R", "L"]

    circuit_data = {
        "components": [
            _instance_payload(instance_id, "U", defn_id, pin_nodes=pin_nodes)
        ],
        "node_map": {instance_id: list(pin_nodes)},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    converter.build(circuit_data)

    # Inspect the flattened components list — no SUBCIRCUIT_PORT
    # entries must remain, only the inner R.
    types_emitted = {c.get("type") for c in circuit_data["components"]}
    assert "SUBCIRCUIT_PORT" not in types_emitted
    # And RESISTOR is the only non-trivial entry.
    assert "RESISTOR" in {str(t).upper() for t in types_emitted}


def test_safety_net_resync_at_flatten_time() -> None:
    """If a definition has markers but ``ports`` is stale (e.g. the
    GUI's auto-sync hook didn't run), the converter must re-sync
    inside ``_expand_single_instance`` so the bridging still works.

    Built by deliberately wiping definition.ports after sync and
    confirming the converter still produces a correct stamp.
    """
    defn = _build_r_definition_with_markers(resistance=33.0)
    # Wipe the port list — simulates a missed auto-sync. The
    # converter's safety net should rebuild it from the markers
    # before reading internal_node.
    defn.ports = []
    defn_id = str(defn.id)

    instance_id = str(uuid4())
    # Without ports, the instance pin_nodes ordering is ambiguous.
    # We give two external nets that exercise the same bridging path.
    pin_nodes = ["X", "Y"]

    circuit_data = {
        "components": [
            _instance_payload(instance_id, "U", defn_id, pin_nodes=pin_nodes)
        ],
        "node_map": {instance_id: list(pin_nodes)},
        "node_aliases": {},
        "subcircuits": {defn_id: defn.to_dict()},
    }

    converter = CircuitConverter(_FakeBackend)
    fake = converter.build(circuit_data)

    assert len(fake.resistor_calls) == 1
    call = fake.resistor_calls[0]
    assert call["resistance"] == pytest.approx(33.0)
    # The resistor must be stamped on the two external nets we
    # supplied — not on synthesized "port open" nets (which would
    # indicate the safety-net sync failed to populate internal_node).
    assert {call["n1"], call["n2"]} == {fake.nodes["NX"], fake.nodes["NY"]}
