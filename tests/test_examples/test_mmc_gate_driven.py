"""Regression test for the gate-driven 3-phase MMC (switched, external control).

Pins that ``scripts/validate_mmc_gate_driven.py`` builds a six-arm DC→AC MMC
whose arms are driven entirely by external gates (no internal modulation, no
internal balancing) and that the external sinusoidal modulator produces real
switched signals: a multilevel arm-voltage staircase, balanced load currents,
and per-submodule capacitors equalised by the external sort-and-select.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_mmc_gate_driven import (  # noqa: E402
    N_SM, V_DC, build_gate_driven_mmc, simulate_gate_driven_mmc)


def test_build_shape() -> None:
    model = build_gate_driven_mmc(dt=2.0e-5)
    assert len(model.arms) == 6                       # upper + lower per phase
    assert set(model.arm_names) == {f"{s}_{p}" for s in "UL" for p in "abc"}
    for arm in model.arms.values():
        assert len(arm.v_C_per_sm) == N_SM


def test_switched_signals_and_external_balancing() -> None:
    model = build_gate_driven_mmc(dt=1.0e-5, v_c0_spread=400.0)
    assert max(a.v_C_spread for a in model.arms.values()) > 250.0   # seeded

    sim = simulate_gate_driven_mmc(model, t_end=0.05)
    t = sim["times"]
    sl = slice(len(t) // 2, None)

    def amp(s):
        return float(np.sqrt(2.0) * np.std(np.asarray(s)[sl]))

    i_amps = [amp(s) for s in sim["i_load"]]
    assert all(80.0 < a < 400.0 for a in i_amps), i_amps
    # balanced three-phase load currents
    assert (max(i_amps) - min(i_amps)) < 0.15 * (sum(i_amps) / 3.0)

    # the upper-arm voltage is a genuine multilevel staircase (≥ several of the
    # N+1 levels are visited)
    levels = len(np.unique(np.round(sim["vb_ua"] / model.meta["v_cap"])))
    assert levels >= 6, levels

    # arm caps stay near the DC bus (energy-balanced over the window)
    assert 0.8 * V_DC < float(np.mean(sim["v_c"][-1])) < 1.2 * V_DC

    # external sort-and-select collapses the seeded submodule spread
    assert float(np.max(sim["spread"][-1])) < 120.0


def test_arms_have_no_internal_modulation() -> None:
    model = build_gate_driven_mmc(dt=2.0e-5)
    arm = next(iter(model.arms.values()))
    assert not hasattr(arm, "m_b_fn")              # no internal modulation index
    assert callable(arm.gate_source)               # driven by external gates
    assert arm.params.sm_type == "half_bridge"
