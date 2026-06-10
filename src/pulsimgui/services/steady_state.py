"""Periodic steady-state detection over a finished transient run.

PLECS' steady-state analysis skips startup transients with a shooting method —
that needs kernel support for restarting from an arbitrary state vector, which
pulsim's ``simulate`` does not expose (no ``x0``). What the GUI CAN give today
is the other half of the workflow: after a transient run, answer **"did the
simulation actually reach periodic steady state?"** with per-cycle residuals,
and hand back the converged final cycle for analysis.

Method: slice the waveforms into fundamental periods, resample every cycle
onto a common uniform grid, and compute the cycle-to-cycle residual

    r_k = max over signals of  RMS(c_k − c_{k−1}) / max(RMS_k, ε)  · 100 %

The run is steady when r_k stays below the tolerance for the remaining cycles.
A capacitor still charging or an energy mode slowly diverging (the classic
MMC/M3C "caps lose themselves") shows up immediately as a non-decaying tail.

Pure Python/numpy (no Qt) so it unit-tests in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

_GRID_POINTS = 512


@dataclass
class SteadyStateReport:
    """Outcome of a steady-state check."""

    period: float
    n_cycles: int
    tol_pct: float
    residuals_pct: list[float] = field(default_factory=list)  # r_1 … (len = n_cycles-1)
    converged_cycle: int | None = None     # first cycle index that stays converged
    worst_signal: str = ""                  # signal dominating the LAST residual

    @property
    def converged(self) -> bool:
        return self.converged_cycle is not None

    @property
    def final_residual_pct(self) -> float:
        return self.residuals_pct[-1] if self.residuals_pct else float("nan")


def _cycles(times: np.ndarray, values: np.ndarray, period: float) -> np.ndarray:
    """Resample the signal into complete cycles on a common uniform grid.

    Returns an array of shape (n_cycles, _GRID_POINTS). Cycles are counted
    backwards from the END of the run so a partial first cycle (start-up
    offset) never misaligns the comparison.
    """
    t0, t1 = float(times[0]), float(times[-1])
    n = int(np.floor((t1 - t0) / period + 1e-9))
    if n < 1:
        return np.empty((0, _GRID_POINTS))
    rows = []
    local = np.linspace(0.0, period, _GRID_POINTS, endpoint=False)
    for k in range(n):
        start = t1 - (n - k) * period
        rows.append(np.interp(start + local, times, values))
    return np.asarray(rows)


def analyze_steady_state(
    times,
    signals: dict[str, np.ndarray],
    period: float,
    tol_pct: float = 1.0,
) -> SteadyStateReport:
    """Cycle-to-cycle convergence check across every signal.

    ``signals`` maps name → samples on the shared ``times`` axis. ``period``
    is the fundamental period (1/f of the slowest excitation). ``tol_pct`` is
    the maximum allowed cycle-to-cycle RMS delta, in percent.
    """
    times = np.asarray(times, dtype=float)
    if times.size < 4 or period <= 0:
        return SteadyStateReport(period=period, n_cycles=0, tol_pct=tol_pct)

    per_signal: dict[str, np.ndarray] = {}
    n_cycles = 0
    for name, values in signals.items():
        values = np.asarray(values, dtype=float)
        if values.size != times.size:
            continue
        cyc = _cycles(times, values, period)
        if cyc.shape[0] >= 2:
            per_signal[name] = cyc
            n_cycles = max(n_cycles, cyc.shape[0])

    report = SteadyStateReport(period=period, n_cycles=n_cycles, tol_pct=tol_pct)
    if not per_signal or n_cycles < 2:
        return report

    residuals: list[float] = []
    worst_at: list[str] = []
    for k in range(1, n_cycles):
        worst, worst_name = 0.0, ""
        for name, cyc in per_signal.items():
            if k >= cyc.shape[0]:
                continue
            ref = float(np.sqrt(np.mean(cyc[k] ** 2)))
            scale = max(ref, 1e-12)
            delta = float(np.sqrt(np.mean((cyc[k] - cyc[k - 1]) ** 2)))
            r = 100.0 * delta / scale
            if r > worst:
                worst, worst_name = r, name
        residuals.append(worst)
        worst_at.append(worst_name)

    report.residuals_pct = residuals
    report.worst_signal = worst_at[-1] if worst_at else ""

    # Converged when the residual drops below tol and STAYS below it.
    for k in range(len(residuals)):
        if all(r <= tol_pct for r in residuals[k:]):
            report.converged_cycle = k + 1     # residual k compares cycle k+1 vs k
            break
    return report


def extract_last_cycle(
    times, signals: dict[str, np.ndarray], period: float,
) -> tuple[np.ndarray, dict[str, np.ndarray]]:
    """The final complete cycle of every signal, rebased to t=0 — the
    'steady-state cycle' to analyse/export once the report says converged."""
    times = np.asarray(times, dtype=float)
    t1 = float(times[-1])
    start = t1 - period
    if start < float(times[0]):
        return times.copy(), {k: np.asarray(v, dtype=float)
                              for k, v in signals.items()}
    grid = np.linspace(0.0, period, _GRID_POINTS, endpoint=False)
    out = {
        name: np.interp(start + grid, times, np.asarray(values, dtype=float))
        for name, values in signals.items()
        if np.asarray(values).size == times.size
    }
    return grid, out
