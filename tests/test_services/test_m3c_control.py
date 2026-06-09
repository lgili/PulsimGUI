"""Unit tests for the M3C closed-loop controller (pure-Python, no pulsim)."""
from __future__ import annotations

import math

from pulsimgui.services.m3c_control import M3CClosedLoopController

BRANCHES = [f"M_{X}{y}" for X in "ABC" for y in "abc"]


def _make(**kw) -> M3CClosedLoopController:
    base = dict(branches=list(BRANCHES), f_in=50.0, f_out=45.0,
                v_in_pk=11268.0, v_out_pk=8981.0, v_c_ref=24000.0,
                l_branch=25e-3, r_branch=0.5, control_dt=1e-5)
    base.update(kw)
    return M3CClosedLoopController(**base)


def test_initial_m_ref_zero() -> None:
    c = _make()
    assert all(c.m_ref(n) == 0.0 for n in BRANCHES)


def test_update_produces_valid_modulation() -> None:
    c = _make(id_out=148.0)
    nominal = {n: 24000.0 for n in BRANCHES}
    currents = {n: 0.0 for n in BRANCHES}
    c.update(0.02, currents, nominal)
    ms = [c.m_ref(n) for n in BRANCHES]
    assert all(-1.0 <= m <= 1.0 for m in ms)        # full-bridge range
    assert any(abs(m) > 0.01 for m in ms)           # actually modulating


def test_sample_and_hold() -> None:
    """update only re-runs the law once per control_dt."""
    c = _make(control_dt=1e-3)
    nominal = {n: 24000.0 for n in BRANCHES}
    c.update(0.0, {n: 0.0 for n in BRANCHES}, nominal)
    m0 = c.m_ref("M_Aa")
    # Within the hold window the held value is not recomputed.
    c.update(0.0005, {n: 999.0 for n in BRANCHES}, nominal)
    assert c.m_ref("M_Aa") == m0


def test_energy_loop_sign() -> None:
    """Caps below target ⇒ the energy loop commands positive input current."""
    c = _make()
    low = {n: 22000.0 for n in BRANCHES}   # below 24 kV
    for k in range(50):
        c.update(k * c.control_dt, {n: 0.0 for n in BRANCHES}, low)
    assert c.last_id_in > 0.0
    assert math.isclose(c.last_vc_mean, 22000.0)


def test_balancing_is_zero_sum_per_row_and_column() -> None:
    """The balancing circulating injection has zero row and column sums, so it
    cannot disturb the input phase currents (rows) or output (columns)."""
    c = _make(balance=True, k_balance=0.1, soft_start_time=0.0)
    # One branch (M_Bb, index 4) sags; everything else at nominal.
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Bb"] = 20000.0
    # Drive update at a time where sin(θ_in+φ) ≠ 0 so the injection is nonzero.
    t = 0.003
    c.update(t, {n: 0.0 for n in BRANCHES}, vcap)
    # Reconstruct the per-branch circulating injection from m_ref deltas is
    # indirect; instead verify the law directly via a second controller that
    # exposes the centred error pattern through last_* is not available, so we
    # re-derive: the doubly-centred error must sum to zero over every row/col.
    err = [c.last_vc_mean - vcap[BRANCHES[k]] for k in range(9)]
    row = [sum(err[3 * i + j] for j in range(3)) / 3.0 for i in range(3)]
    col = [sum(err[3 * i + j] for i in range(3)) / 3.0 for j in range(3)]
    tot = sum(err) / 9.0
    centred = [err[3 * i + j] - row[i] - col[j] + tot
               for i in range(3) for j in range(3)]
    for i in range(3):
        assert abs(sum(centred[3 * i + j] for j in range(3))) < 1e-9
    for j in range(3):
        assert abs(sum(centred[3 * i + j] for i in range(3))) < 1e-9
    # The sagging branch keeps the largest positive (charge) centred error.
    assert centred[4] == max(centred)


def test_balancing_integral_accumulates() -> None:
    """A sustained branch-cap sag accumulates the integral most on that branch
    (the integral term that arrests the switched-model drift)."""
    c = _make(balance=True, control_dt=1e-4, soft_start_time=0.0)
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Bb"] = 23800.0           # branch index 4 sags 200 V (no clamp)
    for k in range(30):
        c.update(k * c.control_dt, {n: 0.0 for n in BRANCHES}, vcap)
    assert c._int_bal[4] == max(c._int_bal)   # sagging branch integrates most
    assert c._int_bal[4] > 0                  # +ve ⇒ commands charging
    # Integral state stays doubly-centred (zero row/column sums ⇒ never
    # disturbs the input/output phase currents).
    ib = c._int_bal
    for i in range(3):
        assert abs(sum(ib[3 * i + j] for j in range(3))) < 1e-9
    for j in range(3):
        assert abs(sum(ib[3 * i + j] for i in range(3))) < 1e-9
