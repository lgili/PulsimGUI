"""Netlist and connectivity helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    CONNECTION_DOMAIN_THERMAL,
    ComponentType,
    pin_connection_domain,
)

if TYPE_CHECKING:  # pragma: no cover
    from pulsimgui.models.circuit import Circuit
    from pulsimgui.models.wire import Wire, WireSegment


PIN_HIT_TOLERANCE = 5.0


class _UnionFind:
    """Disjoint-set helper for geometric net connectivity."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}
        self._rank: dict[str, int] = {}

    def add(self, item: str) -> None:
        if item in self._parent:
            return
        self._parent[item] = item
        self._rank[item] = 0

    def find(self, item: str) -> str:
        parent = self._parent[item]
        if parent != item:
            self._parent[item] = self.find(parent)
        return self._parent[item]

    def union(self, left: str, right: str) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return

        rank_left = self._rank[root_left]
        rank_right = self._rank[root_right]
        if rank_left < rank_right:
            self._parent[root_left] = root_right
        elif rank_left > rank_right:
            self._parent[root_right] = root_left
        else:
            self._parent[root_right] = root_left
            self._rank[root_left] += 1


def build_node_map(circuit: Circuit) -> dict[tuple[str, int], str]:
    """Build a connectivity map for component pins.

    Returns a mapping of ``(component_id, pin_index)`` to the string node name.
    Ground-connected nets are mapped to node ``"0"`` for SPICE compatibility.
    """

    uf = _UnionFind()
    point_positions: dict[str, tuple[float, float]] = {}
    point_domains: dict[str, str] = {}
    pin_refs: list[tuple[str, int, str]] = []
    ground_pin_refs: set[str] = set()

    # Register all component pins
    for comp in circuit.components.values():
        comp_id = str(comp.id)
        for pin_idx, _pin in enumerate(comp.pins):
            pin_ref = f"pin:{comp_id}:{pin_idx}"
            uf.add(pin_ref)
            point_positions[pin_ref] = comp.get_pin_position(pin_idx)
            point_domains[pin_ref] = pin_connection_domain(comp, pin_idx)
            pin_refs.append((comp_id, pin_idx, pin_ref))
            if comp.type == ComponentType.GROUND:
                ground_pin_refs.add(pin_ref)

    # Register wire endpoints/junctions and preserve explicit segment connectivity
    for wire in circuit.wires.values():
        _register_wire_points(
            wire,
            uf,
            point_positions,
            point_domains,
            _wire_domain(circuit, wire),
        )

    # Merge points that are geometrically coincident (within tolerance)
    _merge_nearby_points(point_positions, point_domains, uf)

    # Any net touching a ground component pin is forced to node "0"
    ground_roots = {uf.find(pin_ref) for pin_ref in ground_pin_refs}

    node_map: dict[tuple[str, int], str] = {}
    root_to_node: dict[str, str] = {}
    node_counter = 1

    for comp_id, pin_idx, pin_ref in pin_refs:
        root = uf.find(pin_ref)
        node_name = root_to_node.get(root)
        if node_name is None:
            if root in ground_roots:
                node_name = "0"
            else:
                node_name = str(node_counter)
                node_counter += 1
            root_to_node[root] = node_name
        node_map[(comp_id, pin_idx)] = node_name

    return node_map


def build_node_alias_map(
    circuit: Circuit,
    node_map: dict[tuple[str, int], str],
) -> dict[str, str]:
    """Map resolved node identifiers to user-visible aliases.

    Preference order per node:
        1. Explicit wire alias label
        2. Wire-assigned node_name (if present)
        3. Falls back to raw node identifier handled by caller
    """

    alias_map: dict[str, str] = {}
    for wire in circuit.wires.values():
        alias = (wire.alias or "").strip()
        fallback = (wire.node_name or "").strip()
        if not wire.segments:
            continue

        connected_nodes = _nodes_for_wire(circuit, wire, node_map)
        if not connected_nodes:
            continue

        for node_id in connected_nodes:
            if alias and node_id not in alias_map:
                alias_map[node_id] = alias
            elif fallback and node_id not in alias_map:
                alias_map[node_id] = fallback

    return alias_map


def _nodes_for_wire(
    circuit: Circuit,
    wire: Wire,
    node_map: dict[tuple[str, int], str],
) -> set[str]:
    """Return all node identifiers touched by the given wire."""

    nodes: set[str] = set()
    endpoints: list[tuple[float, float]] = []
    for segment in wire.segments:
        endpoints.append((segment.x1, segment.y1))
        endpoints.append((segment.x2, segment.y2))
    endpoints.extend(wire.junctions or [])

    if not endpoints:
        return nodes

    for component in circuit.components.values():
        comp_id = str(component.id)
        for pin_index, _pin in enumerate(component.pins):
            pin_pos = component.get_pin_position(pin_index)
            if _point_hits_any(pin_pos, endpoints):
                node_id = node_map.get((comp_id, pin_index))
                if node_id:
                    nodes.add(node_id)

    return nodes


def _point_hits_any(point: tuple[float, float], endpoints: list[tuple[float, float]]) -> bool:
    px, py = point
    for ex, ey in endpoints:
        if abs(px - ex) < PIN_HIT_TOLERANCE and abs(py - ey) < PIN_HIT_TOLERANCE:
            return True
    return False


def _register_wire_points(
    wire: Wire,
    uf: _UnionFind,
    point_positions: dict[str, tuple[float, float]],
    point_domains: dict[str, str],
    wire_domain: str,
) -> None:
    """Register wire points and explicit wire-internal connectivity."""

    # Segment endpoints are always connected by the segment itself.
    for seg_idx, seg in enumerate(wire.segments):
        start_ref = f"wire:{wire.id}:seg:{seg_idx}:start"
        end_ref = f"wire:{wire.id}:seg:{seg_idx}:end"
        uf.add(start_ref)
        uf.add(end_ref)
        point_positions[start_ref] = (seg.x1, seg.y1)
        point_positions[end_ref] = (seg.x2, seg.y2)
        point_domains[start_ref] = wire_domain
        point_domains[end_ref] = wire_domain
        uf.union(start_ref, end_ref)

    # Junctions are explicit connection points that may split crossing wires.
    for j_idx, (jx, jy) in enumerate(wire.junctions or []):
        j_ref = f"wire:{wire.id}:junction:{j_idx}"
        uf.add(j_ref)
        point_positions[j_ref] = (jx, jy)
        point_domains[j_ref] = wire_domain

        # If the junction lies on a segment, connect it to that segment net.
        for seg_idx, seg in enumerate(wire.segments):
            if _point_on_segment((jx, jy), seg):
                uf.union(j_ref, f"wire:{wire.id}:seg:{seg_idx}:start")
                uf.union(j_ref, f"wire:{wire.id}:seg:{seg_idx}:end")


def _merge_nearby_points(
    point_positions: dict[str, tuple[float, float]],
    point_domains: dict[str, str],
    uf: _UnionFind,
) -> None:
    """Merge points that are within PIN_HIT_TOLERANCE using a spatial hash."""

    if not point_positions:
        return

    bucket_size = PIN_HIT_TOLERANCE
    buckets: dict[tuple[int, int], list[tuple[str, float, float]]] = {}

    for point_ref, (px, py) in point_positions.items():
        key = _bucket_key(px, py, bucket_size)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbor_key = (key[0] + dx, key[1] + dy)
                for other_ref, ox, oy in buckets.get(neighbor_key, []):
                    if point_domains.get(point_ref) != point_domains.get(other_ref):
                        continue
                    if abs(px - ox) < PIN_HIT_TOLERANCE and abs(py - oy) < PIN_HIT_TOLERANCE:
                        uf.union(point_ref, other_ref)

        buckets.setdefault(key, []).append((point_ref, px, py))


def _bucket_key(x: float, y: float, bucket_size: float) -> tuple[int, int]:
    return int(round(x / bucket_size)), int(round(y / bucket_size))


def _point_on_segment(point: tuple[float, float], segment: WireSegment) -> bool:
    """Return True when a point lies on (or very near) a segment."""

    px, py = point
    x1, y1, x2, y2 = segment.x1, segment.y1, segment.x2, segment.y2

    if px < min(x1, x2) - PIN_HIT_TOLERANCE or px > max(x1, x2) + PIN_HIT_TOLERANCE:
        return False
    if py < min(y1, y2) - PIN_HIT_TOLERANCE or py > max(y1, y2) + PIN_HIT_TOLERANCE:
        return False

    dx = x2 - x1
    dy = y2 - y1
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return abs(px - x1) < PIN_HIT_TOLERANCE and abs(py - y1) < PIN_HIT_TOLERANCE

    # Distance from point to infinite line through segment.
    area = abs((px - x1) * dy - (py - y1) * dx)
    length = (dx**2 + dy**2) ** 0.5
    distance = area / length
    return distance < PIN_HIT_TOLERANCE


def _wire_domain(circuit: Circuit, wire: Wire) -> str:
    """Infer wire domain from endpoint pin metadata."""
    domains: set[str] = set()
    for connection in (wire.start_connection, wire.end_connection):
        if connection is None:
            continue
        component = circuit.components.get(connection.component_id)
        if component is None:
            continue
        pin_index = connection.pin_index
        if pin_index < 0 or pin_index >= len(component.pins):
            continue
        domains.add(pin_connection_domain(component, pin_index))

    # Backward compatibility: infer domain from geometric pin touches when
    # explicit endpoint metadata is missing (legacy projects/tests).
    if not domains:
        wire_points: list[tuple[float, float]] = []
        for segment in wire.segments:
            wire_points.append((segment.x1, segment.y1))
            wire_points.append((segment.x2, segment.y2))
        wire_points.extend(wire.junctions or [])

        for component in circuit.components.values():
            for pin_index in range(len(component.pins)):
                pin_x, pin_y = component.get_pin_position(pin_index)
                for point_x, point_y in wire_points:
                    if (
                        abs(pin_x - point_x) < PIN_HIT_TOLERANCE
                        and abs(pin_y - point_y) < PIN_HIT_TOLERANCE
                    ):
                        domains.add(pin_connection_domain(component, pin_index))
                        break

    if CONNECTION_DOMAIN_THERMAL in domains:
        return CONNECTION_DOMAIN_THERMAL
    if CONNECTION_DOMAIN_SIGNAL in domains:
        return CONNECTION_DOMAIN_SIGNAL
    return CONNECTION_DOMAIN_CIRCUIT
