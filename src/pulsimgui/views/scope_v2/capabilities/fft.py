"""``FFTCapability`` — toggle a frequency-domain view of the cached signals.

Decorates the toolbar's FFT button. When the user clicks it, the plot
canvas switches from its time-domain pyqtgraph layout to the FFT
layout (handled entirely inside ``PlotCanvas.set_view``). Clicking
again switches back. The capability owns no UI of its own — it just
wires the toolbar toggle to the canvas.

The actual FFT math (``numpy.fft.rfft`` on the cached samples + log-X
magnitude in dB) lives in ``plot_canvas._signal_fft`` so the canvas
can recompute it whenever the user re-enters the FFT view without
needing a callback into the capability.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


class FFTCapability:
    """Toolbar FFT button → ``PlotCanvas.set_view("fft" / "time")``."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell
        shell.toolbar.btn_fft.toggled.connect(self._on_toggle)

    def _on_toggle(self, on: bool) -> None:
        if self._shell is None:
            return
        self._shell.plot_canvas.set_view("fft" if on else "time")
        # Friendly status line so the user knows what changed.
        if on:
            self._shell.drawer.summary.setText(
                "FFT view — frequency-domain magnitude (dB) of the cached signals."
            )
        else:
            self._shell.drawer.summary.setText(
                "Time view — drag the timeline scrubber to navigate captured data."
            )


__all__ = ["FFTCapability"]
