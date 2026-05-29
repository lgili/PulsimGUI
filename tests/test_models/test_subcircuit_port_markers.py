"""Tests for the SUBCIRCUIT_PORT marker (the new in-body way to
declare subcircuit boundary connections).

The marker is a pseudo-component placed inside a SubcircuitDefinition's
body. It carries a name, a direction (input/output/bidir), and a side
(left/right/top/bottom). A sync helper rebuilds
``SubcircuitDefinition.ports`` from the markers it finds, and a refresh
helper propagates the new pin layout to every SubcircuitInstance that
points to this definition.

These tests pin the contract at the model layer; flattening with
markers is covered by ``test_subcircuit_port_marker_flattening.py``.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    Component,
    ComponentType,
    DEFAULT_PARAMETERS,
    Pin,
    _synchronize_special_component,
)
from pulsimgui.models.project import Project
from pulsimgui.models.subcircuit import (
    SubcircuitDefinition,
    SubcircuitInstance,
    refresh_subcircuit_instance_pins,
    sync_definition_ports_from_markers,
)
from pulsimgui.models.wire import Wire, WireSegment


def _make_marker(
    port_name: str = "P",
    side: str = "left",
    direction: str = "bidir",
    x: float = 0.0,
    y: float = 0.0,
) -> Component:
    return Component(
        type=ComponentType.SUBCIRCUIT_PORT,
        name=f"X_{port_name}",
        x=x, y=y,
        parameters={"port_name": port_name, "side": side, "direction": direction},
    )


def test_marker_creation_uses_defaults() -> None:
    """A bare SUBCIRCUIT_PORT created without explicit parameters
    must pick up the catalog defaults so the user can drag one onto
    the canvas and start editing immediately."""
    m = Component(type=ComponentType.SUBCIRCUIT_PORT, name="X", x=0, y=0)
    expected = DEFAULT_PARAMETERS[ComponentType.SUBCIRCUIT_PORT]
    assert m.parameters["port_name"] == expected["port_name"]
    assert m.parameters["direction"] == expected["direction"]
    assert m.parameters["side"] == expected["side"]
    assert len(m.pins) == 1


@pytest.mark.parametrize("side,expected_pin", [
    ("left",   ( 40.0,  0.0)),
    ("right",  (-40.0,  0.0)),
    ("top",    (  0.0, 20.0)),   # snapped from 25 to grid 20
    ("bottom", (  0.0, -20.0)),
])
def test_marker_pin_moves_with_side(side: str, expected_pin: tuple) -> None:
    """The marker's single pin always faces *into* the subcircuit
    body (so wires from inner components attach naturally). Changing
    the ``side`` parameter must move the pin to the opposite edge of
    the marker."""
    m = _make_marker(side=side)
    assert (m.pins[0].x, m.pins[0].y) == expected_pin


def test_marker_pin_label_mirrors_port_name() -> None:
    """The marker's pin name shows up in tooltips and wire-routing
    diagnostics. It should always equal ``port_name`` so the inner
    schematic surface is debuggable."""
    m = _make_marker(port_name="V_BUS")
    assert m.pins[0].name == "V_BUS"

    m.parameters["port_name"] = "I_LOAD"
    _synchronize_special_component(m)
    assert m.pins[0].name == "I_LOAD"


def test_sync_definition_ports_from_markers_produces_one_port_per_marker() -> None:
    """One marker → one port. Port name + position come from the
    marker; ``internal_node`` reflects the net the marker pin sits on."""
    body = Circuit(name="Body")
    r = Component(type=ComponentType.RESISTOR, name="R1", x=0, y=0,
                  parameters={"resistance": 100.0})
    pa = _make_marker(port_name="A", side="left", x=-50, y=0)
    pb = _make_marker(port_name="B", side="right", x=50, y=0)
    for c in (r, pa, pb):
        body.components[c.id] = c

    defn = SubcircuitDefinition(name="D", circuit=body)
    changed = sync_definition_ports_from_markers(defn)
    assert changed is True

    names = {p.name for p in defn.ports}
    assert names == {"A", "B"}

    by_name = {p.name: p for p in defn.ports}
    # Left side is on the left edge of the outer symbol — negative x.
    assert by_name["A"].x < 0
    assert by_name["B"].x > 0
    # Each port has a stable pin_index (used by the converter to
    # map external nets to internal ones).
    assert {p.pin_index for p in defn.ports} == {0, 1}


def test_sync_with_no_markers_returns_false_and_preserves_existing_ports() -> None:
    """Backward compat: a definition built from the old
    ``create_subcircuit_from_selection`` path stores ports directly
    (no markers). Sync must leave it alone."""
    from pulsimgui.models.subcircuit import SubcircuitPort

    body = Circuit(name="Body")
    body.components[uuid4()] = Component(type=ComponentType.RESISTOR, name="R", x=0, y=0)

    legacy_port = SubcircuitPort(name="legacy", internal_node="3", pin_index=0, x=-40, y=0)
    defn = SubcircuitDefinition(name="D", circuit=body, ports=[legacy_port])

    changed = sync_definition_ports_from_markers(defn)
    assert changed is False
    assert defn.ports == [legacy_port]


def test_sync_returns_false_on_no_op_resync() -> None:
    """Calling sync twice with no edits in between must not signal
    a change (avoids noisy refresh cycles)."""
    body = Circuit(name="Body")
    body.components[uuid4()] = _make_marker(port_name="A", side="left")
    defn = SubcircuitDefinition(name="D", circuit=body)
    assert sync_definition_ports_from_markers(defn) is True
    # Idempotent
    assert sync_definition_ports_from_markers(defn) is False


def test_multiple_markers_on_same_side_distribute_along_edge() -> None:
    """N markers on the same side land on distinct y-positions along
    that edge (no two pins on top of each other)."""
    body = Circuit(name="Body")
    for i, name in enumerate(("A", "B", "C")):
        m = _make_marker(port_name=name, side="left", x=-50, y=i * 20)
        body.components[m.id] = m

    defn = SubcircuitDefinition(name="D", circuit=body)
    sync_definition_ports_from_markers(defn)

    ys = sorted(p.y for p in defn.ports)
    assert len(set(ys)) == 3, "Each port must have a unique y"
    # All on the left edge → same x
    assert len({p.x for p in defn.ports}) == 1


def test_markers_on_different_sides_land_on_matching_edges() -> None:
    """A marker with side=top must produce a port with y = -height/2,
    side=bottom with y = +height/2, etc."""
    body = Circuit(name="Body")
    for side, port_name in (("left", "L"), ("right", "R"),
                            ("top", "T"), ("bottom", "B")):
        m = _make_marker(port_name=port_name, side=side)
        body.components[m.id] = m

    defn = SubcircuitDefinition(name="D", circuit=body,
                                symbol_width=100.0, symbol_height=80.0)
    sync_definition_ports_from_markers(defn)

    by_name = {p.name: p for p in defn.ports}
    assert by_name["L"].x == pytest.approx(-50.0)   # -width/2
    assert by_name["R"].x == pytest.approx(+50.0)   # +width/2
    assert by_name["T"].y == pytest.approx(-40.0)   # -height/2
    assert by_name["B"].y == pytest.approx(+40.0)   # +height/2


def test_sync_picks_up_internal_node_from_wire_connectivity() -> None:
    """The marker's pin connects to a net inside the subcircuit
    via a wire. After sync, ``port.internal_node`` should equal
    the union-find node label for that pin — which is what the
    flattener uses to bridge external nets."""
    body = Circuit(name="Body")
    r = Component(type=ComponentType.RESISTOR, name="R", x=0, y=0,
                  pins=[Pin(0, "1", -25, 0), Pin(1, "2", 25, 0)],
                  parameters={"resistance": 100.0})
    pin_marker = _make_marker(port_name="LEFT", side="left", x=-80, y=0)
    body.components[r.id] = r
    body.components[pin_marker.id] = pin_marker
    # Wire connects R.pin0 (-25, 0) to marker.pin (-80+40 = -40, 0)
    wire = Wire(segments=[WireSegment(-25, 0, -40, 0)])
    body.wires[wire.id] = wire

    defn = SubcircuitDefinition(name="D", circuit=body)
    sync_definition_ports_from_markers(defn)

    left_port = next(p for p in defn.ports if p.name == "LEFT")
    # The exact net label is implementation-dependent (it could be
    # "1" or "2" depending on union-find seed), but it MUST be a
    # non-empty string — that's what bridges to the external net
    # at flatten time.
    assert left_port.internal_node != "", (
        "Marker connected to a wire must populate internal_node"
    )


def test_refresh_subcircuit_instance_pins_propagates_to_all_instances() -> None:
    """Two instances of the same definition in the parent circuit
    must BOTH pick up the renamed port after sync + refresh."""
    body = Circuit(name="Body")
    body.components[uuid4()] = _make_marker(port_name="A", side="left")
    defn = SubcircuitDefinition(name="D", circuit=body)
    sync_definition_ports_from_markers(defn)

    project = Project(name="p")
    project.add_subcircuit(defn)
    root = Circuit(name="main")
    project.circuits["main"] = root
    project.active_circuit = "main"

    u1 = SubcircuitInstance(name="U1", x=0, y=0,
                            subcircuit_id=defn.id, pins=defn.get_pins())
    u2 = SubcircuitInstance(name="U2", x=100, y=0,
                            subcircuit_id=defn.id, pins=defn.get_pins())
    root.components[u1.id] = u1
    root.components[u2.id] = u2

    # Rename inside
    marker = next(c for c in body.components.values()
                  if c.type == ComponentType.SUBCIRCUIT_PORT)
    marker.parameters["port_name"] = "V_OUT"
    sync_definition_ports_from_markers(defn)

    touched = refresh_subcircuit_instance_pins(project, defn)
    assert touched == 2
    assert u1.pins[0].name == "V_OUT"
    assert u2.pins[0].name == "V_OUT"


def test_refresh_skips_instances_pointing_to_other_definitions() -> None:
    """``refresh_subcircuit_instance_pins`` must scope its mutation
    to the specific definition — instances of other subcircuits in
    the project stay untouched."""
    body_a = Circuit(name="A")
    body_a.components[uuid4()] = _make_marker(port_name="a_pin", side="left")
    defn_a = SubcircuitDefinition(name="A", circuit=body_a)
    sync_definition_ports_from_markers(defn_a)

    body_b = Circuit(name="B")
    body_b.components[uuid4()] = _make_marker(port_name="b_pin", side="left")
    defn_b = SubcircuitDefinition(name="B", circuit=body_b)
    sync_definition_ports_from_markers(defn_b)

    project = Project(name="p")
    project.add_subcircuit(defn_a)
    project.add_subcircuit(defn_b)
    root = Circuit(name="main")
    project.circuits["main"] = root
    project.active_circuit = "main"

    u_a = SubcircuitInstance(name="UA", x=0, y=0,
                             subcircuit_id=defn_a.id, pins=defn_a.get_pins())
    u_b = SubcircuitInstance(name="UB", x=100, y=0,
                             subcircuit_id=defn_b.id, pins=defn_b.get_pins())
    root.components[u_a.id] = u_a
    root.components[u_b.id] = u_b

    # Only A changes
    marker_a = next(c for c in body_a.components.values()
                    if c.type == ComponentType.SUBCIRCUIT_PORT)
    marker_a.parameters["port_name"] = "VCC"
    sync_definition_ports_from_markers(defn_a)
    touched = refresh_subcircuit_instance_pins(project, defn_a)

    assert touched == 1
    assert u_a.pins[0].name == "VCC"
    assert u_b.pins[0].name == "b_pin", (
        "Refreshing definition A must not perturb instances of B"
    )


def test_round_trip_through_project_save_load(tmp_path) -> None:
    """Saving + reloading a project preserves marker components inside
    the definition body (so the sync can run again on next edit)."""
    body = Circuit(name="Body")
    m = _make_marker(port_name="OUT", direction="output", side="right")
    body.components[m.id] = m

    defn = SubcircuitDefinition(name="D", circuit=body)
    sync_definition_ports_from_markers(defn)

    project = Project(name="p")
    project.add_subcircuit(defn)
    project.circuits["main"] = Circuit(name="main")
    project.active_circuit = "main"

    path = tmp_path / "demo.pulsim"
    project.save(path)

    loaded = Project.load(path)
    loaded_defn = list(loaded.subcircuits.values())[0]

    markers = [c for c in loaded_defn.circuit.components.values()
               if c.type == ComponentType.SUBCIRCUIT_PORT]
    assert len(markers) == 1
    assert markers[0].parameters["port_name"] == "OUT"
    assert markers[0].parameters["direction"] == "output"
    assert markers[0].parameters["side"] == "right"
