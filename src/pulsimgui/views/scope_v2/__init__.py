"""Scope v2 — modular PLECS-style scope shell.

A single ``BaseScopeWindow`` shell that any scope variant (electrical,
thermal, future AC/DC, …) composes with capabilities (live stream,
post-sim, cursors, math, trigger, FFT, SMPS macros, export, …).

The shell owns the chrome — header, menubar, toolbar, sidebars,
multi-pane plot canvas, inspector, drawer, timeline. Capabilities own
behaviour and plug into the shell at construction time.
"""

from .capabilities import (
    CursorsCapability,
    ExportCapability,
    FFTCapability,
    LiveSignalSpec,
    LiveStreamCapability,
    MathSignalsCapability,
    MeasurementsCapability,
    PostSimCapability,
    SMPSMacrosCapability,
    TriggerCapability,
)
from .plot_canvas import DEFAULT_PALETTE, PlotCanvas
from .shell import BaseScopeWindow

__all__ = [
    "MeasurementsCapability",
    "BaseScopeWindow",
    "DEFAULT_PALETTE",
    "LiveSignalSpec",
    "LiveStreamCapability",
    "PlotCanvas",
    "PostSimCapability",
]
