"""Backend bridge for signal-flow evaluation.

PulsimGui intentionally delegates signal-domain block execution to the backend
package (``pulsim.signal_evaluator``) to keep control behavior aligned between
GUI and backend runs.
"""

from __future__ import annotations

from typing import Any


class AlgebraicLoopError(RuntimeError):
    """Raised when a cycle is detected in the signal-flow graph."""


class SignalEvaluator:
    """Placeholder type used when backend evaluator is unavailable."""

    def __init__(self, _circuit_data: dict[str, Any]) -> None:
        raise RuntimeError(
            "SignalEvaluator requires backend support from pulsim.signal_evaluator. "
            "Install/upgrade the Pulsim backend package to run signal-domain control blocks."
        )


SIGNAL_TYPES: frozenset[str] = frozenset()


try:  # Prefer backend-native implementation.
    from pulsim.signal_evaluator import (  # type: ignore[import-not-found]
        AlgebraicLoopError,
        SIGNAL_TYPES,
        SignalEvaluator,
    )
except Exception:
    # Keep module importable so optional-backend workflows and tests can still start.
    # Runtime code must treat SignalEvaluator construction failure as backend-missing.
    pass


__all__ = ["SignalEvaluator", "AlgebraicLoopError", "SIGNAL_TYPES"]
