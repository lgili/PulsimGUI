#!/usr/bin/env python3
"""Validation harness for the Modular Multilevel Matrix Converter (M3C).

Based on Luiz Carlos Gili, *"Contribuições Para o Conversor Modular Matricial
Multinível - M3C"* (Tese de doutorado, UFSC, 2024) — the M3C topology of
Figure 34 ("M3C com indutor") and the simulation parameters of Table 15
(p.134, "Conexão Genérica do M3C", both sides fed by three-phase sources).

Topology
--------
The M3C is a single-stage direct AC↔AC converter: a 3×3 matrix of NINE branches
(modules) directly meshing the three input phases A,B,C to the three output
phases a,b,c — no DC link. Branch ``M_Xy`` ties input phase X to output phase y::

          out a      out b      out c
   in A   M_Aa       M_Ab       M_Ac
   in B   M_Ba       M_Bb       M_Bc
   in C   M_Ca       M_Cb       M_Cc

Each branch is a chain of N series full-bridge submodules (clamped-capacitor
H-bridge cells, Fig 35) in series with a branch inductor (the "indutores
adicionais" of Fig 15/34). The full bridge produces a BIPOLAR branch voltage
(±v_C), which the matrix needs because a branch synthesizes v_in_X − v_out_y
(a bipolar quantity). Input phase X feeds the three branches in its row; output
phase y collects the three branches in its column. The per-branch inductor is
also what gives the nine branch currents independent state (and breaks the
voltage-source loops an ideal-source matrix would otherwise form).

How it is modeled here
----------------------
Each of the 9 branches is a pulsim L0 *average* MMC arm
(``add_mmc_arm_average``, ``sm_type="full_bridge"``) in series with a branch
inductor. Both converter sides are stiff three-phase sine sources (Sistema 1 =
grid, Sistema 2 = load-side grid), exactly like Fig 63.

This is the OPEN-LOOP, feed-forward validation — the M3C analogue of example 24
for the MMC. It establishes the topology and the AC↔AC voltage/current synthesis
in pulsim BEFORE the full closed-loop SVM + capacitor-balancing control of the
thesis is ported. Each branch modulation is the feed-forward::

    m_Xy(t) = ( v_in_X(t) − v_out_y(t) − L_b·di_Xy/dt ) / v_C_live

normalized by the LIVE branch capacitor voltage so the synthesized branch
voltage v_arm = m·v_C exactly equals the KVL target regardless of capacitor
drift; with matched initial inductor currents this drives the desired balanced
branch current ``i_Xy = I_in_X/3 + I_out_y/3`` (the minimal-circulating
distribution that makes the row sums the input phase currents and the column
sums the output phase currents). Input currents are in phase with the input
voltages (unity PF, grid supplying) and output currents in phase with the
output voltages (load-side grid absorbing), so power flows input→output near
the rated level.

What this validates / open-loop limits
--------------------------------------
Validated: the 9-branch 3×3 mesh is a well-posed circuit in pulsim, the
full-bridge arms synthesize the bipolar branch voltages, and the feed-forward
produces balanced sinusoidal currents on BOTH sides at their (different) input
and output frequencies with power flowing input→output. Because there is no
current feedback nor capacitor-balancing control yet, two open-loop residuals
remain (and are reported): the per-branch capacitor voltages drift apart
(no balancing) and, lacking a current loop, the input power settles a little
below the output (the caps supply the difference). Both are exactly what the
thesis's closed-loop current + SVM capacitor-balancing control resolve — the
next step after this topology validation.

Run::

    PYTHONPATH=src python3 scripts/validate_m3c.py            # default f_out=45 Hz
    PYTHONPATH=src python3 scripts/validate_m3c.py --f-out 30 --plot /tmp/m3c.png
"""
from __future__ import annotations

import argparse
import math
from dataclasses import dataclass, field

import numpy as np

import pulsim as p
from pulsim import mmc
from pulsim.mmc import MmcArmAverageParams

# --- Thesis Table 15 parameters --------------------------------------------
P_RATED = 2.0e6          # converter rated power [VA]
N_SM = 6                 # submodules per branch
V_CAP_SM = 4.0e3         # capacitor voltage per submodule [V]
C_SM = 680.0e-6          # submodule capacitance [F] (Table prints "µH"; it is µF)
V_C_AGG = N_SM * V_CAP_SM  # aggregate branch capacitor voltage = 24 kV
L_BRANCH = 25.0e-3       # per-branch / filter inductance [H] (Sistema 1&2: 25 mH)

V_IN_LINE = 13.8e3       # Sistema 1 (input grid) line voltage [V]
F_IN = 50.0              # Sistema 1 frequency [Hz] (held fixed)
V_OUT_LINE = 11.0e3      # Sistema 2 (output grid) line voltage [V]
# Sistema 2 frequency is swept over {5, 30, 45, 55} Hz in the thesis.

INPUT_PHASES = ("A", "B", "C")
OUTPUT_PHASES = ("a", "b", "c")
# 120°-apart phase angles, in phase order A/a=0, B/b=−120°, C/c=+120°.
PHASE_RAD = {0: 0.0, 1: -2.0 * math.pi / 3.0, 2: +2.0 * math.pi / 3.0}


def _peak_phase(v_line: float) -> float:
    """Peak phase voltage from an RMS line voltage."""
    return v_line * math.sqrt(2.0) / math.sqrt(3.0)


@dataclass
class M3CModel:
    builder: object
    arms: list = field(default_factory=list)
    branch_inductors: dict = field(default_factory=dict)  # (i,j) -> name
    meta: dict = field(default_factory=dict)


def build_m3c(f_out: float = 45.0, dt: float = 1.0e-5) -> M3CModel:
    """Build the 9-branch M3C between two 3-phase sources (thesis Fig 34/63)."""
    w_in = 2.0 * math.pi * F_IN
    w_out = 2.0 * math.pi * f_out
    v_in_pk = _peak_phase(V_IN_LINE)
    v_out_pk = _peak_phase(V_OUT_LINE)
    # Balanced 3φ power P = (3/2)·V_pk·I_pk  →  I_pk = 2P/(3 V_pk).
    i_in_pk = 2.0 * P_RATED / (3.0 * v_in_pk)
    i_out_pk = 2.0 * P_RATED / (3.0 * v_out_pk)

    b = p.CircuitBuilder()
    b.ground()

    # Stiff 3φ sine sources (grounded neutrals): inputs drive the row nodes,
    # outputs drive the column nodes. v(t) = V_pk·sin(ω t + θ).
    for i, X in enumerate(INPUT_PHASES):
        b.add_sine_voltage_source(f"V_in_{X}", f"in_{X}", "0",
                                  0.0, v_in_pk, F_IN, PHASE_RAD[i])
    for j, y in enumerate(OUTPUT_PHASES):
        b.add_sine_voltage_source(f"V_out_{y}", f"out_{y}", "0",
                                  0.0, v_out_pk, f_out, PHASE_RAD[j])

    def v_in(i, t):
        return v_in_pk * math.sin(w_in * t + PHASE_RAD[i])

    def v_out(j, t):
        return v_out_pk * math.sin(w_out * t + PHASE_RAD[j])

    def i_branch(i, j, t):
        # Balanced minimal-circulating distribution.
        ii = i_in_pk * math.sin(w_in * t + PHASE_RAD[i])
        io = i_out_pk * math.sin(w_out * t + PHASE_RAD[j])
        return (ii + io) / 3.0

    def di_branch(i, j, t):
        di_in = w_in * i_in_pk * math.cos(w_in * t + PHASE_RAD[i])
        di_out = w_out * i_out_pk * math.cos(w_out * t + PHASE_RAD[j])
        return (di_in + di_out) / 3.0

    model = M3CModel(builder=b)
    for i, X in enumerate(INPUT_PHASES):
        for j, y in enumerate(OUTPUT_PHASES):
            # Feed-forward branch modulation, normalized by the LIVE branch
            # capacitor voltage so v_arm = m·v_C exactly equals the KVL target
            #     v_in_X − v_out_y − L_b·di_ref/dt
            # regardless of (open-loop) capacitor drift. ``box`` defers reading
            # the arm's v_C until simulation time (the arm object does not exist
            # yet at closure-creation).
            box: list = []

            def m_ref(t, _i=i, _j=j, _box=box):
                vc = _box[0].v_C if _box else V_C_AGG
                target = v_in(_i, t) - v_out(_j, t) - L_BRANCH * di_branch(_i, _j, t)
                return target / max(vc, 1.0)

            arm = mmc.add_mmc_arm_average(
                b, name=f"M_{X}{y}", node_a=f"in_{X}", node_b=f"mid_{X}{y}",
                params=MmcArmAverageParams(n_sm=N_SM, c_sm=C_SM, v_c0=V_C_AGG,
                                           sm_type="full_bridge"),
                m_b=m_ref,
            )
            box.append(arm)
            model.arms.append(arm)
            lname = f"Lb_{X}{y}"
            b.add_inductor(lname, f"mid_{X}{y}", f"out_{y}",
                           L_BRANCH, i_branch(i, j, 0.0))
            model.branch_inductors[(i, j)] = lname

    model.meta = dict(
        f_in=F_IN, f_out=f_out, dt=dt, v_in_pk=v_in_pk, v_out_pk=v_out_pk,
        i_in_pk=i_in_pk, i_out_pk=i_out_pk, v_c_agg=V_C_AGG,
    )
    return model


def simulate_m3c(model: M3CModel, t_end: float = 0.12) -> dict:
    """Run the transient and record per-branch v_C + node/branch traces."""
    b = model.builder
    dt = model.meta["dt"]
    step_obs, b_extra = mmc.make_mmc_arms_observer(b, model.arms, dt=dt)

    rec_t: list[float] = []
    rec_vc: list[list[float]] = []

    def observer(t, x):
        step_obs(t, x)
        rec_t.append(t)
        rec_vc.append([float(a.v_C) for a in model.arms])

    result = p.simulate(b, t_end=t_end, dt=dt,
                        b_extra_fn=b_extra, step_observer=observer)

    times = np.asarray(result.times)
    # Branch currents (inductor currents): i_Xy flows mid→out (= branch current).
    branch_i = {ij: np.asarray(result.i(name))
                for ij, name in model.branch_inductors.items()}
    # Input phase current = row sum; output phase current = column sum.
    i_in = [branch_i[(i, 0)] + branch_i[(i, 1)] + branch_i[(i, 2)]
            for i in range(3)]
    i_out = [branch_i[(0, j)] + branch_i[(1, j)] + branch_i[(2, j)]
             for j in range(3)]
    v_in = [np.asarray(result.v(f"in_{X}")) for X in INPUT_PHASES]
    v_out = [np.asarray(result.v(f"out_{y}")) for y in OUTPUT_PHASES]
    v_c = np.asarray(rec_vc)  # [steps, 9]

    return dict(times=times, i_in=i_in, i_out=i_out, v_in=v_in, v_out=v_out,
                v_c=v_c, vc_t=np.asarray(rec_t), branch_i=branch_i,
                result=result)


def analyze(model: M3CModel, sim: dict) -> dict:
    """Compute validation metrics and print a report."""
    m = model.meta
    t = sim["times"]
    half = len(t) // 2          # steady-state window = second half
    sl = slice(half, None)

    def amp(sig):
        return float(np.sqrt(2.0) * np.std(np.asarray(sig)[sl]))

    in_amps = [amp(s) for s in sim["i_in"]]
    out_amps = [amp(s) for s in sim["i_out"]]

    vi, ii = sim["v_in"], sim["i_in"]
    vo, io = sim["v_out"], sim["i_out"]
    p_in = vi[0] * ii[0] + vi[1] * ii[1] + vi[2] * ii[2]
    p_out = vo[0] * io[0] + vo[1] * io[1] + vo[2] * io[2]
    p_in_mean = float(np.mean(p_in[sl]))
    p_out_mean = float(np.mean(p_out[sl]))

    vc = sim["v_c"]
    vc_drift = np.abs(vc[-1] - vc[0]) / m["v_c_agg"] * 100.0
    metrics = dict(
        in_amps=in_amps, out_amps=out_amps,
        i_in_pk_ref=m["i_in_pk"], i_out_pk_ref=m["i_out_pk"],
        p_in_mean=p_in_mean, p_out_mean=p_out_mean,
        vc_mean_start=float(np.mean(vc[0])), vc_mean_end=float(np.mean(vc[-1])),
        vc_max_drift_pct=float(np.max(vc_drift)),
    )

    print(f"M3C validation — f_in={m['f_in']:.0f} Hz, f_out={m['f_out']:.0f} Hz, "
          f"{t[-1]*1e3:.0f} ms @ dt={m['dt']*1e6:.0f} µs")
    print(f"  input  current amplitude per phase: "
          f"{[f'{a:.1f}' for a in in_amps]} A   (ref {m['i_in_pk']:.1f} A)")
    print(f"  output current amplitude per phase: "
          f"{[f'{a:.1f}' for a in out_amps]} A   (ref {m['i_out_pk']:.1f} A)")
    print(f"  power: P_in={p_in_mean/1e6:.3f} MW   P_out={p_out_mean/1e6:.3f} MW   "
          f"(rated {P_RATED/1e6:.1f} MVA)")
    print(f"  branch v_C: mean {metrics['vc_mean_start']/1e3:.2f} kV → "
          f"{metrics['vc_mean_end']/1e3:.2f} kV   "
          f"(max drift {metrics['vc_max_drift_pct']:.1f}% over window)")
    print("  note: open-loop feed-forward only — the v_C drift and the small "
          "P_in<P_out gap are\n        the residuals the thesis's closed-loop "
          "current + capacitor-balancing control fixes.")
    return metrics


def plot(model: M3CModel, sim: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = sim["times"] * 1e3
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    for k, X in enumerate(INPUT_PHASES):
        ax[0, 0].plot(t, sim["i_in"][k], label=f"I_{X}")
    ax[0, 0].set_title(f"Input currents ({model.meta['f_in']:.0f} Hz)")
    ax[0, 0].set_ylabel("A"); ax[0, 0].legend(loc="upper right"); ax[0, 0].grid(True)
    for k, y in enumerate(OUTPUT_PHASES):
        ax[0, 1].plot(t, sim["i_out"][k], label=f"I_{y}")
    ax[0, 1].set_title(f"Output currents ({model.meta['f_out']:.0f} Hz)")
    ax[0, 1].set_ylabel("A"); ax[0, 1].legend(loc="upper right"); ax[0, 1].grid(True)
    tc = sim["vc_t"] * 1e3
    for k in range(9):
        ax[1, 0].plot(tc, sim["v_c"][:, k] / 1e3, lw=0.8)
    ax[1, 0].set_title("Branch capacitor voltages (9 branches, open-loop drift)")
    ax[1, 0].set_ylabel("kV"); ax[1, 0].set_xlabel("ms"); ax[1, 0].grid(True)
    for k, X in enumerate(INPUT_PHASES):
        ax[1, 1].plot(t, sim["v_in"][k] / 1e3, label=f"V_{X}")
    ax[1, 1].set_title("Input phase voltages")
    ax[1, 1].set_ylabel("kV"); ax[1, 1].set_xlabel("ms")
    ax[1, 1].legend(loc="upper right"); ax[1, 1].grid(True)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    print(f"  saved plot → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Validate the M3C in pulsim.")
    ap.add_argument("--f-out", type=float, default=45.0,
                    help="Sistema 2 output frequency [Hz] (thesis sweep: 5/30/45/55)")
    ap.add_argument("--t-end", type=float, default=0.12, help="sim duration [s]")
    ap.add_argument("--dt", type=float, default=1.0e-5, help="time step [s]")
    ap.add_argument("--plot", type=str, default=None, help="save a PNG to this path")
    args = ap.parse_args()

    model = build_m3c(f_out=args.f_out, dt=args.dt)
    sim = simulate_m3c(model, t_end=args.t_end)
    analyze(model, sim)
    if args.plot:
        plot(model, sim, args.plot)


if __name__ == "__main__":
    main()
