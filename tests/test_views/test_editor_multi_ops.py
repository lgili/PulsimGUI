"""Multi-component editor operations: copy/paste/cut/duplicate of a whole
selection (with its internal wiring) and group-drag collision handling.

These pin the fixes for the three classic editor bugs:
* copy/cut only acted on the FIRST selected component (loop ``break``);
* Ctrl+D duplicated a fresh default component (parameters lost);
* group-drag froze because co-selected items collided with each other's
  mid-drag rects in ``resolve_component_position``.
"""
from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QPointF

from pulsimgui.commands.base import CompositeCommand
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.views.schematic.items import WireItem, create_component_item
from pulsimgui.views.schematic.scene import SchematicScene
from pulsimgui.views.schematic.view import SchematicView


def _make_component(name: str, x: float, y: float, **params) -> Component:
    comp = Component(type=ComponentType.RESISTOR, name=name, x=x, y=y)
    comp.parameters.update(params)
    return comp


def _build_view_with_stage() -> tuple[SchematicView, SchematicScene, list[Component], Wire]:
    """Two wired resistors + one bystander, the wired pair selected."""
    scene = SchematicScene()
    view = SchematicView(scene)
    c1 = _make_component("R1", 0.0, 0.0, resistance=123.0)
    c2 = _make_component("R2", 200.0, 0.0, resistance=456.0)
    c3 = _make_component("R3", 600.0, 600.0, resistance=789.0)
    items = []
    for comp in (c1, c2, c3):
        item = create_component_item(comp)
        scene.addItem(item)
        items.append(item)
    wire = Wire(
        id=uuid4(),
        segments=[WireSegment(x1=40.0, y1=0.0, x2=160.0, y2=0.0)],
        start_connection=WireConnection(component_id=c1.id, pin_index=1),
        end_connection=WireConnection(component_id=c2.id, pin_index=0),
    )
    scene.addItem(WireItem(wire))
    items[0].setSelected(True)
    items[1].setSelected(True)
    return view, scene, [c1, c2, c3], wire


def test_copy_selected_copies_whole_selection_with_wiring(qapp) -> None:
    view, _scene, _comps, _wire = _build_view_with_stage()
    try:
        view.copy_selected()
        assert len(view._clipboard_components_data) == 2          # both, not 1
        names = {d["name"] for d in view._clipboard_components_data}
        assert names == {"R1", "R2"}
        # the wire between the two selected components rides along
        assert len(view._clipboard_wires_data) == 1
    finally:
        view.close()


def test_paste_preserves_params_positions_and_remaps_wires(qapp) -> None:
    view, _scene, comps, wire = _build_view_with_stage()
    try:
        view.copy_selected()
        pasted: list = []
        view.selection_pasted.connect(lambda cs, ws: pasted.append((cs, ws)))
        view._paste_component(None)                # blind paste ⇒ +40/+40
        assert len(pasted) == 1
        new_comps, new_wires = pasted[0]
        assert len(new_comps) == 2 and len(new_wires) == 1

        by_name_src = {c.name: c for c in comps}
        for nc in new_comps:
            assert nc.name not in by_name_src                  # fresh names
        # parameters preserved (the original bug lost them)
        params = sorted(c.parameters.get("resistance") for c in new_comps)
        assert params == [123.0, 456.0]
        # relative placement preserved: same +40/+40 shift on both
        xs = sorted(c.x for c in new_comps)
        assert xs == [40.0, 240.0]
        # wire endpoints remapped to the NEW ids and geometry shifted
        nw = new_wires[0]
        new_ids = {str(c.id) for c in new_comps}
        assert str(nw.start_connection.component_id) in new_ids
        assert str(nw.end_connection.component_id) in new_ids
        assert str(nw.id) != str(wire.id)
        seg = nw.segments[0]
        assert (seg.x1, seg.y1, seg.x2, seg.y2) == (80.0, 40.0, 200.0, 40.0)
    finally:
        view.close()


def test_duplicate_selected_preserves_parameters(qapp) -> None:
    view, _scene, _comps, _wire = _build_view_with_stage()
    try:
        pasted: list = []
        view.selection_pasted.connect(lambda cs, ws: pasted.append((cs, ws)))
        view.duplicate_selected()
        assert len(pasted) == 1
        new_comps, new_wires = pasted[0]
        assert len(new_comps) == 2 and len(new_wires) == 1
        assert sorted(c.parameters.get("resistance") for c in new_comps) == [123.0, 456.0]
        # clipboard untouched by duplicate
        assert view._clipboard_components_data == []
    finally:
        view.close()


def test_cut_selected_fills_clipboard_and_requests_deletes(qapp) -> None:
    view, _scene, _comps, _wire = _build_view_with_stage()
    try:
        deleted: list[str] = []
        view.component_delete_requested.connect(deleted.append)
        view.cut_selected()
        assert len(view._clipboard_components_data) == 2
        assert len(deleted) == 2                                # both, not 1
    finally:
        view.close()


def test_group_drag_skips_co_selected_collisions(qapp) -> None:
    """Adjacent co-selected items must not 'collide' with each other while the
    group is being dragged (the bug froze the whole group in place)."""
    view, scene, _comps, _wire = _build_view_with_stage()
    try:
        items = [it for it in scene.items()
                 if hasattr(it, "component") and it.isSelected()]
        assert len(items) == 2
        a, b = items
        # Place the candidate directly ON the co-selected neighbour: with the
        # fix this is NOT an overlap (both move together).
        assert not scene._component_overlaps_at(a, QPointF(b.pos()))
        # ...but it still collides with an UNSELECTED component.
        bystander = next(it for it in scene.items()
                         if hasattr(it, "component") and not it.isSelected())
        assert scene._component_overlaps_at(a, QPointF(bystander.pos()))
    finally:
        view.close()


def test_composite_command_executes_and_undoes_as_one() -> None:
    log: list[str] = []

    class _Cmd:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def execute(self) -> None:
            log.append(f"+{self.tag}")

        def undo(self) -> None:
            log.append(f"-{self.tag}")

        @property
        def description(self) -> str:
            return self.tag

    composite = CompositeCommand([_Cmd("a"), _Cmd("b")], "Paste 2 component(s)")
    composite.execute()
    composite.undo()
    assert log == ["+a", "+b", "-b", "-a"]      # undo in reverse order
    assert composite.description == "Paste 2 component(s)"
