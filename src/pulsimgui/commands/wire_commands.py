"""Commands for wire operations."""

from uuid import UUID

from pulsimgui.commands.base import Command
from pulsimgui.models.circuit import Circuit
from pulsimgui.models.wire import Wire


class AddWireCommand(Command):
    """Command to add a wire to a circuit."""

    def __init__(self, circuit: Circuit, wire: Wire):
        self._circuit = circuit
        self._wire = wire

    def execute(self) -> None:
        """Add the wire to the circuit."""
        self._circuit.add_wire(self._wire)

    def undo(self) -> None:
        """Remove the wire from the circuit."""
        self._circuit.remove_wire(self._wire.id)

    @property
    def description(self) -> str:
        return "Add wire"


class DeleteWireCommand(Command):
    """Command to delete a wire from a circuit."""

    def __init__(self, circuit: Circuit, wire_id: UUID):
        self._circuit = circuit
        self._wire_id = wire_id
        self._wire: Wire | None = None

    def execute(self) -> None:
        """Remove the wire from the circuit."""
        self._wire = self._circuit.remove_wire(self._wire_id)

    def undo(self) -> None:
        """Restore the wire to the circuit."""
        if self._wire:
            self._circuit.add_wire(self._wire)

    @property
    def description(self) -> str:
        return "Delete wire"
