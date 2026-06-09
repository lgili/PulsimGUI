"""Unit tests for the thesis Fast-SVM M3C controller (cost-function balancing).

Verifies the SVM cost-function balancing drop-in keeps every structural
guarantee of the modal default law — the circulating injection has zero
input/output-phase sums, the selected connection is a valid spanning tree, and
the selection is a genuine cost argmin — while regulating valid modulation.
"""
from __future__ import annotations

import math

from pulsimgui.services.m3c_control import M3CSvmController
from pulsimgui.services.m3c_svm import tree_module_currents

BRANCHES = [f"M_{X}{y}" for X in "ABC" for y in "abc"]


def _make(**kw) -> M3CSvmController:
    base = dict(branches=list(BRANCHES), f_in=50.0, f_out=45.0,
                v_in_pk=11268.0, v_out_pk=8981.0, v_c_ref=24000.0,
                l_branch=25e-3, r_branch=0.5, control_dt=1e-5,
                id_out=148.0, soft_start_time=0.0, f_switch=2000.0)
    base.update(kw)
    return M3CSvmController(**base)


def test_builds_and_modulates() -> None:
    c = _make()
    assert all(c.m_ref(n) == 0.0 for n in BRANCHES)
    nominal = {n: 24000.0 for n in BRANCHES}
    c.update(0.02, {n: 0.0 for n in BRANCHES}, nominal)
    ms = [c.m_ref(n) for n in BRANCHES]
    assert all(-1.0 <= m <= 1.0 for m in ms)
    assert any(abs(m) > 0.01 for m in ms)


def test_selected_connection_is_valid_tree() -> None:
    c = _make()
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Bb"] = 22000.0
    # nonzero branch currents so the cost function differentiates candidates
    cur = {n: 50.0 * math.sin(0.7 * k) for k, n in enumerate(BRANCHES)}
    c.update(0.004, cur, vcap)
    conn = c.last_connection
    assert len(conn) == 5
    assert {i for i, _ in conn} == {0, 1, 2}      # spanning all input phases
    assert {j for _, j in conn} == {0, 1, 2}      # spanning all output phases
    assert c.last_short in conn                    # Etapa-3 short edge kept


def test_circulating_injection_zero_phase_sums() -> None:
    """The SVM circulating injection must not disturb the regulated input
    (row) or output (column) phase currents. The exact zero-sum holds for
    physically consistent (KCL-balanced) terminal currents, so seed a balanced
    branch-current distribution ``(I_in_X + I_out_y)/3``."""
    c = _make()
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Aa"] = 22500.0
    i_in = (100.0, -40.0, -60.0)        # sums to 0
    i_out = (50.0, -20.0, -30.0)        # sums to 0
    cur = {BRANCHES[3 * i + j]: (i_in[i] + i_out[j]) / 3.0
           for i in range(3) for j in range(3)}
    c.update(0.004, cur, vcap)
    ic = c.last_i_circ
    assert any(abs(v) > 1e-9 for v in ic)
    assert max(abs(v) for v in ic) < c.i_circ_max      # unsaturated regime
    for i in range(3):
        assert abs(sum(ic[3 * i + j] for j in range(3))) < 1e-6
    for j in range(3):
        assert abs(sum(ic[3 * i + j] for i in range(3))) < 1e-6


def test_connection_held_over_switching_period() -> None:
    """The connection is re-selected once per Ts (held between), per the
    thesis; within one Ts it does not change."""
    c = _make(f_switch=2000.0)          # Ts = 0.5 ms
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Cc"] = 21000.0
    cur = {n: 60.0 * math.sin(0.3 * k) for k, n in enumerate(BRANCHES)}
    c.update(0.0040, cur, vcap)
    first = c.last_connection
    c.update(0.0041, cur, vcap)         # +0.1 ms < Ts ⇒ same connection
    assert c.last_connection == first


def test_selection_is_true_cost_argmin() -> None:
    c = _make()
    vcap = {n: 24000.0 for n in BRANCHES}
    vcap["M_Bb"] = 21500.0
    cur = {n: 55.0 * math.sin(0.4 * k + 0.2) for k, n in enumerate(BRANCHES)}
    c.update(0.006, cur, vcap)
    conn = c.last_connection
    vc = [vcap[n] for n in BRANCHES]
    ib = [cur[n] for n in BRANCHES]
    i_in = tuple(sum(ib[3 * i + j] for j in range(3)) for i in range(3))
    i_out = tuple(sum(ib[3 * i + j] for i in range(3)) for j in range(3))
    _, cands = c._cost.reduced_set(
        tuple(c.v_in_pk * math.sin(2 * math.pi * c.f_in * 0.006
                                   + off) for off in (0, -2.094, 2.094)),
        tuple(c.v_out_pk * math.sin(2 * math.pi * c.f_out * 0.006
                                    + off) for off in (0, -2.094, 2.094)))
    v_mean = sum(vc) / 9.0
    eps = [vc[k] - v_mean for k in range(9)]
    scale = c._cost.sn * c._cost.ts / c._cost.capacitance

    def jcost(cn):
        cc = tree_module_currents(cn, i_in, i_out)
        return sum((eps[3 * i + j] + scale * cc.get((i, j), 0.0)) ** 2
                   for i in range(3) for j in range(3))

    assert jcost(conn) == min(jcost(cn) for cn in cands)
