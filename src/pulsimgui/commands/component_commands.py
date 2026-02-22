"""Commands for component operations."""

from copy import deepcopy
from uuid import UUID

from pulsimgui.commands.base import Command
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component
from pulsimgui.models.wire import Wire


class AddComponentCommand(Command):
    """Command to add a component to a circuit."""

    def __init__(self, circuit: Circuit, component: Component):
        self._circuit = circuit
        self._component = component

    def execute(self) -> None:
        """Add the component to the circuit."""
        self._circuit.add_component(self._component)

    def undo(self) -> None:
        """Remove the component from the circuit."""
        self._circuit.remove_component(self._component.id)

    @property
    def description(self) -> str:
        return f"Add {self._component.name}"


class DeleteComponentCommand(Command):
    """Command to delete a component from a circuit."""

    def __init__(self, circuit: Circuit, component_id: UUID):
        self._circuit = circuit
        self._component_id = component_id
        self._component: Component | None = None
        self._removed_wires: list[Wire] = []

    def execute(self) -> None:
        """Remove the component from the circuit."""
        self._removed_wires = []
        for wire in list(self._circuit.wires.values()):
            start_match = (
                wire.start_connection is not None
                and wire.start_connection.component_id == self._component_id
            )
            end_match = (
                wire.end_connection is not None
                and wire.end_connection.component_id == self._component_id
            )
            if start_match or end_match:
                removed = self._circuit.remove_wire(wire.id)
                if removed is not None:
                    self._removed_wires.append(removed)
        self._component = self._circuit.remove_component(self._component_id)

    def undo(self) -> None:
        """Restore the component to the circuit."""
        if self._component:
            self._circuit.add_component(self._component)
        for wire in self._removed_wires:
            self._circuit.add_wire(wire)

    @property
    def description(self) -> str:
        name = self._component.name if self._component else str(self._component_id)[:8]
        return f"Delete {name}"


class MoveComponentCommand(Command):
    """Command to move a component."""

    def __init__(
        self,
        circuit: Circuit,
        component_id: UUID,
        new_x: float,
        new_y: float,
        *,
        old_x: float | None = None,
        old_y: float | None = None,
        already_applied: bool = False,
    ):
        self._circuit = circuit
        self._component_id = component_id
        self._new_x = new_x
        self._new_y = new_y
        self._old_x: float = old_x if old_x is not None else 0.0
        self._old_y: float = old_y if old_y is not None else 0.0
        self._has_old_position = old_x is not None and old_y is not None
        self._already_applied = already_applied

    def execute(self) -> None:
        """Move the component to new position."""
        component = self._circuit.get_component(self._component_id)
        if component:
            if not self._has_old_position:
                self._old_x = component.x
                self._old_y = component.y
                self._has_old_position = True
            if self._already_applied:
                self._already_applied = False
                return
            component.x = self._new_x
            component.y = self._new_y

    def undo(self) -> None:
        """Restore the component to old position."""
        component = self._circuit.get_component(self._component_id)
        if component:
            component.x = self._old_x
            component.y = self._old_y

    @property
    def description(self) -> str:
        component = self._circuit.get_component(self._component_id)
        name = component.name if component else str(self._component_id)[:8]
        return f"Move {name}"

    def can_merge(self, other: Command) -> bool:
        """Allow merging consecutive moves of the same component."""
        if isinstance(other, MoveComponentCommand):
            return other._component_id == self._component_id
        return False

    def merge(self, other: Command) -> None:
        """Merge by updating to the newer position."""
        if isinstance(other, MoveComponentCommand):
            self._new_x = other._new_x
            self._new_y = other._new_y


class RotateComponentCommand(Command):
    """Command to rotate a component."""

    def __init__(self, circuit: Circuit, component_id: UUID, degrees: int = 90):
        self._circuit = circuit
        self._component_id = component_id
        self._degrees = degrees

    def execute(self) -> None:
        """Rotate the component."""
        component = self._circuit.get_component(self._component_id)
        if component:
            component.rotation = (component.rotation + self._degrees) % 360

    def undo(self) -> None:
        """Unrotate the component."""
        component = self._circuit.get_component(self._component_id)
        if component:
            component.rotation = (component.rotation - self._degrees) % 360

    @property
    def description(self) -> str:
        component = self._circuit.get_component(self._component_id)
        name = component.name if component else str(self._component_id)[:8]
        return f"Rotate {name}"


class FlipComponentCommand(Command):
    """Command to flip a component horizontally or vertically."""

    def __init__(self, circuit: Circuit, component_id: UUID, *, horizontal: bool = True):
        self._circuit = circuit
        self._component_id = component_id
        self._horizontal = horizontal

    def execute(self) -> None:
        """Flip the component."""
        component = self._circuit.get_component(self._component_id)
        if component:
            if self._horizontal:
                component.mirrored_h = not component.mirrored_h
            else:
                component.mirrored_v = not component.mirrored_v

    def undo(self) -> None:
        """Unflip the component."""
        self.execute()

    @property
    def description(self) -> str:
        component = self._circuit.get_component(self._component_id)
        name = component.name if component else str(self._component_id)[:8]
        axis = "H" if self._horizontal else "V"
        return f"Flip {name} {axis}"


class UpdateComponentStateCommand(Command):
    """Command to apply an arbitrary component state snapshot."""

    def __init__(
        self,
        circuit: Circuit,
        component_id: UUID,
        new_state: dict,
        *,
        old_state: dict | None = None,
        already_applied: bool = False,
    ):
        self._circuit = circuit
        self._component_id = component_id
        self._new_state = deepcopy(new_state)
        self._old_state = deepcopy(old_state) if old_state is not None else None
        self._already_applied = already_applied

    @staticmethod
    def snapshot(component: Component) -> dict:
        """Capture an editable state snapshot from a component."""
        return {
            "name": component.name,
            "x": float(component.x),
            "y": float(component.y),
            "rotation": int(component.rotation) % 360,
            "mirrored_h": bool(component.mirrored_h),
            "mirrored_v": bool(component.mirrored_v),
            "parameters": deepcopy(component.parameters),
            "pins": deepcopy(component.pins),
        }

    @staticmethod
    def _apply(component: Component, state: dict) -> None:
        component.name = state["name"]
        component.x = float(state["x"])
        component.y = float(state["y"])
        component.rotation = int(state["rotation"]) % 360
        component.mirrored_h = bool(state["mirrored_h"])
        component.mirrored_v = bool(state["mirrored_v"])
        component.parameters = deepcopy(state["parameters"])
        component.pins = deepcopy(state["pins"])

    def execute(self) -> None:
        """Apply the new state."""
        component = self._circuit.get_component(self._component_id)
        if component is None:
            return

        if self._old_state is None:
            self._old_state = self.snapshot(component)

        if self._already_applied:
            self._already_applied = False
            return

        self._apply(component, self._new_state)

    def undo(self) -> None:
        """Restore the old state."""
        component = self._circuit.get_component(self._component_id)
        if component is None or self._old_state is None:
            return
        self._apply(component, self._old_state)

    @property
    def description(self) -> str:
        component = self._circuit.get_component(self._component_id)
        if component is not None:
            return f"Edit {component.name}"
        name = self._new_state.get("name")
        if name:
            return f"Edit {name}"
        return f"Edit {str(self._component_id)[:8]}"

    def can_merge(self, other: Command) -> bool:
        """Allow collapsing consecutive edits of the same component."""
        return (
            isinstance(other, UpdateComponentStateCommand)
            and other._component_id == self._component_id
        )

    def merge(self, other: Command) -> None:
        """Keep the original old state and replace the target new state."""
        if isinstance(other, UpdateComponentStateCommand):
            self._new_state = deepcopy(other._new_state)


class ChangeParameterCommand(Command):
    """Command to change a component parameter."""

    def __init__(
        self,
        circuit: Circuit,
        component_id: UUID,
        param_name: str,
        new_value: any,
    ):
        self._circuit = circuit
        self._component_id = component_id
        self._param_name = param_name
        self._new_value = new_value
        self._old_value: any = None

    def execute(self) -> None:
        """Change the parameter value."""
        component = self._circuit.get_component(self._component_id)
        if component:
            self._old_value = component.parameters.get(self._param_name)
            component.parameters[self._param_name] = self._new_value

    def undo(self) -> None:
        """Restore the parameter value."""
        component = self._circuit.get_component(self._component_id)
        if component:
            if self._old_value is None:
                component.parameters.pop(self._param_name, None)
            else:
                component.parameters[self._param_name] = self._old_value

    @property
    def description(self) -> str:
        component = self._circuit.get_component(self._component_id)
        name = component.name if component else str(self._component_id)[:8]
        return f"Change {name}.{self._param_name}"
