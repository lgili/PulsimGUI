"""Regression test for the M3C open-loop topology validation harness.

Pins that ``scripts/validate_m3c.py`` keeps building a well-posed 9-branch
3×3 M3C that simulates in pulsim and performs balanced AC↔AC conversion with
power flowing input→output and bounded (non-diverging) capacitor voltages.

This is a topology/feasibility guard, not a precision check — the open-loop
feed-forward leaves residual current/capacitor errors (the targets of the
thesis's closed-loop control), so the thresholds are deliberately generous.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the repo-root ``scripts`` package importable.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_m3c import (  # noqa: E402
    N_SM, P_RATED, V_C_AGG, analyze, build_m3c, simulate_m3c,
)


def test_build_shape() -> None:
    """The M3C is exactly 9 branches (3×3) of full-bridge arms + inductors."""
    model = build_m3c(f_out=45.0, dt=2.0e-5)
    assert len(model.arms) == 9
    assert len(model.branch_inductors) == 9
    # Every (input-row, output-col) pair present.
    assert set(model.branch_inductors) == {(i, j) for i in range(3) for j in range(3)}
    assert model.meta["v_c_agg"] == V_C_AGG == N_SM * 4.0e3


@pytest.mark.parametrize("f_out", [30.0, 45.0])
def test_ac_ac_conversion(f_out: float) -> None:
    """A short transient converts input→output with balanced sinusoidal
    currents, real power flow, and bounded capacitor voltages."""
    # ≥1 full output cycle must fall in the (second-half) measurement window
    # for the √2·std amplitude estimate to be reliable, so use an 80 ms run.
    model = build_m3c(f_out=f_out, dt=2.0e-5)
    sim = simulate_m3c(model, t_end=0.08)
    metrics = analyze(model, sim)

    # Non-trivial balanced AC currents on both sides (open-loop tolerant).
    assert all(a > 60.0 for a in metrics["in_amps"]), metrics["in_amps"]
    assert all(a > 90.0 for a in metrics["out_amps"]), metrics["out_amps"]
    # Phase balance: spread within 25% of the mean amplitude.
    for amps in (metrics["in_amps"], metrics["out_amps"]):
        mean = sum(amps) / 3.0
        assert (max(amps) - min(amps)) < 0.25 * mean, amps

    # Real power flows input→output near the rated level (both > 1 MW).
    assert metrics["p_in_mean"] > 1.0e6
    assert metrics["p_out_mean"] > 1.0e6
    assert metrics["p_out_mean"] < 1.5 * P_RATED

    # Capacitors stay BOUNDED over the window — open-loop per-branch drift is
    # expected and is largest near f_out≈f_in (slow beat); this guards against
    # divergence, not against the drift the balancing control is meant to fix.
    assert metrics["vc_max_drift_pct"] < 45.0
    assert 0.6 * V_C_AGG < metrics["vc_mean_end"] < 1.4 * V_C_AGG
