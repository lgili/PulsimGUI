"""Regression test for the gate-driven M3C (thesis modulation 100% external).

Pins that ``scripts/validate_m3c_gate_driven.py`` builds a 9-branch M3C whose
arms are driven ENTIRELY by external gates (no internal modulation, no internal
balancing) and that the external thesis modulator regulates it: balanced phase
currents, the per-submodule capacitors equalised by the EXTERNAL sort-and-select
(the seeded intra-module spread collapsing — the headline of the "control is
external, model represents" paradigm), and bounded inter-module spread from the
external cost-function balancing.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.validate_m3c_gate_driven import (  # noqa: E402
    build_gate_driven_m3c, simulate_gate_driven_m3c)


def test_build_shape() -> None:
    model = build_gate_driven_m3c(f_out=45.0, dt=2.0e-5)
    assert len(model.arms) == 9
    assert set(model.branches) == {f"M_{X}{y}" for X in "ABC" for y in "abc"}
    # each arm carries six per-submodule capacitor states (no aggregate lump)
    for arm in model.arms.values():
        assert len(arm.v_C_per_sm) == 6


def test_external_gates_run_and_balance() -> None:
    """The whole control hierarchy is external; the arm only represents."""
    model = build_gate_driven_m3c(f_out=45.0, dt=1.0e-5, v_c0_spread=600.0)
    # the seeded intra-module spread is present before the run
    assert max(a.v_C_spread for a in model.arms.values()) > 400.0

    sim = simulate_gate_driven_m3c(model, t_end=0.04)

    import numpy as np
    t = sim["times"]
    sl = slice(len(t) // 2, None)

    def amp(s):
        return float(np.sqrt(2.0) * np.std(np.asarray(s)[sl]))

    in_amps = [amp(s) for s in sim["i_in"]]
    out_amps = [amp(s) for s in sim["i_out"]]
    assert all(70.0 < a < 170.0 for a in in_amps), in_amps
    assert all(80.0 < a < 200.0 for a in out_amps), out_amps

    vc = sim["v_c"]
    mean_end = float(np.mean(vc[-1]))
    assert 0.85 * 24000.0 < mean_end < 1.15 * 24000.0

    # Intra-module balancing — done EXTERNALLY by sort-and-select on the live
    # per-SM caps — collapses the seeded 600 V spread to a few volts.
    intra = float(np.max(sim["spread"][-1]))
    assert intra < 150.0, intra

    # Inter-module balancing (external Fast-SVM cost function) keeps the nine
    # branch caps bounded together (choppier than the smooth modal law).
    inter = float(np.max(vc[-1]) - np.min(vc[-1]))
    assert inter < 8000.0, inter


def test_arms_have_no_internal_modulation() -> None:
    """The gate-driven arm exposes per-SM caps + current but takes NO m_ref —
    all modulation/balancing is the external modulator's job."""
    model = build_gate_driven_m3c(f_out=45.0, dt=2.0e-5)
    arm = next(iter(model.arms.values()))
    assert not hasattr(arm, "m_b_fn")          # unlike the native L0-L3 arms
    assert hasattr(arm, "v_C_per_sm")           # exposes per-SM state instead
    assert callable(arm.gate_source)            # driven by external gates
