"""Smart orthogonal wire router for programmatic schematic generation.

The GUI's interactive wire editor (``views/schematic/items/wire_item.py``)
already lays down clean L-shaped segments when a user drags a wire. But
when a wire is created **programmatically** — by example builders, the
device-library auto-wire, or AI-assisted schematic generation — the
default L-routing has two failure modes that this router fixes:

1. **Corner collisions silently merge nets.** The netlist builder in
   ``utils/net_utils.py`` runs a union-find over segment endpoints
   within ``PIN_HIT_TOLERANCE``. Two L-routed wires that happen to
   share an L-corner coordinate (very common when many wires go to
   the same pin row) get unioned into one electrical net — producing
   shorted-out circuits that the user can't see is wrong.

2. **Routes pass through component bodies.** A straight L from one
   side of the canvas to the other often slices through unrelated
   components, looking messy and making the schematic harder to read.

The router below addresses both:

* **Unique corners.** Every routed wire records its L-corner (or
  Z-routing mid-x) in a shared ``used_corners`` set; subsequent routes
  pick a corner offset that doesn't already exist within
  ``PIN_HIT_TOLERANCE``.
* **Obstacle avoidance.** Component bounding boxes are passed as
  ``Obstacle`` rects; the router rejects candidate segments that
  cross any obstacle (with configurable padding) and falls back
  through L → Z → diagonal until a valid path is found.

Usage::

    router = WireRouter(grid=20.0)
    router.add_obstacles_from_components(components)

    for wire_spec in wires:
        segments = router.route(start_pt, end_pt)
        # segments is a list of (x1, y1, x2, y2) tuples ready to be
        # serialized into the .pulsim wire["segments"] list.

The router is **deterministic** — given the same inputs it always
produces the same routes (no random offsets), so generated
``.pulsim`` files are diff-friendly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


# Same tolerance as ``utils/net_utils.PIN_HIT_TOLERANCE`` — keeping
# them in sync is important: any two points within this distance get
# union-find merged into the same electrical net.
PIN_HIT_TOLERANCE = 2.0


# ---------------------------------------------------------------------------
# Obstacles
# ---------------------------------------------------------------------------
@dataclass
class Obstacle:
    """Axis-aligned rectangle the router must avoid (with padding)."""

    x: float
    y: float
    width: float
    height: float
    padding: float = 4.0

    def left(self) -> float: return self.x - self.padding
    def right(self) -> float: return self.x + self.width + self.padding
    def top(self) -> float: return self.y - self.padding
    def bottom(self) -> float: return self.y + self.height + self.padding

    def contains_point(self, px: float, py: float, *,
                       margin: float = 0.0) -> bool:
        return (self.left() - margin <= px <= self.right() + margin
                and self.top() - margin <= py <= self.bottom() + margin)

    def segment_crosses(self, x1: float, y1: float,
                          x2: float, y2: float, *,
                          allow_endpoints: bool = True) -> bool:
        """True iff the segment (x1,y1)→(x2,y2) intersects the
        padded rectangle. If ``allow_endpoints`` is set, endpoints
        exactly at the rect's boundary are allowed (so pins on the
        edge of a component don't get flagged).

        Only handles horizontal/vertical segments — diagonals aren't
        used by this router so we don't need general segment-rect
        intersection.
        """
        L, R = self.left(), self.right()
        T, B = self.top(), self.bottom()

        # Snap micro-noise to zero
        if abs(y2 - y1) < 1e-9:        # horizontal segment
            y = y1
            if y <= T or y >= B:
                return False
            x_lo, x_hi = min(x1, x2), max(x1, x2)
            if x_hi <= L or x_lo >= R:
                return False
            if allow_endpoints:
                # Endpoints on/just inside boundaries are tolerated
                # because pins are positioned at component edges.
                interior_left = max(x_lo, L)
                interior_right = min(x_hi, R)
                # If the interior overlap is tiny (just touching),
                # treat as not crossing.
                if interior_right - interior_left <= PIN_HIT_TOLERANCE:
                    return False
            return True

        if abs(x2 - x1) < 1e-9:        # vertical segment
            x = x1
            if x <= L or x >= R:
                return False
            y_lo, y_hi = min(y1, y2), max(y1, y2)
            if y_hi <= T or y_lo >= B:
                return False
            if allow_endpoints:
                interior_top = max(y_lo, T)
                interior_bot = min(y_hi, B)
                if interior_bot - interior_top <= PIN_HIT_TOLERANCE:
                    return False
            return True

        # Generic diagonal — treat as crossing if either endpoint is inside
        return (self.contains_point(x1, y1) or self.contains_point(x2, y2))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
@dataclass
class WireRouter:
    """Smart orthogonal router with obstacle + corner-collision awareness.

    Attributes
    ----------
    grid : float
        All routes are snapped to multiples of ``grid``. Matches the
        editor's default (20 px).
    obstacles : list[Obstacle]
        Routes try not to cross these. Add via
        :meth:`add_obstacles_from_components` for a typical use.
    used_corners : set[tuple[float, float]]
        Grid-snapped corner positions that any previous route has
        already used. New routes pick a different corner to avoid the
        union-find collision bug. Public so callers can pre-seed it
        with pin positions if they want EXTRA reserved coordinates.
    routed_segments : list[tuple[float, float, float, float]]
        All segments emitted so far — used to avoid colinear overlap
        between two wires (the OTHER common merge trigger).
    """

    grid: float = 20.0
    obstacles: list[Obstacle] = field(default_factory=list)
    used_corners: set[tuple[float, float]] = field(default_factory=set)
    routed_segments: list[tuple[float, float, float, float]] = field(
        default_factory=list,
    )

    # ----- setup helpers ------------------------------------------------
    def add_obstacle(self, obs: Obstacle) -> None:
        self.obstacles.append(obs)

    def add_obstacles_from_components(
        self,
        components: Iterable[dict],
        *,
        body_half_w: float = 30.0,
        body_half_h: float = 25.0,
        padding: float = 6.0,
    ) -> None:
        """Add an obstacle per component using its (x, y) centre and a
        default body half-extent. Pin positions are exempt — pins sit
        on the body edge and shouldn't be treated as forbidden.

        For tighter routing pass a smaller ``body_half_w/h``; for
        wider clearance bump ``padding``.
        """
        for comp in components:
            cx = float(comp.get("x", 0.0) or 0.0)
            cy = float(comp.get("y", 0.0) or 0.0)
            self.obstacles.append(Obstacle(
                x=cx - body_half_w,
                y=cy - body_half_h,
                width=2 * body_half_w,
                height=2 * body_half_h,
                padding=padding,
            ))

    # ----- routing API --------------------------------------------------
    def route(
        self,
        ax: float, ay: float,
        bx: float, by: float,
        *,
        prefer_h_first: bool = True,
    ) -> list[tuple[float, float, float, float]]:
        """Return a list of ``(x1, y1, x2, y2)`` orthogonal segments
        from ``(ax, ay)`` to ``(bx, by)``.

        Routing priority:
            1. Single straight line if collinear and unobstructed
            2. Two-segment L with corner = (bx, ay) or (ax, by),
               whichever doesn't collide with obstacles, other corners,
               or other wires' colinear segments
            3. Three-segment Z with a mid-x offset chosen from a
               deterministic candidate list until a clear one is found
            4. Same Z but with mid-y instead of mid-x
            5. Fall back to a single diagonal segment (topologically
               correct but visually ugly — only happens when the
               canvas is genuinely impassable)

        After each successful route the corners + segments are
        recorded so subsequent routes avoid them.
        """
        ax = self._snap(ax)
        ay = self._snap(ay)
        bx = self._snap(bx)
        by = self._snap(by)

        # --- straight line ---
        if abs(ax - bx) < PIN_HIT_TOLERANCE or abs(ay - by) < PIN_HIT_TOLERANCE:
            segs = [(ax, ay, bx, by)]
            if self._segments_clear(segs, anchor_endpoints={(ax, ay), (bx, by)}):
                self._record(segs)
                return segs

        # --- L-routing ---
        corner_candidates: list[tuple[float, float]] = []
        if prefer_h_first:
            corner_candidates.append((bx, ay))
            corner_candidates.append((ax, by))
        else:
            corner_candidates.append((ax, by))
            corner_candidates.append((bx, ay))

        for cx, cy in corner_candidates:
            if self._corner_in_use(cx, cy):
                continue
            segs = self._l_segments(ax, ay, cx, cy, bx, by)
            if self._segments_clear(segs, anchor_endpoints={(ax, ay), (bx, by)}):
                self._record(segs, corners=[(cx, cy)])
                return segs

        # --- Z-routing with mid_x ---
        for mid_x in self._candidate_mid_axes(ax, bx):
            c1 = (mid_x, ay)
            c2 = (mid_x, by)
            if self._corner_in_use(*c1) or self._corner_in_use(*c2):
                continue
            segs = [
                (ax, ay, mid_x, ay),
                (mid_x, ay, mid_x, by),
                (mid_x, by, bx, by),
            ]
            if self._segments_clear(segs, anchor_endpoints={(ax, ay), (bx, by)}):
                self._record(segs, corners=[c1, c2])
                return segs

        # --- Z-routing with mid_y ---
        for mid_y in self._candidate_mid_axes(ay, by):
            c1 = (ax, mid_y)
            c2 = (bx, mid_y)
            if self._corner_in_use(*c1) or self._corner_in_use(*c2):
                continue
            segs = [
                (ax, ay, ax, mid_y),
                (ax, mid_y, bx, mid_y),
                (bx, mid_y, bx, by),
            ]
            if self._segments_clear(segs, anchor_endpoints={(ax, ay), (bx, by)}):
                self._record(segs, corners=[c1, c2])
                return segs

        # --- last resort: single diagonal (correct but ugly) ---
        segs = [(ax, ay, bx, by)]
        self._record(segs)
        return segs

    # ----- internal helpers --------------------------------------------
    def _snap(self, v: float) -> float:
        return round(v / self.grid) * self.grid

    def _corner_in_use(self, cx: float, cy: float) -> bool:
        """True if any previously-used corner is within tolerance of
        (cx, cy). Coincident corners are what triggers the union-find
        merge bug — we never want two wires sharing a corner unless
        they share a pin (handled outside this check)."""
        for ux, uy in self.used_corners:
            if (abs(ux - cx) < PIN_HIT_TOLERANCE
                    and abs(uy - cy) < PIN_HIT_TOLERANCE):
                return True
        return False

    def _l_segments(self, ax, ay, cx, cy, bx, by):
        segs = []
        if abs(ax - cx) > PIN_HIT_TOLERANCE or abs(ay - cy) > PIN_HIT_TOLERANCE:
            segs.append((ax, ay, cx, cy))
        if abs(cx - bx) > PIN_HIT_TOLERANCE or abs(cy - by) > PIN_HIT_TOLERANCE:
            segs.append((cx, cy, bx, by))
        return segs

    def _candidate_mid_axes(self, a: float, b: float):
        """Yield grid-aligned candidate mid coordinates that aren't
        equal to either endpoint. Order: midpoint first, then ±1, ±2
        grid steps."""
        mid = self._snap((a + b) / 2.0)
        seen = {mid, self._snap(a), self._snap(b)}
        yield mid
        for delta in range(1, 8):
            for sign in (1, -1):
                cand = mid + sign * delta * self.grid
                if cand in seen:
                    continue
                seen.add(cand)
                yield cand

    def _segments_clear(self,
                          segs: list[tuple[float, float, float, float]],
                          *,
                          anchor_endpoints: set[tuple[float, float]]
                          ) -> bool:
        """True iff every segment in ``segs`` clears all obstacles AND
        doesn't colinearly overlap any previously-routed segment at a
        non-endpoint coordinate.

        ``anchor_endpoints`` are the legitimate pin positions of the
        wire being routed; endpoints there are allowed to touch other
        wires (intentional fan-out at a shared pin).
        """
        for x1, y1, x2, y2 in segs:
            for obs in self.obstacles:
                if obs.segment_crosses(x1, y1, x2, y2,
                                         allow_endpoints=True):
                    return False
            # Check for colinear overlap with previously-routed segs
            for (px1, py1, px2, py2) in self.routed_segments:
                if self._colinear_overlap(x1, y1, x2, y2,
                                            px1, py1, px2, py2,
                                            anchor_endpoints):
                    return False
        return True

    @staticmethod
    def _colinear_overlap(
        x1, y1, x2, y2,
        px1, py1, px2, py2,
        anchor_endpoints: set[tuple[float, float]],
    ) -> bool:
        """True iff two segments are colinear AND overlap at a region
        of length > PIN_HIT_TOLERANCE that ISN'T just a shared
        endpoint at one of the anchor pin positions."""
        # Both horizontal at same Y?
        if abs(y1 - y2) < PIN_HIT_TOLERANCE and abs(py1 - py2) < PIN_HIT_TOLERANCE \
                and abs(y1 - py1) < PIN_HIT_TOLERANCE:
            a_lo, a_hi = sorted((x1, x2))
            b_lo, b_hi = sorted((px1, px2))
            overlap = min(a_hi, b_hi) - max(a_lo, b_lo)
            if overlap > PIN_HIT_TOLERANCE:
                # Allow if the overlap is anchored at a legitimate pin
                lo = max(a_lo, b_lo)
                hi = min(a_hi, b_hi)
                for ax, ay in anchor_endpoints:
                    if (abs(ay - y1) < PIN_HIT_TOLERANCE
                            and lo - PIN_HIT_TOLERANCE <= ax <= hi + PIN_HIT_TOLERANCE):
                        # The overlap zone touches a pin — that's a
                        # legitimate fan-out, not a corner collision.
                        # But if the overlap EXTENDS beyond the pin
                        # in both directions, that's still a problem.
                        if (lo + PIN_HIT_TOLERANCE < ax < hi - PIN_HIT_TOLERANCE
                                or abs(overlap - 0) > 8 * PIN_HIT_TOLERANCE):
                            return True
                        return False
                return True
        # Both vertical at same X?
        if abs(x1 - x2) < PIN_HIT_TOLERANCE and abs(px1 - px2) < PIN_HIT_TOLERANCE \
                and abs(x1 - px1) < PIN_HIT_TOLERANCE:
            a_lo, a_hi = sorted((y1, y2))
            b_lo, b_hi = sorted((py1, py2))
            overlap = min(a_hi, b_hi) - max(a_lo, b_lo)
            if overlap > PIN_HIT_TOLERANCE:
                lo = max(a_lo, b_lo)
                hi = min(a_hi, b_hi)
                for ax, ay in anchor_endpoints:
                    if (abs(ax - x1) < PIN_HIT_TOLERANCE
                            and lo - PIN_HIT_TOLERANCE <= ay <= hi + PIN_HIT_TOLERANCE):
                        if (lo + PIN_HIT_TOLERANCE < ay < hi - PIN_HIT_TOLERANCE
                                or abs(overlap - 0) > 8 * PIN_HIT_TOLERANCE):
                            return True
                        return False
                return True
        return False

    def _record(self,
                  segs: list[tuple[float, float, float, float]],
                  *,
                  corners: list[tuple[float, float]] | None = None) -> None:
        """Save the segments + their corners so future routes can
        avoid colliding with them."""
        for seg in segs:
            self.routed_segments.append(seg)
        for c in (corners or []):
            self.used_corners.add((self._snap(c[0]), self._snap(c[1])))
