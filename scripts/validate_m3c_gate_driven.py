#!/usr/bin/env python3
"""Gate-driven M3C — the thesis modulation runs FULLY EXTERNAL, model represents.

Same 9-branch 3×3 M3C topology as ``scripts/validate_m3c.py`` (Gili, UFSC 2024,
Fig 34 / Table 15), but every branch is a gate-driven arm
(:mod:`pulsimgui.services.gate_driven_arm`) instead of a native L0-L3 arm: the
arm has NO internal modulation and NO internal balancing — it just integrates
each submodule capacitor under the insertion vector it is handed.

All the control is external, in :class:`M3CSvmGateModulator`, exactly the
HIL/Simulink workflow ("I feed the gates, the model represents"):

* **Etapas 1-4** — :class:`M3CSvmController` (dq energy + per-branch current
  loops + Fast-SVM cost-function inter-module balancing) → per-branch ``m_ref``;
* **Etapa 3/6** — level quantisation + carrier PWM → number of inserted SMs;
* **Etapa 5** — external sort-and-select on each arm's live per-SM capacitors →
  WHICH submodules insert (intra-module balancing).

So both balancing layers live in the controller and the arm is a passive
multilevel capacitor network. Runs at behavioural speed (no gate-level MNA
switches) — the same shortcut that lets Simulink/PLECS simulate this at all.

Run::

    PYTHONPATH=src python3 scripts/validate_m3c_gate_driven.py
    PYTHONPATH=src python3 scripts/validate_m3c_gate_driven.py --f-out 30 --plot /tmp/g.png
"""
from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import pulsim as p

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pulsimgui.services.gate_driven_arm import (  # noqa: E402
    GateDrivenArmParams, add_gate_driven_arm, make_gate_driven_arm_observers)
from pulsimgui.services.m3c_control import M3CSvmController  # noqa: E402
from pulsimgui.services.m3c_gate_modulator import (  # noqa: E402
    M3CSvmGateModulator)
from scripts.validate_m3c import (  # noqa: E402
    C_SM, F_IN, INPUT_PHASES, L_BRANCH, N_SM, OUTPUT_PHASES, P_RATED,
    PHASE_RAD, V_C_AGG, V_CAP_SM, V_IN_LINE, V_OUT_LINE, _peak_phase)

R_BRANCH = 0.5            # per-branch damping resistance [Ω]


@dataclass
class GateM3CModel:
    builder: object
    arms: dict = field(default_factory=dict)         # name -> GateDrivenArm
    modulator: object = None
    branches: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def build_gate_driven_m3c(f_out: float = 45.0, dt: float = 1.0e-5,
                          v_c0_spread: float = 0.0) -> GateM3CModel:
    """Build the gate-driven 9-branch M3C + its external SVM gate modulator.

    ``v_c0_spread`` seeds an initial per-submodule imbalance (V) so the EXTERNAL
    sort-and-select can be seen removing it."""
    v_in_pk = _peak_phase(V_IN_LINE)
    v_out_pk = _peak_phase(V_OUT_LINE)
    i_in_pk = 2.0 * P_RATED / (3.0 * v_in_pk)
    i_out_pk = 2.0 * P_RATED / (3.0 * v_out_pk)

    b = p.CircuitBuilder()
    b.ground()
    for i, X in enumerate(INPUT_PHASES):
        b.add_sine_voltage_source(f"V_in_{X}", f"in_{X}", "0",
                                  0.0, v_in_pk, F_IN, PHASE_RAD[i])
    for j, y in enumerate(OUTPUT_PHASES):
        b.add_sine_voltage_source(f"V_out_{y}", f"out_{y}", "0",
                                  0.0, v_out_pk, f_out, PHASE_RAD[j])

    branches = [f"M_{X}{y}" for X in INPUT_PHASES for y in OUTPUT_PHASES]
    controller = M3CSvmController(
        branches=branches, f_in=F_IN, f_out=f_out,
        v_in_pk=v_in_pk, v_out_pk=v_out_pk, v_c_ref=V_C_AGG,
        l_branch=L_BRANCH, r_branch=R_BRANCH, id_out=i_out_pk,
        control_dt=dt, soft_start_time=1.0e-2, f_switch=2000.0,
        svm_capacitance=C_SM, svm_sn=float(N_SM))
    modulator = M3CSvmGateModulator(controller=controller, branches=branches,
                                    f_carrier=2000.0)
    gsrc = modulator.gate_source()

    model = GateM3CModel(builder=b, modulator=modulator, branches=branches)
    for i, X in enumerate(INPUT_PHASES):
        for j, y in enumerate(OUTPUT_PHASES):
            name = f"M_{X}{y}"
            # seed alternating per-SM imbalance around the 4 kV nominal
            seed = ([V_CAP_SM + (1 if (k % 2 == 0) else -1) * 0.5 * v_c0_spread
                     for k in range(N_SM)] if v_c0_spread > 0 else None)
            arm = add_gate_driven_arm(
                b, name=name, node_a=f"in_{X}", node_b=f"mid_{name}",
                params=GateDrivenArmParams(n_sm=N_SM, c_sm=C_SM, v_c0=V_CAP_SM,
                                           sm_type="full_bridge"),
                gate_source=gsrc, v_c0_per_sm=seed)
            model.arms[name] = arm
            b.add_resistor(f"Rb_{name}", f"mid_{name}", f"rl_{name}", R_BRANCH)
            i0 = (i_in_pk * math.sin(PHASE_RAD[i])
                  + i_out_pk * math.sin(PHASE_RAD[j])) / 3.0
            b.add_inductor(f"Lb_{name}", f"rl_{name}", f"out_{y}", L_BRANCH, i0)

    model.meta = dict(f_in=F_IN, f_out=f_out, dt=dt, v_in_pk=v_in_pk,
                      v_out_pk=v_out_pk, i_in_pk=i_in_pk, i_out_pk=i_out_pk,
                      v_c_agg=V_C_AGG)
    return model


def simulate_gate_driven_m3c(model: GateM3CModel, t_end: float = 0.08) -> dict:
    """Run the transient driving the arms entirely from external gates."""
    b = model.builder
    dt = model.meta["dt"]
    arm_names = model.branches
    arms = [model.arms[n] for n in arm_names]
    arm_step, b_extra = make_gate_driven_arm_observers(b, arms, dt=dt)
    src_idx = {n: b.pool.branch_var_id_for_source(model.arms[n].source_branch_id,
                                                  b.graph) for n in arm_names}

    rec_t: list[float] = []
    rec_vc: list[list[float]] = []
    rec_spread: list[list[float]] = []
    rec_vb: list[float] = []          # M_Aa switched arm voltage (bipolar)

    def observer(t, x):
        currents = {n: float(x[src_idx[n]]) for n in arm_names}
        vcap = {n: model.arms[n].v_C for n in arm_names}
        model.modulator.update(t, currents, vcap)   # Etapas 1-4 (external)
        arm_step(t, x)                                # caps integrate under gates
        rec_t.append(t)
        rec_vc.append([model.arms[n].v_C for n in arm_names])
        rec_spread.append([model.arms[n].v_C_spread for n in arm_names])
        rec_vb.append(model.arms["M_Aa"].v_b)

    result = p.simulate(b, t_end=t_end, dt=dt, b_extra_fn=b_extra,
                        step_observer=observer)

    times = np.asarray(result.times)
    branch_i = {(i, j): np.asarray(result.i(f"Lb_M_{X}{y}"))
                for i, X in enumerate(INPUT_PHASES)
                for j, y in enumerate(OUTPUT_PHASES)}
    i_in = [branch_i[(i, 0)] + branch_i[(i, 1)] + branch_i[(i, 2)]
            for i in range(3)]
    i_out = [branch_i[(0, j)] + branch_i[(1, j)] + branch_i[(2, j)]
             for j in range(3)]
    return dict(times=times, i_in=i_in, i_out=i_out,
                v_c=np.asarray(rec_vc), vc_t=np.asarray(rec_t),
                spread=np.asarray(rec_spread), vb_aa=np.asarray(rec_vb),
                result=result)


def analyze(model: GateM3CModel, sim: dict) -> dict:
    m = model.meta
    t = sim["times"]
    sl = slice(len(t) // 2, None)

    def amp(s):
        return float(np.sqrt(2.0) * np.std(np.asarray(s)[sl]))

    in_amps = [amp(s) for s in sim["i_in"]]
    out_amps = [amp(s) for s in sim["i_out"]]
    vc = sim["v_c"]
    inter_spread = float(np.max(vc[-1]) - np.min(vc[-1]))
    intra_spread = float(np.max(sim["spread"][-1]))
    metrics = dict(in_amps=in_amps, out_amps=out_amps,
                   vc_mean_end=float(np.mean(vc[-1])),
                   inter_module_spread=inter_spread,
                   intra_module_spread=intra_spread)
    print(f"gate-driven M3C — f_in={m['f_in']:.0f} Hz, f_out={m['f_out']:.0f} Hz, "
          f"{t[-1]*1e3:.0f} ms @ dt={m['dt']*1e6:.0f} µs   (control 100% external)")
    print(f"  input  current per phase: {[f'{a:.0f}' for a in in_amps]} A "
          f"(ref {m['i_in_pk']:.0f})")
    print(f"  output current per phase: {[f'{a:.0f}' for a in out_amps]} A "
          f"(ref {m['i_out_pk']:.0f})")
    print(f"  branch cap mean: {metrics['vc_mean_end']/1e3:.2f} kV   "
          f"inter-module spread: {inter_spread/1e3:.2f} kV   "
          f"intra-module spread: {intra_spread:.0f} V")
    return metrics


def plot(model: GateM3CModel, sim: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = sim["times"] * 1e3
    tc = sim["vc_t"] * 1e3
    fig, ax = plt.subplots(2, 3, figsize=(16, 7))
    for k, X in enumerate(INPUT_PHASES):
        ax[0, 0].plot(t, sim["i_in"][k], label=f"I_{X}")
    ax[0, 0].set_title("Input currents (50 Hz)"); ax[0, 0].set_ylabel("A")
    ax[0, 0].legend(loc="upper right"); ax[0, 0].grid(True)
    for k, y in enumerate(OUTPUT_PHASES):
        ax[0, 1].plot(t, sim["i_out"][k], label=f"I_{y}")
    ax[0, 1].set_title("Output currents (45 Hz)"); ax[0, 1].set_ylabel("A")
    ax[0, 1].legend(loc="upper right"); ax[0, 1].grid(True)
    ax[0, 2].plot(tc, sim["vb_aa"] / 1e3, lw=0.6, color="#c0392b")
    ax[0, 2].set_title("Branch M_Aa voltage (switched, bipolar full-bridge)")
    ax[0, 2].set_ylabel("kV"); ax[0, 2].set_xlabel("ms"); ax[0, 2].grid(True)
    for k in range(9):
        ax[1, 0].plot(tc, sim["v_c"][:, k] / 1e3, lw=0.8)
    ax[1, 0].set_title("Branch cap voltages (inter-module, cost function)")
    ax[1, 0].set_ylabel("kV"); ax[1, 0].set_xlabel("ms"); ax[1, 0].grid(True)
    for k in range(9):
        ax[1, 1].plot(tc, sim["spread"][:, k], lw=0.8)
    ax[1, 1].set_title("Submodule spread (intra, ext. sort-and-select)")
    ax[1, 1].set_ylabel("V"); ax[1, 1].set_xlabel("ms"); ax[1, 1].grid(True)
    ax[1, 2].axis("off")
    ax[1, 2].text(0.0, 0.5,
                  "Gate-driven M3C\n\nControl 100% EXTERNAL:\n"
                  "• Etapas 1-4  → m_ref\n"
                  "• Etapa 3/6   → level + PWM\n"
                  "• Etapa 5     → ext. sort-and-select\n\n"
                  "The arm only integrates its\nsubmodule capacitors under\n"
                  "the gates it is handed.",
                  fontsize=11, va="center", family="monospace")
    fig.tight_layout(); fig.savefig(path, dpi=90)
    print(f"  saved plot → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate-driven M3C (external control).")
    ap.add_argument("--f-out", type=float, default=45.0)
    ap.add_argument("--t-end", type=float, default=0.08)
    ap.add_argument("--dt", type=float, default=1.0e-5)
    ap.add_argument("--seed-spread", type=float, default=600.0,
                    help="initial per-SM imbalance [V] for the external balancer")
    ap.add_argument("--plot", type=str, default=None)
    args = ap.parse_args()
    model = build_gate_driven_m3c(f_out=args.f_out, dt=args.dt,
                                  v_c0_spread=args.seed_spread)
    sim = simulate_gate_driven_m3c(model, t_end=args.t_end)
    analyze(model, sim)
    if args.plot:
        plot(model, sim, args.plot)


if __name__ == "__main__":
    main()
