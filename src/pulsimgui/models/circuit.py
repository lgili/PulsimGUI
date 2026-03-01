"""Circuit model containing components and wires."""

from dataclasses import dataclass, field
from typing import Iterator
from uuid import UUID

from pulsimgui.models.component import Component
from pulsimgui.models.wire import Wire


@dataclass
class Circuit:
    """A circuit schematic containing components and wires."""

    name: str = "untitled"
    components: dict[UUID, Component] = field(default_factory=dict)
    wires: dict[UUID, Wire] = field(default_factory=dict)
    _component_counter: dict[str, int] = field(default_factory=dict)

    def add_component(self, component: Component) -> None:
        """Add a component to the circuit."""
        if not component.name:
            component.name = self._generate_name(component.type.name)
        self.components[component.id] = component

    def remove_component(self, component_id: UUID) -> Component | None:
        """Remove a component from the circuit."""
        return self.components.pop(component_id, None)

    def get_component(self, component_id: UUID) -> Component | None:
        """Get a component by ID."""
        return self.components.get(component_id)

    def get_component_by_name(self, name: str) -> Component | None:
        """Get a component by name."""
        for comp in self.components.values():
            if comp.name == name:
                return comp
        return None

    def add_wire(self, wire: Wire) -> None:
        """Add a wire to the circuit."""
        self.wires[wire.id] = wire

    def remove_wire(self, wire_id: UUID) -> Wire | None:
        """Remove a wire from the circuit."""
        return self.wires.pop(wire_id, None)

    def get_wire(self, wire_id: UUID) -> Wire | None:
        """Get a wire by ID."""
        return self.wires.get(wire_id)

    def iter_components(self) -> Iterator[Component]:
        """Iterate over all components."""
        yield from self.components.values()

    def iter_wires(self) -> Iterator[Wire]:
        """Iterate over all wires."""
        yield from self.wires.values()

    def _generate_name(self, type_name: str) -> str:
        """Generate a unique component name like R1, R2, C1, etc."""
        prefix = type_name[0].upper()
        if prefix not in self._component_counter:
            self._component_counter[prefix] = 0
        self._component_counter[prefix] += 1
        return f"{prefix}{self._component_counter[prefix]}"

    def clear(self) -> None:
        """Clear all components and wires."""
        self.components.clear()
        self.wires.clear()
        self._component_counter.clear()

    def to_dict(self) -> dict:
        """Serialize circuit to dictionary."""
        return {
            "name": self.name,
            "components": [c.to_dict() for c in self.components.values()],
            "wires": [w.to_dict() for w in self.wires.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Circuit":
        """Deserialize circuit from dictionary."""
        circuit = cls(name=data.get("name", "untitled"))
        for comp_data in data.get("components", []):
            comp = Component.from_dict(comp_data)
            circuit.components[comp.id] = comp
        for wire_data in data.get("wires", []):
            wire = Wire.from_dict(wire_data)
            circuit.wires[wire.id] = wire
        return circuit
