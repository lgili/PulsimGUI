"""Undoable auto-layout: move every component + re-route every wire.

One command, one undo — pressing Ctrl+Z after Auto-Layout restores
both the exact prior component positions AND each wire's original
polyline (the embedded :class:`RerouteAllWiresCommand` captures and
restores segments itself).
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from pulsimgui.commands.base import Command
from pulsimgui.commands.wire_commands import RerouteAllWiresCommand

if TYPE_CHECKING:  # pragma: no cover - typing only
    from pulsimgui.models.circuit import Circuit


class AutoLayoutCommand(Command):
    """Apply a computed placement to the circuit, then tidy the wires."""

    def __init__(
        self,
        circuit: Circuit,
        positions: dict[UUID, tuple[float, float]],
        *,
        grid: float = 20.0,
    ):
        self._circuit = circuit
        self._positions = dict(positions)
        self._before: dict[UUID, tuple[float, float]] | None = None
        self._reroute = RerouteAllWiresCommand(circuit, grid=grid)

    @property
    def description(self) -> str:
        return "Auto-layout components"

    def execute(self) -> None:
        if self._before is None:
            self._before = {}
            for cid in self._positions:
                comp = self._circuit.get_component(cid)
                if comp is not None:
                    self._before[cid] = (comp.x, comp.y)
        for cid, (x, y) in self._positions.items():
            comp = self._circuit.get_component(cid)
            if comp is not None:
                comp.x = x
                comp.y = y
        self._reroute.execute()

    def undo(self) -> None:
        self._reroute.undo()
        for cid, (x, y) in (self._before or {}).items():
            comp = self._circuit.get_component(cid)
            if comp is not None:
                comp.x = x
                comp.y = y
