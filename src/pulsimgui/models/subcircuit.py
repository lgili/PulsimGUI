"""Subcircuit model for hierarchical schematics."""

from dataclasses import dataclass, field
from typing import Any
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
