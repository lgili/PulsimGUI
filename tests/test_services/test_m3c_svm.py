"""Unit tests for the thesis-faithful M3C Fast-SVM modulator (pure Python)."""
from __future__ import annotations

import math

from pulsimgui.services.m3c_svm import (
    CostSelector,
    abc_from_lg,
    enumerate_connections,
    fast_svm_plane,
    lg_from_abc,
    module_voltages,
    tree_module_currents,
)


# --- non-orthogonal lgγ transform -----------------------------------------
def test_lg_round_trip() -> None:
    for va, vb, vc in [(1.0, -0.5, -0.5), (3.2, -1.1, 0.7), (0.0, 0.0, 0.0)]:
        vl, vg, vgam = lg_from_abc(va, vb, vc)
        ra, rb, rc = abc_from_lg(vl, vg, vgam)
        assert math.isclose(ra, va, abs_tol=1e-9)
        assert math.isclose(rb, vb, abs_tol=1e-9)
        assert math.isclose(rc, vc, abs_tol=1e-9)


# --- fast SVM in one plane -------------------------------------------------
def test_fast_svm_reconstructs_reference() -> None:
    """The three nearest vectors, duty-weighted, reproduce the reference, with
    all duties non-negative and summing to one (integer lattice vectors)."""
    refs = [(0.3, 0.4), (-1.7, 2.2), (2.9, -0.1), (0.6, 0.6), (-0.2, -0.9),
            (1.5, 1.5)]
    for vl, vg in refs:
        plane = fast_svm_plane(vl, vg)
        # lattice integer vectors
        for v in plane.vectors:
            assert v == (int(v[0]), int(v[1]))
        # duties valid
        assert all(d >= -1e-12 for d in plane.duties), plane.duties
        assert math.isclose(sum(plane.duties), 1.0, abs_tol=1e-9)
        # reconstruction
        al, ag = plane.average()
        assert math.isclose(al, vl, abs_tol=1e-9)
        assert math.isclose(ag, vg, abs_tol=1e-9)


def test_fast_svm_integer_reference_is_exact() -> None:
    """A reference already on a lattice point selects it with unit duty."""
    plane = fast_svm_plane(2.0, -1.0)
    al, ag = plane.average()
    assert math.isclose(al, 2.0) and math.isclose(ag, -1.0)


# --- connection model: 81 spanning trees of K3,3 ---------------------------
def test_enumerate_81_connections() -> None:
    conns = enumerate_connections()
    assert len(conns) == 81                          # spanning trees of K3,3
    for c in conns:
        assert len(c) == 5                           # exactly 5 conducting modules
        assert len(set(c)) == 5
        # every input phase and every output phase touched (spanning)
        assert {i for i, _ in c} == {0, 1, 2}
        assert {j for _, j in c} == {0, 1, 2}


def test_reduction_81_to_45() -> None:
    """The Etapa-3 smallest-in/smallest-out tie keeps exactly 45 connections,
    all containing that edge."""
    sel = CostSelector()
    v_in = (-2.0, 1.0, 1.0)        # smallest input phase = A (index 0)
    v_out = (1.0, -2.0, 1.0)       # smallest output phase = b (index 1)
    short, cands = sel.reduced_set(v_in, v_out)
    assert short == (0, 1)
    assert len(cands) == 45
    assert all(short in c for c in cands)


# --- module voltage mesh ---------------------------------------------------
def test_module_voltages_short_is_zero() -> None:
    v_in = (2.0, -1.0, -1.0)
    v_out = (1.0, 1.0, -2.0)
    short = (0, 2)                  # tie input A to output c
    vmod = module_voltages(v_in, v_out, short)
    assert len(vmod) == 9
    # shorted module M_Ac (index 0*3+2 = 2) is exactly 0 V
    assert math.isclose(vmod[2], 0.0, abs_tol=1e-9)
    # any module = v_in[i] - v_out[j] - (v_in[si]-v_out[sj])
    off = v_in[0] - v_out[2]
    for i in range(3):
        for j in range(3):
            assert math.isclose(vmod[3 * i + j], v_in[i] - v_out[j] - off,
                                abs_tol=1e-9)


# --- module current mesh ---------------------------------------------------
def test_module_currents_satisfy_kcl() -> None:
    """Per-module currents obey KCL: each input node sources its injected
    current through its conducting modules; each output node sinks its draw."""
    conns = enumerate_connections()
    i_in = (100.0, -40.0, -60.0)        # sums to 0
    i_out = (70.0, -30.0, -40.0)        # sums to 0
    for conn in conns[:20]:
        cur = tree_module_currents(conn, i_in, i_out)
        # KCL at each input node i: sum of its module currents = i_in[i]
        for i in range(3):
            s = sum(cur[(a, b)] for (a, b) in conn if a == i)
            assert math.isclose(s, i_in[i], abs_tol=1e-6), (conn, i, s)
        # KCL at each output node j: sum of currents in = i_out[j]
        for j in range(3):
            s = sum(cur[(a, b)] for (a, b) in conn if b == j)
            assert math.isclose(s, i_out[j], abs_tol=1e-6), (conn, j, s)


# --- Etapa 4 cost-function selection ---------------------------------------
def test_cost_selector_returns_valid_candidate() -> None:
    sel = CostSelector()
    v_in = (2.0, -1.0, -1.0)
    v_out = (1.0, 1.0, -2.0)
    i_in = (100.0, -50.0, -50.0)
    i_out = (60.0, -30.0, -30.0)
    vmod = [24000.0] * 9
    conn, short = sel.select(v_in, v_out, i_in, i_out, vmod)
    _, cands = sel.reduced_set(v_in, v_out)
    assert conn in cands
    assert short in conn


def test_cost_selector_prefers_charging_the_low_module() -> None:
    """With one module's cap sagging, the chosen connection routes current so
    its predicted ΔV reduces the spread (lower J than the worst candidate)."""
    sel = CostSelector(sn=6.0, capacitance=680e-6, ts=0.5e-3)
    v_in = (2.0, -1.0, -1.0)
    v_out = (1.0, 1.0, -2.0)
    i_in = (120.0, -60.0, -60.0)
    i_out = (80.0, -40.0, -40.0)
    vmod = [24000.0] * 9
    vmod[4] = 22000.0               # M_Bb sags 2 kV
    conn, _ = sel.select(v_in, v_out, i_in, i_out, vmod)

    # Recompute J for the chosen connection and confirm it is the minimum over
    # the candidate set (selection is a true argmin, not arbitrary).
    _, cands = sel.reduced_set(v_in, v_out)
    v_mean = sum(vmod) / 9.0
    eps = [vmod[k] - v_mean for k in range(9)]
    scale = sel.sn * sel.ts / sel.capacitance

    def jcost(c):
        cur = tree_module_currents(c, i_in, i_out)
        return sum((eps[3 * i + j] + scale * cur.get((i, j), 0.0)) ** 2
                   for i in range(3) for j in range(3))

    j_best = jcost(conn)
    assert j_best == min(jcost(c) for c in cands)
