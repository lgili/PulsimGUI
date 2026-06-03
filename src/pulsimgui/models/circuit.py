"""Circuit model containing components and wires."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID

from pulsimgui.models.component import Component
from pulsimgui.models.wire import Wire

# Tolerance (px) for matching a component terminal to a wire endpoint when
# healing double-rotated components. Sized to absorb the historical 5px
# pin/grid offset without admitting unrelated wires.
_HEAL_WIRE_TOL = 6.0


def _heal_double_rotated_components(circuit: "Circuit") -> int:
    """Repair components whose 90°/270° rotation was double-applied.

    A latent authoring bug (seen in some builder-generated files) stored a
    component's pins *already rotated* while ALSO setting ``rotation`` to the
    same quarter-turn. The symbol body is drawn on its canonical axis and then
    rotated by the view transform, so the leads to the pre-rotated pins come
    out diagonal ("deformed"); worse, :meth:`Component.get_pin_position`
    rotates the pins a *second* time, landing the computed terminals 90° away
    from the wires (the parts only simulate because connectivity is by
    node-map, not geometry).

    The wires are the ground truth for the *intended* orientation, so a
    component is healed only when (a) its terminals currently miss every wire
    endpoint and (b) un-rotating its stored pins by ``rotation`` makes ALL of
    them land on wire endpoints. That strict, evidence-based test never
    touches a legitimately-rotated part (whose pins already meet their wires)
    and is idempotent (a healed circuit re-loads as a no-op).

    Returns the number of components repaired.
    """
    if not circuit.components or not circuit.wires:
        return 0

    wire_pts: list[tuple[float, float]] = []
    for wire in circuit.wires.values():
        for endpoint in (wire.start_point, wire.end_point):
            if endpoint is not None:
                wire_pts.append((float(endpoint[0]), float(endpoint[1])))
    if not wire_pts:
        return 0

    def on_wire(point: tuple[float, float]) -> bool:
        px, py = point
        return any(
            abs(px - wx) <= _HEAL_WIRE_TOL and abs(py - wy) <= _HEAL_WIRE_TOL
            for wx, wy in wire_pts
        )

    def unrotate(x: float, y: float, steps: int) -> tuple[float, float]:
        # Inverse of get_pin_position's per-step rotation (px, py) -> (-py, px).
        for _ in range(steps % 4):
            x, y = y, -x
        return x, y

    healed = 0
    for comp in circuit.components.values():
        steps = (int(getattr(comp, "rotation", 0) or 0) // 90) % 4
        if steps not in (1, 3):  # only odd quarter-turns flip the pin axis
            continue
        pins = getattr(comp, "pins", None) or []
        if len(pins) < 2:
            continue
        n = len(pins)
        cur_match = sum(1 for i in range(n) if on_wire(comp.get_pin_position(i)))
        if cur_match == n:
            continue  # already connected — never touch a healthy part

        original = [(p.x, p.y) for p in pins]
        for p in pins:
            p.x, p.y = unrotate(p.x, p.y, steps)
        fix_match = sum(1 for i in range(n) if on_wire(comp.get_pin_position(i)))
        if fix_match == n and fix_match > cur_match:
            healed += 1  # un-rotation fully reconnects -> keep the repair
        else:
            for p, (x, y) in zip(pins, original):
                p.x, p.y = x, y  # not a double rotation -> revert
    return healed


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
            # SUBCIRCUIT components are SubcircuitInstance subclasses
            # with an extra ``subcircuit_id`` field; route them through
            # the right deserializer so that field survives the round
            # trip. Without this special case, a saved subcircuit
            # would lose its definition pointer and double-click
            # navigation would dead-end at "Missing subcircuit".
            ctype = str(comp_data.get("type", "")).upper()
            if ctype == "SUBCIRCUIT":
                from pulsimgui.models.subcircuit import SubcircuitInstance
                comp = SubcircuitInstance.from_dict(comp_data)
            else:
                comp = Component.from_dict(comp_data)
            circuit.components[comp.id] = comp
        for wire_data in data.get("wires", []):
            wire = Wire.from_dict(wire_data)
            circuit.wires[wire.id] = wire
        # Self-heal a latent authoring bug: components saved with their pins
        # already rotated AND a non-zero ``rotation`` (a double rotation) render
        # deformed and geometrically disconnected. Repair them using the wires
        # as ground truth. No-op for well-formed circuits.
        _heal_double_rotated_components(circuit)
        return circuit
