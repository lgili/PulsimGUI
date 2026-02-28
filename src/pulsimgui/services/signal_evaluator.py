"""Backward-compatibility shim — simulation logic lives in PulsimCore.

Import directly from ``pulsim.signal_evaluator`` for new code.
"""
from pulsim.signal_evaluator import (  # noqa: F401
    SignalEvaluator,
    AlgebraicLoopError,
    SIGNAL_TYPES,
)

__all__ = ["SignalEvaluator", "AlgebraicLoopError", "SIGNAL_TYPES"]
