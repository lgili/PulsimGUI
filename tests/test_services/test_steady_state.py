"""Steady-state detection — convergence verdicts on synthetic waveforms."""
from __future__ import annotations

import math

import numpy as np

from pulsimgui.services.steady_state import (
    analyze_steady_state,
    extract_last_cycle,
)

F = 50.0
T = 1.0 / F


def _times(cycles: float, fs: float = 100_000.0) -> np.ndarray:
    return np.arange(0.0, cycles * T, 1.0 / fs)


def test_settling_waveform_converges() -> None:
    """Sine + decaying exponential (RC start-up): converged once the
    transient dies; the converged cycle is past the time constant."""
    t = _times(10)
    y = np.sin(2 * math.pi * F * t) + 2.0 * np.exp(-t / T)
    rep = analyze_steady_state(t, {"v": y}, T, tol_pct=1.0)
    assert rep.n_cycles >= 9                  # arange ends just short of 10T
    assert rep.converged
    assert 3 <= rep.converged_cycle <= rep.n_cycles
    assert rep.final_residual_pct < 1.0
    # residuals decay monotonically for a settling exponential
    assert rep.residuals_pct == sorted(rep.residuals_pct, reverse=True)


def test_pure_periodic_converges_immediately() -> None:
    t = _times(5)
    y = 10 * np.sin(2 * math.pi * F * t)
    rep = analyze_steady_state(t, {"v": y}, T, tol_pct=1.0)
    assert rep.converged and rep.converged_cycle == 1


def test_drifting_waveform_does_not_converge() -> None:
    """A linearly drifting envelope (the M3C cap-drift signature) must be
    flagged NOT converged, with the drifting signal named."""
    t = _times(8)
    good = np.sin(2 * math.pi * F * t)
    drifting = (1.0 + 5.0 * t) * np.sin(2 * math.pi * F * t)
    rep = analyze_steady_state(t, {"i_in": good, "v_cap": drifting}, T,
                               tol_pct=1.0)
    assert not rep.converged
    assert rep.worst_signal == "v_cap"
    assert rep.final_residual_pct > 1.0


def test_too_short_run_is_inconclusive() -> None:
    t = _times(1.5)
    y = np.sin(2 * math.pi * F * t)
    rep = analyze_steady_state(t, {"v": y}, T)
    assert rep.n_cycles < 2 and not rep.converged


def test_extract_last_cycle_rebased() -> None:
    t = _times(6)
    y = np.sin(2 * math.pi * F * t)
    grid, out = extract_last_cycle(t, {"v": y}, T)
    assert grid[0] == 0.0 and grid[-1] < T
    # the extracted cycle is one clean sine period
    assert abs(float(np.max(out["v"])) - 1.0) < 0.01
    assert abs(float(np.sqrt(np.mean(out["v"] ** 2))) - 1 / math.sqrt(2)) < 0.01


def test_dialog_runs_and_reports(qapp) -> None:
    from pulsimgui.views.dialogs.steady_state_dialog import SteadyStateDialog

    t = _times(6)
    dialog = SteadyStateDialog(
        t, {"v": np.sin(2 * math.pi * F * t)}, default_frequency=F)
    try:
        dialog._run()
        assert dialog.last_report is not None
        assert dialog.last_report.converged
        assert "Steady state reached" in dialog._verdict.text()
        assert dialog._table.rowCount() == dialog.last_report.n_cycles - 1
    finally:
        dialog.close()
