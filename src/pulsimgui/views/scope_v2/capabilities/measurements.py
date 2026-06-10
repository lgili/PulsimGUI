"""``MeasurementsCapability`` — per-signal measurement table (PSIM SIMVIEW /
PLECS Scope style).

Clicking the timeline's ``+ Measure`` button computes, for every signal on the
scope, the classic power-electronics quantities over the ANALYSIS RANGE:

    average · RMS · min · max · peak-peak · fundamental frequency · THD

and lists them in a table inside the bottom drawer. The analysis range is the
A↔B cursor span when the cursors are active (PSIM/PLECS convention — put the
cursors one fundamental period apart for textbook-exact RMS/THD), else the
visible X range of the plot.

The math lives in module-level pure functions so it unit-tests without Qt.
"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtWidgets import (
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow

_LOG = logging.getLogger(__name__)


# ── pure measurement math ───────────────────────────────────────────────────


def compute_signal_measurements(
    t: np.ndarray, y: np.ndarray, *, max_harmonic: int = 40,
) -> dict[str, float]:
    """All measurements for one signal over (t, y).

    Returns keys: ``avg, rms, min, max, pkpk, freq, thd`` (``freq``/``thd``
    are ``nan`` when no fundamental is identifiable — DC or too few points).
    THD is IEEE ratio-to-fundamental, in PERCENT, using harmonics 2..N of the
    dominant non-DC spectral component.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    out = {
        "avg": math.nan, "rms": math.nan, "min": math.nan, "max": math.nan,
        "pkpk": math.nan, "freq": math.nan, "thd": math.nan,
    }
    if t.size < 2 or y.size != t.size:
        return out

    # Time-weighted statistics (trapezoidal) so non-uniform sampling is exact.
    span = float(t[-1] - t[0])
    if span <= 0:
        return out
    out["avg"] = float(np.trapezoid(y, t) / span)
    out["rms"] = float(math.sqrt(max(np.trapezoid(y * y, t) / span, 0.0)))
    out["min"] = float(np.min(y))
    out["max"] = float(np.max(y))
    out["pkpk"] = out["max"] - out["min"]

    # Spectral part needs a uniform grid — resample defensively.
    n = int(min(max(t.size, 256), 1 << 16))
    tu = np.linspace(t[0], t[-1], n)
    yu = np.interp(tu, t, y)
    spectrum = np.abs(np.fft.rfft(yu - np.mean(yu)))
    if spectrum.size < 3:
        return out
    k1 = int(np.argmax(spectrum[1:]) + 1)          # dominant non-DC bin
    if spectrum[k1] <= 0 or spectrum[k1] < 1e-12 * n:
        return out                                  # effectively DC
    out["freq"] = k1 / span

    fund = float(spectrum[k1])
    harm_sq = 0.0
    for h in range(2, max_harmonic + 1):
        kh = h * k1
        if kh >= spectrum.size:
            break
        # ±1-bin tolerance absorbs leakage when the range isn't an exact
        # integer number of periods.
        lo, hi = max(kh - 1, 1), min(kh + 2, spectrum.size)
        harm_sq += float(np.max(spectrum[lo:hi])) ** 2
    out["thd"] = 100.0 * math.sqrt(harm_sq) / fund
    return out


# ── capability ──────────────────────────────────────────────────────────────

_COLUMNS = ("Signal", "Avg", "RMS", "Min", "Max", "Pk-Pk", "Freq", "THD %")


class MeasurementsCapability:
    """Per-signal measurement table over the cursor span / visible range."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None
        self._table: QTableWidget | None = None

    # ── ScopeCapability protocol ────────────────────────────────────────

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell

        table = QTableWidget(0, len(_COLUMNS))
        table.setObjectName("ScopeMeasurementTable")
        table.setHorizontalHeaderLabels(_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(_COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        shell.drawer.extra_layout.addWidget(table)
        self._table = table

        # Take over the timeline's "+ Measure" button.
        shell.measure_handler = self.refresh

    # ── analysis range ──────────────────────────────────────────────────

    def _analysis_range(self) -> tuple[float, float] | None:
        """A↔B cursor span when cursors are active, else visible X range."""
        shell = self._shell
        if shell is None:
            return None
        for cap in getattr(shell, "_capabilities", []):
            if cap.__class__.__name__ == "CursorsCapability" and getattr(
                    cap, "_enabled", False):
                a = float(getattr(cap, "_a").position)
                b = float(getattr(cap, "_b").position)
                if a != b:
                    return (min(a, b), max(a, b))
        panel = shell._first_panel()  # noqa: SLF001
        if panel is not None:
            try:
                x_range, _ = panel.viewRange()
                lo, hi = float(x_range[0]), float(x_range[1])
                if hi > lo:
                    return (lo, hi)
            except Exception:  # noqa: BLE001 — headless test paths
                pass
        return None

    # ── refresh ─────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Recompute every signal's measurements and fill the table."""
        shell, table = self._shell, self._table
        if shell is None or table is None:
            return
        signals = getattr(shell.plot_canvas, "_signals", {})  # noqa: SLF001
        rng = self._analysis_range()

        rows: list[tuple[str, dict[str, float]]] = []
        for name, state in sorted(signals.items()):
            try:
                t_arr, y_arr = state.merged()
            except Exception:  # noqa: BLE001
                continue
            if t_arr.size < 2:
                continue
            if rng is not None:
                mask = (t_arr >= rng[0]) & (t_arr <= rng[1])
                if int(mask.sum()) >= 2:
                    t_arr, y_arr = t_arr[mask], y_arr[mask]
            rows.append((name, compute_signal_measurements(t_arr, y_arr)))

        table.setRowCount(len(rows))
        for r, (name, m) in enumerate(rows):
            values = (
                name, _fmt(m["avg"]), _fmt(m["rms"]), _fmt(m["min"]),
                _fmt(m["max"]), _fmt(m["pkpk"]), _fmt_freq(m["freq"]),
                _fmt(m["thd"]),
            )
            for c, text in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(text))

        # Surface the result + make sure the drawer is open.
        if rng is not None:
            src = "cursors A↔B" if self._cursors_active() else "visible range"
            shell.set_drawer_status(
                "completed",
                f"Measurements over {src}: {rng[0]:.6g} s → {rng[1]:.6g} s "
                f"({len(rows)} signal(s)). Tip: put the cursors exactly one "
                "fundamental period apart for textbook RMS/THD.",
            )
        else:
            shell.set_drawer_status(
                "completed", f"Measurements over full data ({len(rows)} signal(s)).",
            )
        if not getattr(shell, "_drawer_expanded", False):
            shell._on_drawer_expand_toggled()  # noqa: SLF001

    def _cursors_active(self) -> bool:
        for cap in getattr(self._shell, "_capabilities", []):
            if cap.__class__.__name__ == "CursorsCapability":
                return bool(getattr(cap, "_enabled", False))
        return False


def _fmt(value: float) -> str:
    return "—" if (value != value) else f"{value:.5g}"      # nan-safe


def _fmt_freq(value: float) -> str:
    if value != value:
        return "—"
    if value >= 1e6:
        return f"{value / 1e6:.4g} MHz"
    if value >= 1e3:
        return f"{value / 1e3:.4g} kHz"
    return f"{value:.4g} Hz"
