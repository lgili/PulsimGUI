"""A net label on a GROUNDED net must not steal the ground identity.

Pins the bug found while authoring the NPC example: a GOTO label ("MID") wired
to a grounded net made ``build_node_alias_map`` rename node "0" → "MID"; the
converter then no longer recognised the reference node and the whole bus
silently floated (the NPC output sat at −57 V offset). Ground always wins —
the label stays visual-only.
"""
from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map


def _wire(circuit: Circuit, ca: Component, pa: int, cb: Component, pb: int) -> None:
    ax, ay = ca.get_pin_position(pa)
    bx, by = cb.get_pin_position(pb)
    circuit.add_wire(Wire(
        segments=[WireSegment(x1=ax, y1=ay, x2=bx, y2=by)],
        start_connection=WireConnection(component_id=ca.id, pin_index=pa),
        end_connection=WireConnection(component_id=cb.id, pin_index=pb),
    ))


def test_label_on_grounded_net_does_not_unground_it() -> None:
    circuit = Circuit(name="t")
    gnd = Component(type=ComponentType.GROUND, name="GND1", x=0, y=0)
    lbl = Component(type=ComponentType.GOTO_LABEL, name="LBL", x=120, y=-20)
    lbl.parameters["net_label"] = "MID"
    res = Component(type=ComponentType.RESISTOR, name="R1", x=240, y=-20)
    for c in (gnd, lbl, res):
        circuit.add_component(c)
    _wire(circuit, gnd, 0, lbl, 0)             # label ON the grounded net
    _wire(circuit, lbl, 0, res, 0)

    node_map = build_node_map(circuit)
    alias = build_node_alias_map(circuit, node_map)

    # the grounded net resolves to "0" and the alias map never renames it
    grounded = node_map[(str(gnd.id), 0)]
    assert grounded == "0"
    assert "0" not in alias                     # ground identity preserved
    # R1's first pin sits on the same grounded net
    assert node_map[(str(res.id), 0)] == "0"


def test_label_on_normal_net_still_aliases() -> None:
    circuit = Circuit(name="t")
    lbl = Component(type=ComponentType.GOTO_LABEL, name="LBL", x=0, y=0)
    lbl.parameters["net_label"] = "VBUS"
    res = Component(type=ComponentType.RESISTOR, name="R1", x=120, y=0)
    for c in (lbl, res):
        circuit.add_component(c)
    _wire(circuit, lbl, 0, res, 0)

    node_map = build_node_map(circuit)
    alias = build_node_alias_map(circuit, node_map)
    node = node_map[(str(lbl.id), 0)]
    assert node != "0"
    assert alias.get(node) == "VBUS"            # labels keep working off-ground
