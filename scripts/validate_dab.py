#!/usr/bin/env python3
"""Dual Active Bridge (DAB) — kernel validation against the phase-shift law.

Two full bridges (8 switches) around an HF transformer + series (leakage)
inductor; single-phase-shift modulation. The classic power-transfer law:

    P = (V1 · V2') · φ(1 − φ/π) / (2π · f · L)        (V2' = n·V2)

Eight switches but only TWO distinct masks per period (diagonal pairs), so
the PWL cache builds instantly — this is the topology gate-level simulation
is cheap for, unlike the 2^N matrix-converter case.

Run::  PYTHONPATH=src python3 scripts/validate_dab.py
"""
from __future__ import annotations

import math

import numpy as np

import pulsim as p

V1 = 400.0          # input bus [V]
V2 = 200.0          # output bus [V]
N_RATIO = 2.0       # transformer N1/N2 (400:200)
F_SW = 20e3         # switching frequency [Hz]
L_LK = 60e-6        # series (leakage) inductance [H]
PHI = math.pi / 4   # phase shift [rad] — forward power


def build_dab():
    b = p.CircuitBuilder()
    b.ground()
    b.add_voltage_source("Vin", "vp", "0", V1)
    # output bus held by a stiff source (power sink) referenced to ground —
    # the two bridges only share the magnetic link, but a common reference
    # keeps the MNA well-posed without affecting the differential physics.
    b.add_voltage_source("Vout", "vs", "0", V2)

    g_on, g_off = 1e3, 1e-9
    # primary bridge legs: vp → a1/a2 → 0
    for leg, mid in (("A", "pa"), ("B", "pb")):
        b.add_switch(f"S{leg}h", "vp", mid, g_on, g_off)
        b.add_switch(f"S{leg}l", mid, "0", g_on, g_off)
    # secondary bridge legs: vs → b1/b2 → 0
    for leg, mid in (("C", "sa"), ("D", "sb")):
        b.add_switch(f"S{leg}h", "vs", mid, g_on, g_off)
        b.add_switch(f"S{leg}l", mid, "0", g_on, g_off)

    # HF link: pa →L→ tx_p, transformer tx_p/pb : sa/sb
    b.add_inductor("Llk", "pa", "txp", L_LK, 0.0)
    b.add_transformer("TX", "txp", "pb", "sa", "sb",
                      10e-3, 10e-3 / N_RATIO**2, 1.0)
    return b


def switch_fn_factory(b, phi: float):
    idx = {n: b.switch_index_of(n) for n in
           ("SAh", "SAl", "SBh", "SBl", "SCh", "SCl", "SDh", "SDl")}
    nsw = b.graph.num_switches
    t_sw = 1.0 / F_SW

    def fn(t: float):
        m = p.SwitchStateMask(nsw)
        # primary square wave: first half SAh+SBl (v_ab=+V1), second SAl+SBh
        ph_p = (t / t_sw) % 1.0
        if ph_p < 0.5:
            m.set(idx["SAh"], True); m.set(idx["SBl"], True)
        else:
            m.set(idx["SAl"], True); m.set(idx["SBh"], True)
        # secondary lags by phi
        ph_s = ((t - phi / (2 * math.pi) * t_sw) / t_sw) % 1.0
        if ph_s < 0.5:
            m.set(idx["SCh"], True); m.set(idx["SDl"], True)
        else:
            m.set(idx["SCl"], True); m.set(idx["SDh"], True)
        return m
    return fn


def run(phi: float = PHI, t_end: float = 4e-3):
    b = build_dab()
    res = p.simulate(b, t_end=t_end, dt=2e-7,
                     switch_fn=switch_fn_factory(b, phi))
    t = np.asarray(res.times)
    half = len(t) // 2
    # input power: source current × V1 (source current sign: into circuit)
    i_in = np.asarray(res.i("Vin"))[half:]
    p_in = -float(np.mean(i_in)) * V1
    p_theory = (V1 * V2 * N_RATIO) * phi * (1 - phi / math.pi) / (
        2 * math.pi * F_SW * L_LK)
    return p_in, p_theory


if __name__ == "__main__":
    p_sim, p_th = run()
    err = 100 * abs(p_sim - p_th) / p_th
    print(f"DAB φ=45°: P_sim={p_sim:.0f} W  P_theory={p_th:.0f} W  "
          f"err={err:.1f} %")
