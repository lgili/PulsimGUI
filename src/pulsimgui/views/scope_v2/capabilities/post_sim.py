"""``PostSimCapability`` — replaces live data with the full-resolution result.

When the kernel finishes a run, ``SimulationService.simulation_finished``
fires with a ``SimulationResult``. This capability listens for that and
swaps the streaming ring data on each curve for the complete time +
state arrays from the result, so the user sees the entire run in the
same window they were already looking at.

It pairs with :class:`LiveStreamCapability`; if only this capability is
attached, the canvas stays empty until the first run finishes. If both
are attached, the live stream populates the curves first and this
capability finalises them at the end.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostSimSignalSpec:
    """Mapping used to look a signal up in the finished ``SimulationResult``.

    Attributes
    ----------
    name
        Display name on the plot canvas (matches the live-stream spec
        so the curve transitions seamlessly).
    signal_key
        Key into ``SimulationResult.signals`` — the same string the
        scope's channel binding resolved from wires on the schematic.
    """

    name: str
    signal_key: str


class PostSimCapability:
    """Finalise the plot canvas with the full simulation result."""

    def __init__(
        self,
        simulation_service: Any,
        signal_specs: list[PostSimSignalSpec],
    ) -> None:
        self._simulation_service = simulation_service
        self._signal_specs = list(signal_specs)
        self._shell: BaseScopeWindow | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        """Subscribe to the simulation-finished signal."""
        self._shell = shell
        sig = getattr(self._simulation_service, "simulation_finished", None)
        if sig is None:
            _LOG.warning(
                "PostSimCapability: %s has no simulation_finished signal",
                type(self._simulation_service).__name__,
            )
            return
        sig.connect(self._on_finished)

    def _on_finished(self, result: Any) -> None:
        """Replace each curve with the full-resolution arrays from ``result``."""
        if self._shell is None or result is None:
            return
        t = np.asarray(getattr(result, "time", []), dtype=np.float64)
        signals = getattr(result, "signals", None) or {}
        if t.size == 0 or not signals:
            return

        # Each scope channel binding gives us a ``signal_key`` that lives
        # in ``result.signals`` — straight dict lookup, no state-vector
        # slicing required.
        matched = 0
        for spec in self._signal_specs:
            data = signals.get(spec.signal_key)
            if data is None:
                _LOG.debug(
                    "PostSimCapability: signal_key %r not in result.signals",
                    spec.signal_key,
                )
                continue
            y = np.asarray(data, dtype=np.float64)
            # Some backends return per-step values; trim to ``t`` length
            # to be safe if a stray sample slipped in.
            n = min(t.size, y.size)
            self._shell.plot_canvas.replace_signal(spec.name, t[:n], y[:n])
            matched += 1

        # Reset the empty-state hint now that the canvas has real data.
        self._shell.plot_canvas.set_empty_message(
            "Run completed",
            "Drop more signals from the sidebar to overlay them.",
        )

        # Surface a one-line summary in the drawer.
        drawer = getattr(self._shell, "drawer", None)
        if drawer is not None and hasattr(drawer, "summary"):
            drawer.summary.setText(
                f"Run completed — {t.size} points • {matched} of {len(self._signal_specs)} signals matched."
            )


__all__ = ["PostSimCapability", "PostSimSignalSpec"]
