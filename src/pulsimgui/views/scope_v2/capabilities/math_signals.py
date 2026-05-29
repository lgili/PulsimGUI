"""``MathSignalsCapability`` — derive new traces from A∘B formulas.

When the user clicks ``fx`` on the toolbar, a dialog asks for two
source signals (drawn from the canvas), a whitelisted formula
(``A + B``, ``abs(A)``, ``derivative(A)``, ``moving_avg(A, 16)``, …),
and an optional result name. The capability evaluates the formula on
the current time vector and adds the result as a new curve.

Reuses ``MathSignalDialog`` + ``evaluate_math_expression`` from the
legacy scope package so we don't ship two AST evaluators. When the
legacy package is finally deleted we'll move those helpers into
``scope_v2/`` and drop this import.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import QDialog

from .._auto_palette import next_palette_color

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


class MathSignalsCapability:
    """Toolbar fx button → math-expression dialog → derived curve."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None
        self._counter = 0

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell
        shell.toolbar.btn_math.clicked.connect(self._on_math_clicked)

    def _on_math_clicked(self) -> None:
        if self._shell is None:
            return

        # Pull the canvas data into the format ``MathSignalDialog`` wants:
        # one dict {signal_name → y_values}, one parallel units dict, and
        # a single time vector.
        canvas = self._shell.plot_canvas
        signal_names = list(canvas.signals())
        if not signal_names:
            self._shell.drawer.summary.setText(
                "Math signal: run the simulation first so source data is available."
            )
            return

        signal_data: dict[str, np.ndarray] = {}
        signal_units: dict[str, str] = {}
        time_values: np.ndarray | None = None
        for name in signal_names:
            state = canvas._signals[name]  # noqa: SLF001
            t, y = state.merged()
            if t.size == 0:
                continue
            signal_data[name] = y
            signal_units[name] = state.unit
            if time_values is None or t.size > time_values.size:
                time_values = t
        if not signal_data or time_values is None:
            self._shell.drawer.summary.setText(
                "Math signal: no samples yet — click Run to capture data first."
            )
            return

        # Reuse the existing dialog from the legacy scope package (the
        # evaluator + dialog are theme-aware and well-tested).
        try:
            from ..math_expression import (
                MathSignalDialog,
                evaluate_math_expression,
                infer_math_expression_unit,
            )
        except Exception as exc:  # pragma: no cover - safety net
            _LOG.warning("MathSignalsCapability: cannot import dialog: %s", exc)
            return

        default = signal_names[0]
        dialog = MathSignalDialog(
            self._shell,
            signal_data=signal_data,
            signal_units=signal_units,
            time_values=time_values,
            default_signal=default,
            theme=None,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        cfg = dialog.selected_config()
        source_a = str(cfg.get("source_a", default))
        source_b = str(cfg.get("source_b", default))
        formula = str(cfg.get("formula", "A"))
        custom_name = str(cfg.get("custom_name", ""))
        env = {
            "A": signal_data.get(source_a, np.array([], dtype=float)),
            "B": signal_data.get(source_b, signal_data.get(source_a, np.array([], dtype=float))),
            "t": time_values,
        }
        env_units = {
            "A": signal_units.get(source_a, ""),
            "B": signal_units.get(source_b, ""),
            "t": "s",
        }

        try:
            result = evaluate_math_expression(formula, env, time_values)
        except Exception as exc:  # noqa: BLE001 — user-facing error
            self._shell.drawer.summary.setText(f"Math signal failed: {exc}")
            return

        unit = infer_math_expression_unit(formula, env_units)
        self._counter += 1
        name = custom_name.strip() or f"M{self._counter}: {formula}"
        if len(name) > 48:
            name = name[:45] + "…"

        # Colour the math trace from the standard palette but offset by
        # the existing signal count so it doesn't collide with the
        # canonical signals.
        color = next_palette_color(len(canvas.signals()))

        canvas.add_signal(name, color=color, panel="Main", unit=unit)
        canvas.replace_signal(name, time_values, np.asarray(result, dtype=float))
        self._shell.sidebar.add_signal_row(name, color, unit=unit)
        self._shell.drawer.summary.setText(f"Added math signal '{name}'.")


__all__ = ["MathSignalsCapability"]
