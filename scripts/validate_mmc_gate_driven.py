#!/usr/bin/env python3
"""Gate-driven 3-phase MMC — switched signals, control 100% external.

A standard six-arm DC→AC Modular Multilevel Converter where every arm is a
gate-driven arm (:mod:`pulsimgui.services.gate_driven_arm`): NO internal
modulation, NO internal balancing. An external modulator feeds the per-submodule
gates each step (nearest-level + carrier PWM from a sinusoidal reference, plus
an external sort-and-select on each arm's live capacitors), and the arm only
integrates its capacitors — exactly the HIL/Simulink "I feed the gates, the
model represents" workflow.

The point of this example is to SEE the switched signals: the arm voltage is a
genuine multilevel staircase (N+1 levels) with PWM, the AC output is the
switched phase voltage, and the submodule capacitors are kept balanced by the
external sort-and-select — all at behavioural speed (no gate-level MNA switches).

Topology (grounded DC midpoint so the AC swings symmetrically):

    +Vdc/2 ─┬──[ARM_U]──[L]──●── ac_X ──[R+L load]──┐
    (dc_p)  │                 │                       (ground = DC midpoint)
    gnd ────┤                 │
    -Vdc/2 ─┴──[L]──[ARM_L]───●── ac_X ───────────────┘
    (dc_n)

Run::

    PYTHONPATH=src python3 scripts/validate_mmc_gate_driven.py
    PYTHONPATH=src python3 scripts/validate_mmc_gate_driven.py --plot /tmp/mmc.png
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

from pulsimgui.services.gate_driven_arm import (  # noqa: E402
    GateDrivenArmParams, add_gate_driven_arm, make_gate_driven_arm_observers)
from pulsimgui.services.m3c_gate_modulator import insertion_vector  # noqa: E402

# --- parameters ------------------------------------------------------------
N_SM = 8                  # submodules per arm  → 9-level arm voltage
V_CAP = 1000.0            # per-submodule capacitor voltage [V]
V_DC = N_SM * V_CAP       # DC-bus voltage [V] = 8 kV
C_SM = 10.0e-3            # submodule capacitance [F]
L_ARM = 5.0e-3            # arm inductance [H]
R_LOAD = 15.0            # load resistance per phase [Ω]
L_LOAD = 20.0e-3         # load inductance per phase [H]
F_OUT = 50.0             # output frequency [Hz]
M_IDX = 0.9             # modulation index
F_CARRIER = 1000.0       # PWM carrier [Hz]
PHASES = ("a", "b", "c")
PHI = (0.0, -2.0 * math.pi / 3.0, +2.0 * math.pi / 3.0)


@dataclass
class MmcModel:
    builder: object
    arms: dict = field(default_factory=dict)
    arm_names: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def build_gate_driven_mmc(dt: float = 1.0e-5, v_c0_spread: float = 0.0) -> MmcModel:
    """Build the six-arm gate-driven MMC with an external sinusoidal modulator."""
    w = 2.0 * math.pi * F_OUT
    b = p.CircuitBuilder()
    b.ground()                                    # node "0" = DC midpoint
    b.add_voltage_source("Vdc_p", "dc_p", "0", V_DC / 2.0)
    b.add_voltage_source("Vdc_n", "0", "dc_n", V_DC / 2.0)

    # Per-arm modulation references (upper/lower complementary) and a PSC-style
    # carrier phase so the six arms don't dither in lock-step.
    m_funcs: dict = {}
    carrier_phase: dict = {}
    for k, (ph, phi) in enumerate(zip(PHASES, PHI)):
        m_funcs[f"U_{ph}"] = (lambda t, _p=phi: 0.5 * (1.0 - M_IDX * math.sin(w * t + _p)))
        m_funcs[f"L_{ph}"] = (lambda t, _p=phi: 0.5 * (1.0 + M_IDX * math.sin(w * t + _p)))
        carrier_phase[f"U_{ph}"] = (2 * k) / 6.0
        carrier_phase[f"L_{ph}"] = (2 * k + 1) / 6.0

    def gate_source(t, arm):
        m = m_funcs[arm.name](t)
        s, _ = insertion_vector(m, t, arm, f_carrier=F_CARRIER,
                                phase=carrier_phase[arm.name], pwm=True)
        return s

    def seed():
        if v_c0_spread <= 0:
            return None
        return [V_CAP + (1 if (i % 2 == 0) else -1) * 0.5 * v_c0_spread
                for i in range(N_SM)]

    model = MmcModel(builder=b)
    params = dict(n_sm=N_SM, c_sm=C_SM, v_c0=V_CAP, sm_type="half_bridge")
    for k, ph in enumerate(PHASES):
        # upper arm: dc_p → ARM_U → aup → L → ac
        au = add_gate_driven_arm(b, name=f"U_{ph}", node_a="dc_p",
                                 node_b=f"aup_{ph}",
                                 params=GateDrivenArmParams(**params),
                                 gate_source=gate_source, v_c0_per_sm=seed())
        b.add_inductor(f"Lup_{ph}", f"aup_{ph}", f"ac_{ph}", L_ARM, 0.0)
        # lower arm: ac → L → alow → ARM_L → dc_n
        b.add_inductor(f"Llow_{ph}", f"ac_{ph}", f"alow_{ph}", L_ARM, 0.0)
        al = add_gate_driven_arm(b, name=f"L_{ph}", node_a=f"alow_{ph}",
                                 node_b="dc_n",
                                 params=GateDrivenArmParams(**params),
                                 gate_source=gate_source, v_c0_per_sm=seed())
        # 3φ R+L load: ac → R → L → ground (= DC midpoint / load neutral)
        b.add_resistor(f"Rld_{ph}", f"ac_{ph}", f"ldm_{ph}", R_LOAD)
        b.add_inductor(f"Lld_{ph}", f"ldm_{ph}", "0", L_LOAD, 0.0)
        model.arms[f"U_{ph}"] = au
        model.arms[f"L_{ph}"] = al

    model.arm_names = list(model.arms.keys())
    model.meta = dict(dt=dt, v_dc=V_DC, n_sm=N_SM, v_cap=V_CAP, f_out=F_OUT)
    return model


def simulate_gate_driven_mmc(model: MmcModel, t_end: float = 0.06) -> dict:
    b = model.builder
    dt = model.meta["dt"]
    arms = [model.arms[n] for n in model.arm_names]
    arm_step, b_extra = make_gate_driven_arm_observers(b, arms, dt=dt)

    rec_t: list[float] = []
    rec_vb: list[float] = []          # upper-arm-a switched voltage (staircase)
    rec_spread: list[list[float]] = []
    rec_vc: list[list[float]] = []

    def observer(t, x):
        arm_step(t, x)
        rec_t.append(t)
        rec_vb.append(model.arms["U_a"].v_b)
        rec_spread.append([model.arms[n].v_C_spread for n in model.arm_names])
        rec_vc.append([model.arms[n].v_C for n in model.arm_names])

    result = p.simulate(b, t_end=t_end, dt=dt, b_extra_fn=b_extra,
                        step_observer=observer)
    times = np.asarray(result.times)
    v_ac = [np.asarray(result.v(f"ac_{ph}")) for ph in PHASES]
    i_load = [np.asarray(result.i(f"Lld_{ph}")) for ph in PHASES]
    return dict(times=times, v_ac=v_ac, i_load=i_load,
                vb_t=np.asarray(rec_t), vb_ua=np.asarray(rec_vb),
                spread=np.asarray(rec_spread), v_c=np.asarray(rec_vc),
                result=result)


def analyze(model: MmcModel, sim: dict) -> dict:
    t = sim["times"]
    sl = slice(len(t) // 2, None)

    def amp(s):
        return float(np.sqrt(2.0) * np.std(np.asarray(s)[sl]))

    i_amps = [amp(s) for s in sim["i_load"]]
    v_levels = len(np.unique(np.round(sim["vb_ua"] / model.meta["v_cap"])))
    intra = float(np.max(sim["spread"][-1]))
    metrics = dict(load_current_amps=i_amps,
                   arm_voltage_levels=v_levels,
                   intra_module_spread=intra,
                   vc_mean_end=float(np.mean(sim["v_c"][-1])))
    print(f"gate-driven MMC — Vdc={model.meta['v_dc']/1e3:.0f} kV, "
          f"N={model.meta['n_sm']} SM/arm, f_out={model.meta['f_out']:.0f} Hz "
          f"({t[-1]*1e3:.0f} ms)   (control 100% external)")
    print(f"  load current per phase: {[f'{a:.0f}' for a in i_amps]} A")
    print(f"  upper-arm voltage distinct levels: {v_levels}  (≈ N+1 staircase)")
    print(f"  arm cap mean: {metrics['vc_mean_end']/1e3:.2f} kV   "
          f"submodule spread (ext. sort-and-select): {intra:.0f} V")
    return metrics


def plot(model: MmcModel, sim: dict, path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    t = sim["times"] * 1e3
    tb = sim["vb_t"] * 1e3
    fig, ax = plt.subplots(2, 2, figsize=(12, 7))
    ax[0, 0].plot(tb, sim["vb_ua"] / 1e3, lw=0.7, color="#c0392b")
    ax[0, 0].set_title("Upper-arm voltage (switched, N+1 staircase + PWM)")
    ax[0, 0].set_ylabel("kV"); ax[0, 0].set_xlabel("ms"); ax[0, 0].grid(True)
    for k, ph in enumerate(PHASES):
        ax[0, 1].plot(t, sim["v_ac"][k] / 1e3, lw=0.6, label=f"v_{ph}")
    ax[0, 1].set_title("AC output phase voltages (switched)")
    ax[0, 1].set_ylabel("kV"); ax[0, 1].set_xlabel("ms")
    ax[0, 1].legend(loc="upper right"); ax[0, 1].grid(True)
    for k, ph in enumerate(PHASES):
        ax[1, 0].plot(t, sim["i_load"][k], lw=1.0, label=f"i_{ph}")
    ax[1, 0].set_title("Load currents")
    ax[1, 0].set_ylabel("A"); ax[1, 0].set_xlabel("ms")
    ax[1, 0].legend(loc="upper right"); ax[1, 0].grid(True)
    for k in range(len(model.arm_names)):
        ax[1, 1].plot(tb, sim["spread"][:, k], lw=0.8)
    ax[1, 1].set_title("Submodule spread per arm (external sort-and-select)")
    ax[1, 1].set_ylabel("V"); ax[1, 1].set_xlabel("ms"); ax[1, 1].grid(True)
    fig.tight_layout(); fig.savefig(path, dpi=90)
    print(f"  saved plot → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Gate-driven 3φ MMC (switched).")
    ap.add_argument("--t-end", type=float, default=0.06)
    ap.add_argument("--dt", type=float, default=1.0e-5)
    ap.add_argument("--seed-spread", type=float, default=400.0)
    ap.add_argument("--plot", type=str, default=None)
    args = ap.parse_args()
    model = build_gate_driven_mmc(dt=args.dt, v_c0_spread=args.seed_spread)
    sim = simulate_gate_driven_mmc(model, t_end=args.t_end)
    analyze(model, sim)
    if args.plot:
        plot(model, sim, args.plot)


if __name__ == "__main__":
    main()
