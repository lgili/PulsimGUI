"""Tests for the Wire model — orthogonal normalization on load.

Regression: opening a saved circuit showed some wires as slanted
(diagonal) lines. A wire stored as a single diagonal segment renders
diagonal; ``normalize_orthogonal`` rewrites it into a strict H/V L-route
while preserving the polyline endpoints (so pin connectivity holds).
"""
from __future__ import annotations

from pulsimgui.models.wire import Wire, WireSegment


def _seg(w: Wire) -> list[tuple[float, float, float, float]]:
    return [(s.x1, s.y1, s.x2, s.y2) for s in w.segments]


def test_diagonal_segment_splits_into_L_preserving_endpoints() -> None:
    w = Wire(segments=[WireSegment(0.0, 0.0, 100.0, 40.0)])
    changed = w.normalize_orthogonal()
    assert changed is True
    # Endpoints preserved.
    assert w.start_point == (0.0, 0.0)
    assert w.end_point == (100.0, 40.0)
    # Two strictly H/V segments forming an L (horizontal then vertical).
    assert _seg(w) == [(0.0, 0.0, 100.0, 0.0), (100.0, 0.0, 100.0, 40.0)]
    # Every segment is now purely horizontal or vertical.
    for s in w.segments:
        assert (abs(s.x2 - s.x1) < 1e-9) or (abs(s.y2 - s.y1) < 1e-9)


def test_already_orthogonal_wire_is_untouched() -> None:
    w = Wire(segments=[
        WireSegment(0.0, 0.0, 100.0, 0.0),     # horizontal
        WireSegment(100.0, 0.0, 100.0, 40.0),  # vertical
    ])
    before = _seg(w)
    changed = w.normalize_orthogonal()
    assert changed is False
    assert _seg(w) == before


def test_mixed_wire_only_fixes_the_diagonal() -> None:
    w = Wire(segments=[
        WireSegment(0.0, 0.0, 60.0, 0.0),      # horizontal (ok)
        WireSegment(60.0, 0.0, 120.0, 50.0),   # diagonal (fix)
        WireSegment(120.0, 50.0, 120.0, 90.0),  # vertical (ok)
    ])
    assert w.normalize_orthogonal() is True
    assert w.start_point == (0.0, 0.0)
    assert w.end_point == (120.0, 90.0)
    assert _seg(w) == [
        (0.0, 0.0, 60.0, 0.0),
        (60.0, 0.0, 120.0, 0.0),
        (120.0, 0.0, 120.0, 50.0),
        (120.0, 50.0, 120.0, 90.0),
    ]


def test_empty_and_near_orthogonal_are_noops() -> None:
    assert Wire(segments=[]).normalize_orthogonal() is False
    # Sub-tolerance drift is treated as already orthogonal.
    w = Wire(segments=[WireSegment(0.0, 0.0, 100.0, 0.3)])
    assert w.normalize_orthogonal() is False
