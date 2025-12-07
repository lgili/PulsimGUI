"""Commands for component operations."""

from uuid import UUID

from pulsimgui.commands.base import Command
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component


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

    def execute(self) -> None:
        """Remove the component from the circuit."""
        self._component = self._circuit.remove_component(self._component_id)

    def undo(self) -> None:
        """Restore the component to the circuit."""
        if self._component:
            self._circuit.add_component(self._component)

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
    ):
        self._circuit = circuit
        self._component_id = component_id
        self._new_x = new_x
        self._new_y = new_y
        self._old_x: float = 0
        self._old_y: float = 0

    def execute(self) -> None:
        """Move the component to new position."""
        component = self._circuit.get_component(self._component_id)
        if component:
            self._old_x = component.x
            self._old_y = component.y
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
