"""Tests for the smart orthogonal wire router."""
from __future__ import annotations

import pytest

# Side-load the models package first to defuse a latent circular
# import in pulsimgui.utils.__init__.py — net_utils ↔ subcircuit ring.
import pulsimgui.models  # noqa: F401

from pulsimgui.utils.wire_router import (
    PIN_HIT_TOLERANCE,
    Obstacle,
    WireRouter,
)


# ---------------------------------------------------------------------------
# Obstacle basics
# ---------------------------------------------------------------------------
def test_obstacle_contains_point_inside_padding() -> None:
    obs = Obstacle(x=0, y=0, width=20, height=20, padding=4)
    assert obs.contains_point(10, 10)            # well inside
    assert obs.contains_point(-3, 10)            # inside padding zone
    assert not obs.contains_point(-10, 10)       # outside padding


def test_obstacle_horizontal_segment_crosses_when_through_middle() -> None:
    obs = Obstacle(x=0, y=0, width=20, height=20, padding=2)
    # Segment at y=10 (right through the middle) from x=-30 to x=30
    assert obs.segment_crosses(-30, 10, 30, 10)


def test_obstacle_horizontal_segment_above_does_not_cross() -> None:
    obs = Obstacle(x=0, y=0, width=20, height=20, padding=2)
    # Segment at y=-50 (well above), x range overlaps in X but not Y
    assert not obs.segment_crosses(-30, -50, 30, -50)


def test_obstacle_vertical_segment_through_middle_crosses() -> None:
    obs = Obstacle(x=0, y=0, width=20, height=20, padding=2)
    # Vertical line at x=10 from y=-50 to y=50
    assert obs.segment_crosses(10, -50, 10, 50)


def test_obstacle_vertical_segment_far_left_does_not_cross() -> None:
    obs = Obstacle(x=0, y=0, width=20, height=20, padding=2)
    assert not obs.segment_crosses(-50, -100, -50, 100)


# ---------------------------------------------------------------------------
# Router — single straight line when collinear and unobstructed
# ---------------------------------------------------------------------------
def test_route_horizontal_collinear_no_obstacles_returns_single_segment() -> None:
    r = WireRouter()
    segs = r.route(0, 0, 100, 0)
    assert len(segs) == 1
    assert segs[0] == (0, 0, 100, 0)


def test_route_vertical_collinear_no_obstacles_returns_single_segment() -> None:
    r = WireRouter()
    segs = r.route(40, 0, 40, 80)
    assert len(segs) == 1
    assert segs[0] == (40, 0, 40, 80)


# ---------------------------------------------------------------------------
# Router — L-routing for general endpoints
# ---------------------------------------------------------------------------
def test_route_two_endpoints_picks_l_shape_with_two_segments() -> None:
    r = WireRouter()
    segs = r.route(0, 0, 100, 80)
    assert len(segs) == 2
    # All segments must be axis-aligned (the whole point of the router)
    for x1, y1, x2, y2 in segs:
        assert abs(x1 - x2) < 1.0 or abs(y1 - y2) < 1.0


def test_route_two_l_paths_use_different_corners() -> None:
    """Critical: two wires from the same start row to the same end
    row must NOT pick the same L corner (would merge their nets)."""
    r = WireRouter()
    # First wire: (0, 0) → (200, 60)
    segs1 = r.route(0, 0, 200, 60)
    # Second wire: (0, 20) → (200, 80) — same delta pattern
    segs2 = r.route(0, 20, 200, 80)

    # Extract corner points from each route
    corners_1 = {(s[2], s[3]) for s in segs1[:-1]}
    corners_2 = {(s[2], s[3]) for s in segs2[:-1]}
    overlap = corners_1 & corners_2
    assert not overlap, f"corner collision: {overlap}"


def test_route_three_wires_from_same_row_have_unique_corners() -> None:
    """Repeat the collision test with a higher fan-in count (3 wires
    converging on the same destination column from the same source
    column) — this is the exact case that broke the PFC example."""
    r = WireRouter()
    routes = [
        r.route(0, 0, 200, 60),
        r.route(0, 20, 200, 80),
        r.route(0, 40, 200, 100),
    ]
    all_corners: list[tuple[float, float]] = []
    for segs in routes:
        for s in segs[:-1]:
            all_corners.append((s[2], s[3]))
    # Every recorded corner should be unique within tolerance
    for i in range(len(all_corners)):
        for j in range(i + 1, len(all_corners)):
            cx_i, cy_i = all_corners[i]
            cx_j, cy_j = all_corners[j]
            assert (abs(cx_i - cx_j) > PIN_HIT_TOLERANCE
                    or abs(cy_i - cy_j) > PIN_HIT_TOLERANCE), \
                f"corners {i}={all_corners[i]} and {j}={all_corners[j]} too close"


# ---------------------------------------------------------------------------
# Router — obstacle avoidance
# ---------------------------------------------------------------------------
def test_route_avoids_component_obstacle_via_z_route() -> None:
    """A component sitting directly between two pins forces a Z-route
    around it instead of the default L (which would slice through)."""
    r = WireRouter()
    r.add_obstacle(Obstacle(x=40, y=-20, width=40, height=40, padding=4))
    segs = r.route(0, 0, 120, 0)

    # The straight horizontal at y=0 would slice through the obstacle
    # (its body spans y=[-20..+20]). Router should detour above or below.
    obs = r.obstacles[0]
    for x1, y1, x2, y2 in segs:
        assert not obs.segment_crosses(x1, y1, x2, y2,
                                          allow_endpoints=True), \
            f"segment {(x1,y1,x2,y2)} crosses obstacle"


def test_route_from_components_obstacles_blocks_body_passthrough() -> None:
    """``add_obstacles_from_components`` should set up obstacles
    correctly enough that subsequent routes don't slice components."""
    r = WireRouter()
    r.add_obstacles_from_components([
        {"x": 100, "y": 0},
    ], body_half_w=20, body_half_h=15, padding=4)
    # Now route a line that WOULD pass through the component if the
    # router were obstacle-blind
    segs = r.route(0, 0, 200, 0)
    obs = r.obstacles[0]
    for x1, y1, x2, y2 in segs:
        assert not obs.segment_crosses(x1, y1, x2, y2,
                                          allow_endpoints=True)


# ---------------------------------------------------------------------------
# Router — colinear overlap avoidance (the deeper net-merge bug)
# ---------------------------------------------------------------------------
def test_two_wires_sharing_no_pin_do_not_overlap_colinearly() -> None:
    """If wire A is routed at y=0 from x=0..100 and wire B needs to
    route past y=0 too, B should NOT lay a segment at y=0 between
    x=10..90 (that's a colinear overlap → union-find merges them).
    """
    r = WireRouter()
    # Wire A: a horizontal trace
    r.route(0, 0, 100, 0)
    # Wire B from a totally different location that would naturally
    # also want to lay a horizontal at y=0
    segs_b = r.route(20, -40, 80, 40)
    # The router should choose corners that don't put any segment at
    # exactly y=0 in the overlap region [20..80].
    for x1, y1, x2, y2 in segs_b:
        if abs(y1 - 0) < PIN_HIT_TOLERANCE and abs(y2 - 0) < PIN_HIT_TOLERANCE:
            # Same Y axis as wire A — must not overlap in X
            lo, hi = sorted((x1, x2))
            assert hi <= 0 or lo >= 100 or hi - lo <= PIN_HIT_TOLERANCE


# ---------------------------------------------------------------------------
# Router — determinism
# ---------------------------------------------------------------------------
def test_router_is_deterministic_for_same_input_sequence() -> None:
    """Same setup + same route order → byte-identical segments. Keeps
    generated .pulsim files diff-friendly across regenerations."""
    def run_once() -> list[list[tuple[float, float, float, float]]]:
        r = WireRouter()
        r.add_obstacles_from_components([{"x": 100, "y": 0}])
        return [
            r.route(0, 0, 200, 40),
            r.route(0, 20, 200, 60),
            r.route(0, 40, 200, 80),
        ]
    a = run_once()
    b = run_once()
    assert a == b


# ---------------------------------------------------------------------------
# Router — grid snapping
# ---------------------------------------------------------------------------
def test_router_snaps_endpoints_to_grid() -> None:
    r = WireRouter(grid=10.0)
    segs = r.route(3, 7, 97, 23)
    # All coordinates should be multiples of 10
    for x1, y1, x2, y2 in segs:
        for v in (x1, y1, x2, y2):
            assert abs(v - round(v / 10.0) * 10.0) < 1e-9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
