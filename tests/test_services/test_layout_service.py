"""Auto-Layout: placement algorithm + single-undo command contract."""

from __future__ import annotations

from pathlib import Path

from pulsimgui.commands.layout_commands import AutoLayoutCommand
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.project import Project
from pulsimgui.models.wire import Wire, WireConnection
from pulsimgui.services.layout_service import compute_auto_layout

_EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
GRID = 20.0


def _wire(a: Component, ap: int, b: Component, bp: int) -> Wire:
    w = Wire(
        start_connection=WireConnection(a.id, ap),
        end_connection=WireConnection(b.id, bp),
    )
    w.add_segment(0.0, 0.0, 1.0, 0.0)
    return w


def _chain_circuit() -> tuple[Circuit, Component, Component, Component, Component]:
    """V1 -> R1 -> C1 chain with a ground on V1."""
    c = Circuit(name="t")
    v1 = Component(type=ComponentType.VOLTAGE_SOURCE, name="V1", x=500, y=500)
    r1 = Component(type=ComponentType.RESISTOR, name="R1", x=-50, y=900)
    c1 = Component(type=ComponentType.CAPACITOR, name="C1", x=203, y=17)
    g1 = Component(type=ComponentType.GROUND, name="GND1", x=0, y=0)
    for comp in (v1, r1, c1, g1):
        c.add_component(comp)
    c.add_wire(_wire(v1, 0, r1, 0))
    c.add_wire(_wire(r1, 1, c1, 0))
    c.add_wire(_wire(v1, 1, g1, 0))
    return c, v1, r1, c1, g1


def test_chain_layers_left_to_right_and_snaps():
    c, v1, r1, c1, g1 = _chain_circuit()
    pos = compute_auto_layout(c, grid=GRID)

    assert set(pos) == {v1.id, r1.id, c1.id, g1.id}
    # Source first, then flow left -> right.
    assert pos[v1.id][0] < pos[r1.id][0] < pos[c1.id][0]
    # Everything snapped to the grid.
    for x, y in pos.values():
        assert x % GRID == 0 and y % GRID == 0
    # Ground parks BELOW-LEFT of its neighbour (the source), out of
    # the flow and clear of the same column's next row.
    assert pos[g1.id][1] > pos[v1.id][1]
    assert pos[g1.id][0] < pos[v1.id][0]


def test_no_two_flow_components_share_a_cell():
    c, *_ = _chain_circuit()
    pos = compute_auto_layout(c, grid=GRID)
    assert len(set(pos.values())) == len(pos)


def test_isolated_component_still_gets_a_position():
    c, *_ = _chain_circuit()
    orphan = Component(type=ComponentType.RESISTOR, name="R_orphan", x=9, y=9)
    c.add_component(orphan)
    pos = compute_auto_layout(c, grid=GRID)
    assert orphan.id in pos


def test_deterministic_output():
    c, *_ = _chain_circuit()
    assert compute_auto_layout(c, grid=GRID) == compute_auto_layout(c, grid=GRID)


def test_command_applies_and_single_undo_restores_everything():
    c, v1, r1, c1, g1 = _chain_circuit()
    before_pos = {cid: (comp.x, comp.y) for cid, comp in c.components.items()}
    before_segments = {
        w.id: [(s.x1, s.y1, s.x2, s.y2) for s in w.segments]
        for w in c.wires.values()
    }

    cmd = AutoLayoutCommand(c, compute_auto_layout(c, grid=GRID), grid=GRID)
    cmd.execute()

    moved = [cid for cid, comp in c.components.items()
             if (comp.x, comp.y) != before_pos[cid]]
    assert moved, "auto-layout should move at least one component"

    cmd.undo()
    assert {cid: (comp.x, comp.y) for cid, comp in c.components.items()} == before_pos
    assert {
        w.id: [(s.x1, s.y1, s.x2, s.y2) for s in w.segments]
        for w in c.wires.values()
    } == before_segments


def test_ex20_full_project_lays_out_cleanly():
    proj = Project.load(_EXAMPLES / "20_pfc_drive_compressor.pulsim")
    gc = proj.get_active_circuit()
    pos = compute_auto_layout(gc, grid=GRID)
    assert set(pos) == set(gc.components)
    # Sanity: no NaNs, everything on-grid, more than one column used.
    xs = {p[0] for p in pos.values()}
    assert all(x == x and y == y for x, y in pos.values())
    assert len(xs) > 3
