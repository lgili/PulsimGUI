"""Regression tests for wire ``auto-jog`` interaction.

When the user clicks a *pin-locked* wire segment (first/last segment of a
wire whose endpoint is anchored to a component pin), the WireItem inserts a
Z-shaped jog so the segment becomes draggable while keeping both endpoints
attached to their pins. Before this, wires that ran straight between two
pins (very common) had no draggable segment and felt "stuck".

Evolution notes (v1.1.1 → v1.1.2):
* The jog used to be a small ``±20 px`` band centred on the click point,
  which left two big H/V stubs at the original y/x — the user reported
  "looks like a square / leftover wire". The jog now anchors at the
  segment *endpoints* with tiny ``8 px`` stubs near each pin, so dragging
  the long middle reads as "the whole wire moved" rather than "a small
  rectangle popped out".
"""
from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import QPointF

from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.views.schematic.items.wire_item import WireItem


def _conn() -> WireConnection:
    return WireConnection(component_id=uuid4(), pin_index=0)


def _make_pin_to_pin_wire(*, horizontal: bool = True, length: float = 200.0) -> Wire:
    """1-segment wire whose both endpoints are anchored to (mock) pins."""
    if horizontal:
        seg = WireSegment(0.0, 0.0, length, 0.0)
    else:
        seg = WireSegment(0.0, 0.0, 0.0, length)
    return Wire(segments=[seg], start_connection=_conn(), end_connection=_conn())


def test_jog_inserts_5_segments_into_horizontal_pin_wire(qapp) -> None:
    wire = _make_pin_to_pin_wire(horizontal=True, length=200)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(100.0, 0.0)) is True
    assert len(wire.segments) == 5
    s = wire.segments
    # Endpoints unchanged (pins must remain anchored).
    assert (s[0].x1, s[0].y1) == (0.0, 0.0)
    assert (s[4].x2, s[4].y2) == (200.0, 0.0)
    # Tiny 8-px stubs flank the wide middle — middle spans (8, 0)→(192, 0)
    # for a 200-px wire so it covers ~95 % of the run, not a small tab.
    assert (s[0].x1, s[0].x2) == (0.0, 8.0)
    assert (s[4].x1, s[4].x2) == (192.0, 200.0)
    assert (s[2].x1, s[2].y1, s[2].x2, s[2].y2) == (8.0, 0.0, 192.0, 0.0)


def test_jog_inserts_into_vertical_pin_wire(qapp) -> None:
    wire = _make_pin_to_pin_wire(horizontal=False, length=200)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(0.0, 100.0)) is True
    assert len(wire.segments) == 5
    # Middle vertical spans the wire minus 8 px stubs at each pin.
    mid = wire.segments[2]
    assert (mid.x1, mid.y1, mid.x2, mid.y2) == (0.0, 8.0, 0.0, 192.0)


def test_jog_placement_is_click_position_independent(qapp) -> None:
    """Clicking near the start pin and clicking dead-centre yield the same
    geometry — the jog now always anchors at the endpoints, so where the
    user clicks only determines *whether* the jog is inserted, not where."""
    wire_left = _make_pin_to_pin_wire(horizontal=True, length=200)
    wire_centre = _make_pin_to_pin_wire(horizontal=True, length=200)
    WireItem(wire_left)._insert_drag_jog(0, QPointF(10.0, 0.0))
    WireItem(wire_centre)._insert_drag_jog(0, QPointF(100.0, 0.0))

    geom_left = [(s.x1, s.y1, s.x2, s.y2) for s in wire_left.segments]
    geom_centre = [(s.x1, s.y1, s.x2, s.y2) for s in wire_centre.segments]
    assert geom_left == geom_centre


def test_jog_refused_when_segment_too_short(qapp) -> None:
    """Short wire (< 2·gap + min_middle = 2·8 + 20 = 36) cannot host a
    jog. The click is ignored — wire stays as the original 1 segment."""
    wire = _make_pin_to_pin_wire(horizontal=True, length=30)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(15.0, 0.0)) is False
    assert len(wire.segments) == 1


def test_legacy_diagonal_is_normalised_then_remains_draggable(qapp) -> None:
    """A legacy diagonal segment is auto-normalised into an orthogonal L
    on WireItem construction. The two resulting orthogonal segments are
    then individually jog-eligible — this confirms the jog path composes
    with the load-time normalisation rather than rejecting it."""
    wire = Wire(
        segments=[WireSegment(0.0, 0.0, 100.0, 50.0)],  # diagonal
        start_connection=_conn(),
        end_connection=_conn(),
    )
    item = WireItem(wire)
    # WireItem normalises the diagonal into a 2-segment L on construct.
    assert len(wire.segments) == 2
    # And each orthogonal piece can host a jog now.
    assert item._insert_drag_jog(0, QPointF(50.0, 0.0)) is True
    assert len(wire.segments) == 6  # was 2, jog adds 4


def test_jog_with_drag_simulates_z_shape(qapp) -> None:
    """Insert jog + drag the middle vertically — the wire forms a Z,
    endpoints stay anchored, and the middle covers most of the wire so the
    drag visually reads as "the wire moved" rather than a small tab."""
    wire = _make_pin_to_pin_wire(horizontal=True, length=200)
    item = WireItem(wire)
    item._insert_drag_jog(0, QPointF(100.0, 0.0))

    # Drag the middle (index 2) downward by 40 px using the existing helper.
    item._move_segment_fluid(2, QPointF(0.0, 40.0))

    s = wire.segments
    # Endpoints unchanged.
    assert (s[0].x1, s[0].y1) == (0.0, 0.0)
    assert (s[4].x2, s[4].y2) == (200.0, 0.0)
    # Middle now at y=40, spanning the wide range (8, 40)→(192, 40).
    assert (s[2].x1, s[2].y1, s[2].x2, s[2].y2) == (8.0, 40.0, 192.0, 40.0)
    # V stubs now span 0 → 40 at x=8 and x=192 (the new bend points).
    assert (s[1].x1, s[1].x2, s[1].y1, s[1].y2) == (8.0, 8.0, 0.0, 40.0)
    assert (s[3].x1, s[3].x2, s[3].y1, s[3].y2) == (192.0, 192.0, 40.0, 0.0)
