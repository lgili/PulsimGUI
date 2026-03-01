"""Netlist and connectivity helpers."""

from typing import TYPE_CHECKING

from pulsimgui.models.component import ComponentType

if TYPE_CHECKING:  # pragma: no cover
    from pulsimgui.models.circuit import Circuit


PIN_HIT_TOLERANCE = 5.0


def build_node_map(circuit: "Circuit") -> dict[tuple[str, int], str]:
    """Build a connectivity map for component pins.

    Returns a mapping of ``(component_id, pin_index)`` to the string node name.
    Ground pins are mapped to node ``"0"`` for compatibility with SPICE.
    """

    node_map: dict[tuple[str, int], str] = {}
    node_counter = 1

    # Handle ground references first so dependent pins share node 0
    for comp in circuit.components.values():
        if comp.type != ComponentType.GROUND:
            continue
        gnd_pos = comp.get_pin_position(0)
        for other in circuit.components.values():
            if other.id == comp.id:
                continue
            for pin_idx, _pin in enumerate(other.pins):
                pin_pos = other.get_pin_position(pin_idx)
                if abs(pin_pos[0] - gnd_pos[0]) < 5 and abs(pin_pos[1] - gnd_pos[1]) < 5:
                    node_map[(str(other.id), pin_idx)] = "0"

    # Group component pins by geometric wire connections
    for wire in circuit.wires.values():
        if not wire.segments:
            continue
        connected_pins: set[tuple[str, int]] = set()
        for seg in wire.segments:
            for pos in ((seg.x1, seg.y1), (seg.x2, seg.y2)):
                for comp in circuit.components.values():
                    for pin_idx, _pin in enumerate(comp.pins):
                        pin_pos = comp.get_pin_position(pin_idx)
                        if abs(pin_pos[0] - pos[0]) < 5 and abs(pin_pos[1] - pos[1]) < 5:
                            connected_pins.add((str(comp.id), pin_idx))
        if not connected_pins:
            continue

        existing = None
        for key in connected_pins:
            if key in node_map:
                existing = node_map[key]
                break

        if existing is None:
            existing = str(node_counter)
            node_counter += 1

        for key in connected_pins:
            node_map[key] = existing

    # Assign unique nodes to any dangling pins
    for comp in circuit.components.values():
        for pin_idx, _pin in enumerate(comp.pins):
            key = (str(comp.id), pin_idx)
            if key not in node_map:
                node_map[key] = str(node_counter)
                node_counter += 1

    return node_map


def build_node_alias_map(
    circuit: "Circuit",
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
    circuit: "Circuit",
    wire,
    node_map: dict[tuple[str, int], str],
) -> set[str]:
    """Return all node identifiers touched by the given wire."""

    nodes: set[str] = set()
    endpoints: list[tuple[float, float]] = []
    for segment in wire.segments:
        endpoints.append((segment.x1, segment.y1))
        endpoints.append((segment.x2, segment.y2))

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
