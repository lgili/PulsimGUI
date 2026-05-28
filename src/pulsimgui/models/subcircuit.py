"""Subcircuit model for hierarchical schematics."""

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType, Pin
from pulsimgui.utils.net_utils import build_node_map


@dataclass
class BoundaryPortCandidate:
    """Candidate describing a potential subcircuit port."""

    name: str
    node_name: str
    anchor_point: tuple[float, float]
    internal_refs: list[tuple[UUID, int]]


@dataclass
class SubcircuitPort:
    """A port that exposes an internal node to the parent circuit."""

    id: UUID = field(default_factory=uuid4)
    name: str = ""
    internal_node: str = ""  # Name of the internal net
    pin_index: int = 0  # Index in the subcircuit symbol
    x: float = 0.0  # Position on subcircuit boundary (relative)
    y: float = 0.0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "internal_node": self.internal_node,
            "pin_index": self.pin_index,
            "x": self.x,
            "y": self.y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubcircuitPort":
        """Deserialize from dictionary."""
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            internal_node=data.get("internal_node", ""),
            pin_index=data.get("pin_index", 0),
            x=data.get("x", 0.0),
            y=data.get("y", 0.0),
        )


@dataclass
class SubcircuitDefinition:
    """Definition of a reusable subcircuit (the "template")."""

    id: UUID = field(default_factory=uuid4)
    name: str = "Subcircuit"
    description: str = ""
    circuit: Circuit = field(default_factory=Circuit)
    ports: list[SubcircuitPort] = field(default_factory=list)
    symbol_width: float = 80.0
    symbol_height: float = 60.0

    def __post_init__(self):
        """Initialize circuit if not provided."""
        if self.circuit is None:
            self.circuit = Circuit(name=self.name)

    def get_pins(self) -> list[Pin]:
        """Generate pin list from ports for use in component instance."""
        pins = []
        for port in self.ports:
            pins.append(Pin(
                index=port.pin_index,
                name=port.name,
                x=port.x,
                y=port.y,
            ))
        return pins

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "circuit": self.circuit.to_dict(),
            "ports": [p.to_dict() for p in self.ports],
            "symbol_width": self.symbol_width,
            "symbol_height": self.symbol_height,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SubcircuitDefinition":
        """Deserialize from dictionary."""
        circuit = Circuit.from_dict(data.get("circuit", {}))
        ports = [SubcircuitPort.from_dict(p) for p in data.get("ports", [])]

        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            description=data.get("description", ""),
            circuit=circuit,
            ports=ports,
            symbol_width=data.get("symbol_width", 80.0),
            symbol_height=data.get("symbol_height", 60.0),
        )


@dataclass
class SubcircuitInstance(Component):
    """An instance of a subcircuit placed in a schematic.

    This extends Component to add subcircuit-specific data.
    """

    subcircuit_id: UUID | None = None  # Reference to SubcircuitDefinition

    def __post_init__(self):
        """Set component type to SUBCIRCUIT."""
        self.type = ComponentType.SUBCIRCUIT
        # Don't call super().__post_init__ as we handle pins differently

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        data = super().to_dict()
        data["subcircuit_id"] = str(self.subcircuit_id) if self.subcircuit_id else None
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "SubcircuitInstance":
        """Deserialize from dictionary."""
        instance = cls(
            id=UUID(data["id"]),
            type=ComponentType.SUBCIRCUIT,
            name=data["name"],
            x=data["x"],
            y=data["y"],
            rotation=data.get("rotation", 0),
            mirrored_h=data.get("mirrored_h", False),
            mirrored_v=data.get("mirrored_v", False),
            parameters=data.get("parameters", {}),
            pins=[Pin.from_dict(p) for p in data.get("pins", [])],
            subcircuit_id=UUID(data["subcircuit_id"]) if data.get("subcircuit_id") else None,
        )
        return instance


def create_subcircuit_from_selection(
    circuit: Circuit,
    selected_component_ids: list[UUID],
    selected_wire_ids: list[UUID],
    name: str = "Subcircuit",
    description: str = "",
    symbol_size: tuple[float, float] | None = None,
    boundary_ports: list[BoundaryPortCandidate] | None = None,
) -> tuple[SubcircuitDefinition, list[SubcircuitPort], tuple[float, float]]:
    """Create a subcircuit definition from selected components and wires.

    This analyzes the selection to:
    1. Extract the selected components and wires
    2. Identify boundary connections (wires that connect to non-selected components)
    3. Create ports for each boundary connection

    Args:
        circuit: The source circuit
        selected_component_ids: IDs of selected components
        selected_wire_ids: IDs of selected wires
        name: Name for the new subcircuit

    Returns:
        Tuple of (definition, ports, (center_x, center_y))
    """
    from copy import deepcopy

    # Create new circuit for subcircuit content
    subcircuit = Circuit(name=name)

    # Copy selected components
    component_map: dict[UUID, Component] = {}
    min_x, min_y = float("inf"), float("inf")
    max_x, max_y = float("-inf"), float("-inf")

    for comp_id in selected_component_ids:
        original = circuit.get_component(comp_id)
        if original:
            # Deep copy the component
            copied = deepcopy(original)
            component_map[comp_id] = copied
            subcircuit.components[copied.id] = copied

            # Track bounds for centering
            min_x = min(min_x, copied.x)
            min_y = min(min_y, copied.y)
            max_x = max(max_x, copied.x)
            max_y = max(max_y, copied.y)

    if not component_map:
        raise ValueError("At least one component is required to create a subcircuit")

    # Center the components
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    for comp in subcircuit.components.values():
        comp.x -= center_x
        comp.y -= center_y

    # Copy selected wires
    for wire_id in selected_wire_ids:
        original = circuit.get_wire(wire_id)
        if original:
            copied = deepcopy(original)
            # Offset wire segments
            if component_map:
                for seg in copied.segments:
                    seg.x1 -= center_x
                    seg.y1 -= center_y
                    seg.x2 -= center_x
                    seg.y2 -= center_y
            subcircuit.wires[copied.id] = copied

    # Identify boundary connections (ports)
    ports: list[SubcircuitPort] = []
    ports_to_use = boundary_ports or detect_boundary_ports(circuit, selected_component_ids)

    # Calculate subcircuit symbol size based on content
    width = max(80.0, (max_x - min_x) * 0.3 + 40)
    height = max(60.0, (max_y - min_y) * 0.3 + 40)

    if symbol_size:
        width = max(width, float(symbol_size[0]))
        height = max(height, float(symbol_size[1]))

    for index, candidate in enumerate(ports_to_use):
        rel_x = candidate.anchor_point[0] - center_x
        rel_y = candidate.anchor_point[1] - center_y
        ports.append(
            SubcircuitPort(
                name=candidate.name,
                internal_node=candidate.node_name,
                pin_index=index,
                x=rel_x,
                y=rel_y,
            )
        )

    # Create the definition
    definition = SubcircuitDefinition(
        name=name,
        description=description,
        circuit=subcircuit,
        ports=ports,
        symbol_width=width,
        symbol_height=height,
    )

    return definition, ports, (center_x, center_y)


def detect_boundary_ports(
    circuit: Circuit,
    selected_component_ids: list[UUID],
) -> list[BoundaryPortCandidate]:
    """Detect boundary ports for a selection using node connectivity."""

    selected = set(selected_component_ids)
    node_map = build_node_map(circuit)
    node_connections: dict[str, list[tuple[UUID, int]]] = {}

    for (comp_id_str, pin_index), node_name in node_map.items():
        comp_uuid = UUID(comp_id_str)
        node_connections.setdefault(node_name, []).append((comp_uuid, pin_index))

    candidates: list[BoundaryPortCandidate] = []
    used_names: dict[str, int] = {}

    for node_name, refs in node_connections.items():
        inside = [ref for ref in refs if ref[0] in selected]
        outside = [ref for ref in refs if ref[0] not in selected]
        if not inside or not outside:
            continue

        anchor_point = _average_pin_position(circuit, inside)
        label = _derive_port_label(circuit, outside, node_name)
        count = used_names.get(label, 0)
        if count:
            label = f"{label}_{count + 1}"
        used_names[label] = count + 1

        candidates.append(
            BoundaryPortCandidate(
                name=label,
                node_name=node_name,
                anchor_point=anchor_point,
                internal_refs=inside,
            )
        )

    return candidates


def _average_pin_position(
    circuit: Circuit,
    refs: list[tuple[UUID, int]],
) -> tuple[float, float]:
    """Compute the average location for a set of component pins."""

    if not refs:
        return 0.0, 0.0

    total_x = 0.0
    total_y = 0.0
    for comp_id, pin_index in refs:
        comp = circuit.get_component(comp_id)
        if not comp:
            continue
        pin_pos = comp.get_pin_position(pin_index)
        total_x += pin_pos[0]
        total_y += pin_pos[1]

    count = len(refs)
    return total_x / count, total_y / count


def _derive_port_label(
    circuit: Circuit,
    refs: list[tuple[UUID, int]],
    fallback: str,
) -> str:
    """Derive a readable label for a boundary port."""

    if refs:
        comp = circuit.get_component(refs[0][0])
        if comp:
            pin_name = comp.pins[refs[0][1]].name if comp.pins else str(refs[0][1])
            return f"{comp.name}.{pin_name}"
    return f"NET_{fallback}"


def sync_definition_ports_from_markers(
    definition: "SubcircuitDefinition",
) -> bool:
    """Rebuild ``definition.ports`` from SUBCIRCUIT_PORT marker
    components placed inside ``definition.circuit``.

    Each marker contributes one port whose:
      * ``name``           = marker.parameters["port_name"]
      * ``internal_node``  = net name at the marker's pin (via union-find)
      * ``pin_index``      = stable index assigned per side, in
                              creation order
      * ``(x, y)``         = position on the outer symbol's rectangle,
                              distributed along the matching side

    Markers are the new (preferred) source of truth for subcircuit
    boundary connections. Definitions created via the older
    ``create_subcircuit_from_selection`` path keep working because
    we only overwrite ``definition.ports`` when at least one marker
    is found — definitions without markers fall through untouched
    (their pre-existing ``internal_node`` strings remain authoritative).

    Returns True if ``definition.ports`` actually changed.
    """
    from pulsimgui.models.component import ComponentType  # avoid cycles

    inner = definition.circuit
    markers: list[Component] = [
        c for c in inner.components.values()
        if c.type == ComponentType.SUBCIRCUIT_PORT
    ]
    if not markers:
        # No markers — preserve existing ports list as-is. Callers
        # that need a fresh layout from a different mechanism (e.g.
        # detect_boundary_ports) must do that themselves.
        return False

    # Look up the net each marker pin sits on. ``build_node_map`` is
    # keyed by (str(component.id), pin_index).
    node_map = build_node_map(inner)

    # Group markers by side so we can lay them out along the outer
    # rectangle independently per edge.
    by_side: dict[str, list[Component]] = {"left": [], "right": [], "top": [], "bottom": []}
    for marker in markers:
        side = str(marker.parameters.get("side", "left")).lower()
        if side not in by_side:
            side = "left"
        by_side[side].append(marker)

    # Stable ordering per side: alphabetical by port_name keeps the
    # outer symbol layout predictable across edits.
    for side in by_side:
        by_side[side].sort(key=lambda m: str(m.parameters.get("port_name", "")))

    width = definition.symbol_width
    height = definition.symbol_height
    half_w = width / 2.0
    half_h = height / 2.0

    new_ports: list[SubcircuitPort] = []
    pin_index = 0
    used_names: dict[str, int] = {}

    def _distribute(n: int, axis_len: float) -> list[float]:
        # Evenly space n pins along a length, leaving margins at the
        # ends so they don't crowd the corners.
        if n <= 0:
            return []
        if n == 1:
            return [0.0]
        margin = axis_len * 0.18
        usable = axis_len - 2 * margin
        step = usable / (n - 1)
        return [(-axis_len / 2 + margin + i * step) for i in range(n)]

    for side, ms in by_side.items():
        if not ms:
            continue
        if side in ("left", "right"):
            ys = _distribute(len(ms), height)
            x = -half_w if side == "left" else +half_w
            for marker, y in zip(ms, ys):
                name = str(marker.parameters.get("port_name", "")).strip() or "port"
                # De-dup names so two markers with the same label
                # don't collide silently.
                count = used_names.get(name, 0)
                used = name if count == 0 else f"{name}_{count + 1}"
                used_names[name] = count + 1
                internal = node_map.get((str(marker.id), 0), "")
                new_ports.append(SubcircuitPort(
                    name=used,
                    internal_node=internal,
                    pin_index=pin_index,
                    x=x, y=y,
                ))
                pin_index += 1
        else:
            xs = _distribute(len(ms), width)
            y = -half_h if side == "top" else +half_h
            for marker, x in zip(ms, xs):
                name = str(marker.parameters.get("port_name", "")).strip() or "port"
                count = used_names.get(name, 0)
                used = name if count == 0 else f"{name}_{count + 1}"
                used_names[name] = count + 1
                internal = node_map.get((str(marker.id), 0), "")
                new_ports.append(SubcircuitPort(
                    name=used,
                    internal_node=internal,
                    pin_index=pin_index,
                    x=x, y=y,
                ))
                pin_index += 1

    # Compare against previous list — only signal a change if
    # something actually moved/renamed.
    def _signature(ports: list[SubcircuitPort]) -> list[tuple]:
        return [(p.name, p.internal_node, p.pin_index,
                 round(p.x, 2), round(p.y, 2)) for p in ports]

    if _signature(definition.ports) == _signature(new_ports):
        return False

    definition.ports = new_ports
    return True


def refresh_subcircuit_instance_pins(
    project,
    definition: "SubcircuitDefinition",
) -> int:
    """After a definition's ports change, propagate the new pin layout
    to every ``SubcircuitInstance`` in the project that points to it.

    Returns the number of instances that were updated. Callers should
    refresh the schematic scene afterward so the new pins render.
    """
    target_id = definition.id
    new_pins = definition.get_pins()
    touched = 0
    for circuit in getattr(project, "circuits", {}).values():
        for comp in circuit.components.values():
            if (
                getattr(comp, "type", None) is not None
                and comp.type.name == "SUBCIRCUIT"
                and getattr(comp, "subcircuit_id", None) == target_id
            ):
                comp.pins = [
                    Pin(p.index, p.name, p.x, p.y) for p in new_pins
                ]
                touched += 1
    return touched
