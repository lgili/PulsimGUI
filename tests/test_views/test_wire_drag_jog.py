"""Regression tests for wire ``auto-jog`` interaction.

When the user clicks a *pin-locked* wire segment (first/last segment of a
wire whose endpoint is anchored to a component pin), the WireItem inserts a
Z-shaped jog at the click point so the segment becomes draggable while
keeping both endpoints attached to their pins. Before this, wires that
ran straight between two pins (very common) had no draggable segment and
felt "stuck".
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
    # Middle segment is horizontal at y=0 (zero-displacement) and sits
    # between cx-20 and cx+20.
    assert (s[2].x1, s[2].y1, s[2].x2, s[2].y2) == (80.0, 0.0, 120.0, 0.0)


def test_jog_inserts_into_vertical_pin_wire(qapp) -> None:
    wire = _make_pin_to_pin_wire(horizontal=False, length=200)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(0.0, 100.0)) is True
    assert len(wire.segments) == 5
    # Middle segment is the vertical jog spanning cy-20 to cy+20.
    mid = wire.segments[2]
    assert (mid.x1, mid.y1, mid.x2, mid.y2) == (0.0, 80.0, 0.0, 120.0)


def test_jog_clamps_click_near_endpoint(qapp) -> None:
    """A click near the start pin (e.g. x=2 on a 200-px wire) is clamped
    so the jog fits inside the segment without crossing the endpoint."""
    wire = _make_pin_to_pin_wire(horizontal=True, length=200)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(2.0, 0.0)) is True
    mid = wire.segments[2]
    # Middle ends are well inside (0, 200), no overshoot.
    assert mid.x1 >= 4.0
    assert mid.x2 <= 196.0
    assert (mid.y1, mid.y2) == (0.0, 0.0)


def test_jog_refused_when_segment_too_short(qapp) -> None:
    """30-px wire can't fit a 40-px-wide jog with margin → refuse."""
    wire = _make_pin_to_pin_wire(horizontal=True, length=30)
    item = WireItem(wire)

    assert item._insert_drag_jog(0, QPointF(15.0, 0.0)) is False
    assert len(wire.segments) == 1  # unchanged


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
    endpoints stay anchored, and all segments are still orthogonal."""
    wire = _make_pin_to_pin_wire(horizontal=True, length=200)
    item = WireItem(wire)
    item._insert_drag_jog(0, QPointF(100.0, 0.0))

    # Drag the middle (index 2) downward by 40 px using the existing helper.
    item._move_segment_fluid(2, QPointF(0.0, 40.0))

    s = wire.segments
    # Endpoints unchanged.
    assert (s[0].x1, s[0].y1) == (0.0, 0.0)
    assert (s[4].x2, s[4].y2) == (200.0, 0.0)
    # Middle is now horizontal at y=40, V stubs span 0 → 40 on each side.
    assert (s[2].y1, s[2].y2) == (40.0, 40.0)
    # First V stub: from (80, 0) (prev end) to (80, 40) (middle start).
    assert (s[1].x1, s[1].x2) == (80.0, 80.0)
    assert (s[1].y1, s[1].y2) == (0.0, 40.0)
    # Second V stub: from (120, 40) to (120, 0).
    assert (s[3].x1, s[3].x2) == (120.0, 120.0)
    assert (s[3].y1, s[3].y2) == (40.0, 0.0)
