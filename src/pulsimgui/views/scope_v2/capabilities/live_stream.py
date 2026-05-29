"""``LiveStreamCapability`` — feeds the scope plot from the kernel ring buffer.

When the ``SimulationService`` emits ``live_stream_ready(stream)`` at
the start of a run, this capability:

  1. Registers one curve per ``LiveSignalSpec`` on the shell's plot
     canvas (using the spec's panel + colour).
  2. Starts a 60 Hz ``QTimer`` that polls ``stream.get_new_samples()``
     and appends the new chunk to the corresponding curve.
  3. Stops the timer when the simulation ends (the ``PostSimCapability``
     then replaces the ring data with the full-resolution result).

The capability has no UI of its own — it just decorates the existing
plot canvas. The shell stays variant-agnostic.

Threading contract:
    All Qt calls happen on the GUI thread. ``stream.get_new_samples()``
    is safe to call from any thread because the underlying C++ ring
    buffer is atomic — the kernel pushes from the simulation worker
    thread, the GUI reads here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from PySide6.QtCore import QTimer

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveSignalSpec:
    """One curve to stream from the kernel state vector.

    Attributes
    ----------
    name
        Display name + plot-canvas key. Same name the post-sim
        capability uses, so the curve transitions seamlessly.
    state_idx
        Column index into the kernel state vector that the ring
        buffer pushes (resolved by the host from the scope's
        channel bindings).
    color
        Hex string for the pen.
    unit
        SI-ish unit for the axis label.
    panel
        Sub-panel the curve goes into. Defaults to ``"Main"``.
    """

    name: str
    state_idx: int
    color: str = ""
    unit: str = ""
    panel: str = "Main"


class LiveStreamCapability:
    """Subscribe to a kernel ``NativeLiveStream`` and stream into the canvas."""

    def __init__(
        self,
        simulation_service: Any,
        signal_specs: list[LiveSignalSpec],
        *,
        update_hz: float = 60.0,
    ) -> None:
        self._simulation_service = simulation_service
        self._signal_specs = list(signal_specs)
        self._update_interval_ms = max(10, int(1000.0 / max(1.0, update_hz)))

        self._shell: BaseScopeWindow | None = None
        self._stream: Any | None = None
        self._timer: QTimer | None = None
        self._active = False

    # ── ScopeCapability protocol ────────────────────────────────────────

    def attach(self, shell: BaseScopeWindow) -> None:
        """Hook into the shell + start listening for the next live stream."""
        self._shell = shell

        # Register the curves up front so the user sees them both in
        # the plot legend AND in the sidebar signal list even before
        # the first run starts.
        from .._auto_palette import next_palette_color  # local import to avoid cycles
        for idx, spec in enumerate(self._signal_specs):
            color = spec.color or next_palette_color(idx)
            shell.plot_canvas.add_signal(
                spec.name,
                color=color,
                panel=spec.panel,
                unit=spec.unit,
            )
            shell.sidebar.add_signal_row(spec.name, color, unit=spec.unit)
        if self._signal_specs:
            shell.plot_canvas.set_empty_message(
                "Waiting for live data…",
                "Click ▶ Run on the toolbar to start streaming.",
            )
            shell.set_drawer_status(
                "idle",
                f"{len(self._signal_specs)} signals connected — click Run to start streaming.",
            )

        # Wire shell transport buttons to the simulation service so the
        # user can drive the run from inside the scope (PLECS-style).
        shell.toolbar.run_clicked.connect(self._on_run_clicked)
        shell.toolbar.stop_clicked.connect(self._on_stop_clicked)

        # Listen for the kernel allocating a fresh ring buffer.
        simulation_service = self._simulation_service
        sig = getattr(simulation_service, "live_stream_ready", None)
        if sig is not None:
            sig.connect(self._on_stream_ready)
        else:
            _LOG.warning(
                "LiveStreamCapability: %s has no live_stream_ready signal",
                type(simulation_service).__name__,
            )

        # Subscribe to simulation_finished eagerly — one connection per
        # capability lifetime. Doing this lazily inside ``_on_stream_ready``
        # caused two issues: (a) duplicate connections piled up on each
        # run (each run reconnected) so ``_on_sim_finished`` fired N
        # times after N runs, and (b) if the worker thread completed
        # fast enough that ``simulation_finished`` arrived before
        # ``_on_stream_ready`` had a chance to wire the slot, the final
        # ``_tick`` + ``stop_polling`` were skipped entirely.
        finished = getattr(simulation_service, "simulation_finished", None)
        if finished is not None:
            finished.connect(self._on_sim_finished)

    # ── Transport buttons ───────────────────────────────────────────────

    def _on_run_clicked(self) -> None:
        """Forward Run → SimulationService — pre-clear the canvas data."""
        # Drop any previous run's data before the kernel produces the next.
        shell = self._shell
        if shell is not None:
            for spec in self._signal_specs:
                shell.plot_canvas.replace_signal(
                    spec.name,
                    np.empty(0, dtype=np.float64),
                    np.empty(0, dtype=np.float64),
                )
        run = getattr(self._simulation_service, "run_transient_project", None)
        project = getattr(shell, "_project", None) if shell is not None else None
        if callable(run) and project is not None:
            run(project)

    def _on_stop_clicked(self) -> None:
        stop = getattr(self._simulation_service, "stop", None)
        if callable(stop):
            stop()

    # ── Stream lifecycle ────────────────────────────────────────────────

    def _on_stream_ready(self, stream: Any) -> None:
        """Kernel just allocated a NativeLiveStream — start polling it."""
        if self._shell is None:
            return
        self._stream = stream
        self._active = True

        # Refresh the empty-state overlay text in case nothing's drawn yet.
        self._shell.plot_canvas.set_empty_message(
            "Streaming…",
            "Live samples will appear here as the kernel produces them.",
        )
        self._shell.set_drawer_status(
            "running",
            f"Streaming — {len(self._signal_specs)} signal(s) live from kernel.",
        )

        if self._timer is None:
            self._timer = QTimer(self._shell)
            self._timer.setInterval(self._update_interval_ms)
            self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _on_sim_finished(self, _result: Any) -> None:
        # Drain any last samples before we hand off to the post-sim
        # path (which replaces the full-resolution arrays).
        self._tick()
        self.stop_polling()

    def stop_polling(self) -> None:
        """Halt the polling timer without releasing the stream reference."""
        if self._timer is not None and self._timer.isActive():
            self._timer.stop()
        self._active = False

    # ── Hot path ────────────────────────────────────────────────────────

    def _tick(self) -> None:
        """Poll the kernel ring buffer and forward chunks to the canvas."""
        if self._shell is None or self._stream is None or not self._active:
            return
        samples = self._stream.get_new_samples()
        if samples is None:
            return
        t_new, x_new = samples
        if t_new.size == 0:
            return
        for spec in self._signal_specs:
            if spec.state_idx >= x_new.shape[1]:
                continue
            y = x_new[:, spec.state_idx]
            self._shell.plot_canvas.append_signal(spec.name, t_new, y)


__all__ = ["LiveStreamCapability", "LiveSignalSpec"]
