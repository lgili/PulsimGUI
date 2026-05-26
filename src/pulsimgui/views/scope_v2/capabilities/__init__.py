"""Scope capabilities — plug-in modules that add behaviour to ``BaseScopeWindow``.

Each capability exposes an ``attach(shell)`` method that the shell
calls once during construction. Capabilities own no UI of their own —
they decorate the shell (toolbar buttons, inspector groups, plot
canvas) so a variant can compose the exact feature set it needs.
"""

from .cursors import CursorsCapability
from .export import ExportCapability
from .fft import FFTCapability
from .live_stream import LiveSignalSpec, LiveStreamCapability
from .math_signals import MathSignalsCapability
from .post_sim import PostSimCapability
from .smps_macros import SMPSMacrosCapability
from .trigger import TriggerCapability

__all__ = [
    "CursorsCapability",
    "ExportCapability",
    "FFTCapability",
    "LiveSignalSpec",
    "LiveStreamCapability",
    "MathSignalsCapability",
    "PostSimCapability",
    "SMPSMacrosCapability",
    "TriggerCapability",
]
