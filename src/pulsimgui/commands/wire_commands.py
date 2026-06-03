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
        """Return the command text displayed in the undo/redo history."""
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
        """Return the command text displayed in the undo/redo history."""
        return "Delete wire"


class RerouteAllWiresCommand(Command):
    """Re-route every wire in the circuit as clean orthogonal paths.

    Components are NOT moved — only each wire's polyline between its two
    existing endpoints (pin connections) is recomputed with the smart
    :class:`~pulsimgui.utils.wire_router.WireRouter` (obstacle-avoiding,
    corner-deduped). Undoable: stores and restores the exact prior
    segments of every wire.
    """

    def __init__(self, circuit: Circuit, grid: float = 20.0):
        self._circuit = circuit
        self._grid = grid
        # wire_id -> list of (x1, y1, x2, y2) captured on first execute.
        self._before: dict | None = None

    def execute(self) -> None:
        """Recompute every wire's route via the smart orthogonal router."""
        from pulsimgui.models.wire import WireSegment
        from pulsimgui.utils.wire_router import WireRouter

        wires = list(self._circuit.wires.values())
        if self._before is None:
            self._before = {
                w.id: [(s.x1, s.y1, s.x2, s.y2) for s in w.segments]
                for w in wires
            }

        router = WireRouter(grid=self._grid)
        comp_dicts = [
            {
                "x": float(getattr(c, "x", 0.0) or 0.0),
                "y": float(getattr(c, "y", 0.0) or 0.0),
                "pins": [
                    {"x": float(getattr(p, "x", 0.0) or 0.0),
                     "y": float(getattr(p, "y", 0.0) or 0.0)}
                    for p in (getattr(c, "pins", None) or [])
                ],
            }
            for c in self._circuit.components.values()
        ]
        router.add_obstacles_from_components(comp_dicts)

        for wire in wires:
            start = wire.start_point
            end = wire.end_point
            if start is None or end is None:
                continue
            raw = router.route(start[0], start[1], end[0], end[1])
            if raw:
                wire.segments = [
                    WireSegment(x1, y1, x2, y2) for (x1, y1, x2, y2) in raw
                ]
                # Safety net: the router's last-resort fallback (when the
                # canvas is genuinely impassable) can be a single diagonal
                # segment. Split any such segment into an orthogonal L so
                # the result is always strictly horizontal/vertical.
                wire.normalize_orthogonal()

    def undo(self) -> None:
        """Restore every wire's original segments."""
        from pulsimgui.models.wire import WireSegment

        if not self._before:
            return
        for wire in self._circuit.wires.values():
            saved = self._before.get(wire.id)
            if saved is not None:
                wire.segments = [WireSegment(*seg) for seg in saved]

    @property
    def description(self) -> str:
        """Return the command text displayed in the undo/redo history."""
        return "Auto-route wires"
