"""Automatic component placement for the schematic (Auto-Layout).

The one feature-level gap left from the Pulsim Studio redesign: the
"organize my components" button. ``compute_auto_layout`` produces a
clean left-to-right layered arrangement of the circuit:

* **Connectivity graph** from the wires' explicit pin connections
  (the same metadata ``build_node_map`` trusts) — two components are
  adjacent when a wire ties their pins together.
* **Layering (columns)**: breadth-first from the circuit's sources
  (voltage/current sources, batteries, PV panels, PWM generators…) so
  energy flows left → right the way an engineer draws it. BFS depth is
  used instead of longest-path because power circuits are cyclic —
  BFS is robust to loops and deterministic.
* **Row ordering** inside each column by the barycenter of already
  placed neighbours (classic Sugiyama step) — keeps connected
  components vertically near each other and reduces wire crossings.
* **Grounds** are pulled out of the flow and parked directly below
  their (single) connected neighbour, mirroring hand-drawn practice.
* Disconnected islands stack below the main block, each laid out with
  the same rules.

Everything snaps to the schematic grid, and the result is a pure
``{component_id: (x, y)}`` mapping — application and undo live in
:class:`~pulsimgui.commands.layout_commands.AutoLayoutCommand`.

Deliberately NOT here: component rotation and any wire geometry —
rotation is the user's intent to preserve, and wires are re-routed by
the existing orthogonal router right after placement.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.models.circuit import Circuit

# Spacing in scene pixels. Generous enough for the largest stock
# symbols (transformer / PMSM bodies ~60-80 px) plus label clearance.
COLUMN_SPACING = 240.0
ROW_SPACING = 160.0
MARGIN = 80.0
ISLAND_GAP = 160.0
GROUND_DROP = 100.0

# Component-type names treated as flow roots (energy enters here).
_SOURCE_HINTS = (
    "VOLTAGE_SOURCE",
    "CURRENT_SOURCE",
    "BATTERY",
    "PV_PANEL",
    "PWM_GENERATOR",
)


def _is_source(type_name: str) -> bool:
    return any(hint in type_name for hint in _SOURCE_HINTS)


def _is_ground(type_name: str) -> bool:
    return "GROUND" in type_name


def _snap(value: float, grid: float) -> float:
    if grid <= 0:
        return value
    return round(value / grid) * grid


def _adjacency(circuit: Circuit) -> dict[UUID, set[UUID]]:
    """Component adjacency from the wires' explicit pin connections."""
    adj: dict[UUID, set[UUID]] = defaultdict(set)
    for comp_id in circuit.components:
        adj[comp_id]  # ensure isolated components appear
    for wire in circuit.wires.values():
        start = getattr(wire, "start_connection", None)
        end = getattr(wire, "end_connection", None)
        if start is None or end is None:
            continue
        a, b = start.component_id, end.component_id
        if a == b:
            continue
        if a in circuit.components and b in circuit.components:
            adj[a].add(b)
            adj[b].add(a)
    return adj


def compute_auto_layout(
    circuit: Circuit,
    *,
    grid: float = 20.0,
) -> dict[UUID, tuple[float, float]]:
    """Return the new ``{component_id: (x, y)}`` placement.

    Components the algorithm can't reach (fully isolated, no wires)
    are stacked as their own island so nothing is lost off-screen.
    """
    components = circuit.components
    if not components:
        return {}

    adj = _adjacency(circuit)

    # Grounds are parked next to their neighbour afterwards; exclude
    # them from the flow graph so they don't consume a column.
    grounds = {
        cid for cid, comp in components.items()
        if _is_ground(getattr(comp.type, "name", ""))
    }
    flow_ids = [cid for cid in components if cid not in grounds]

    # Deterministic ordering everywhere: sort by component name.
    def _name(cid: UUID) -> str:
        return getattr(components[cid], "name", "") or str(cid)

    flow_ids.sort(key=_name)

    # ── Islands (connected groups over the non-ground graph) ─────────
    unvisited = set(flow_ids)
    islands: list[list[UUID]] = []
    while unvisited:
        seed = min(unvisited, key=_name)
        group: list[UUID] = []
        queue = deque([seed])
        unvisited.discard(seed)
        while queue:
            cid = queue.popleft()
            group.append(cid)
            for nb in adj[cid]:
                if nb in unvisited:
                    unvisited.discard(nb)
                    queue.append(nb)
        islands.append(group)

    positions: dict[UUID, tuple[float, float]] = {}
    island_top = MARGIN

    for group in islands:
        group_set = set(group)

        # ── Layer assignment: BFS depth from the island's sources ────
        roots = sorted(
            (
                cid for cid in group
                if _is_source(getattr(components[cid].type, "name", ""))
            ),
            key=_name,
        ) or [min(group, key=_name)]

        depth: dict[UUID, int] = {}
        queue = deque((r, 0) for r in roots)
        for r in roots:
            depth[r] = 0
        while queue:
            cid, d = queue.popleft()
            for nb in adj[cid]:
                if nb in group_set and nb not in depth:
                    depth[nb] = d + 1
                    queue.append((nb, d + 1))

        columns: dict[int, list[UUID]] = defaultdict(list)
        for cid in group:
            columns[depth.get(cid, 0)].append(cid)

        # ── Row ordering by neighbour barycenter, column by column ───
        row_of: dict[UUID, int] = {}
        max_rows = 0

        def _barycenter(cid: UUID, *, rows: dict[UUID, int] = row_of) -> float:
            # Default-bound (B023): the dict is created fresh per island
            # and MUTATED (never rebound), so binding at def time is the
            # correct capture.
            placed = [rows[nb] for nb in adj[cid] if nb in rows]
            return sum(placed) / len(placed) if placed else 0.0

        for col in sorted(columns):
            members = columns[col]
            members.sort(key=lambda cid: (_barycenter(cid), _name(cid)))
            for row, cid in enumerate(members):
                row_of[cid] = row
            max_rows = max(max_rows, len(members))

        for cid in group:
            x = MARGIN + depth.get(cid, 0) * COLUMN_SPACING
            y = island_top + row_of[cid] * ROW_SPACING
            positions[cid] = (_snap(x, grid), _snap(y, grid))

        island_top += max_rows * ROW_SPACING + ISLAND_GAP

    # ── Grounds: directly below their first placed neighbour ─────────
    ground_load: dict[UUID, int] = defaultdict(int)
    for gid in sorted(grounds, key=_name):
        anchor = next(
            (nb for nb in sorted(adj[gid], key=_name) if nb in positions),
            None,
        )
        if anchor is None:
            positions[gid] = (
                _snap(MARGIN, grid),
                _snap(island_top, grid),
            )
            island_top += ROW_SPACING
            continue
        ax, ay = positions[anchor]
        # Park below-left of the anchor (half a column back) so the
        # ground never collides with the same column's next row;
        # several grounds on one anchor fan out further left.
        offset = (ground_load[anchor] + 1) * (grid * 3)
        ground_load[anchor] += 1
        positions[gid] = (
            _snap(ax - offset, grid),
            _snap(ay + GROUND_DROP, grid),
        )

    return positions
