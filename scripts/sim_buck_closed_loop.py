"""Closed-loop buck converter simulation — pulsim 1.5 idiom.

Circuit:  Vin=12 V → MOSFET/Diode + L=220 µH + Cout=220 µF + R=8 Ω
Control:  V_out feedback → PI(Kp=0.08, Ki=40) throttled to PWM rate → duty

This script *does* converge. Previous revisions documented a "known
limitation" because pulsim 1.4 retired the in-kernel
``pi_controller`` / ``pwm_generator`` virtual-component blocks that
v0 used to embed inside the simulation stride — the GUI's saved
.pulsim file references those blocks, but the v1.3+ ``simulate(
builder, …)`` driver doesn't wire them.

pulsim 1.5 lands the user-facing fix: :func:`pulsim.bind_pi_to_switch`
packages the PI + PWM closure pattern that
``scripts/test_cl_buck.py`` used to hand-roll. This script uses the
helper directly — same plant as the GUI's
``buck_converter_closed_loop.pulsim`` file, just with the loop
re-bound at simulate-time instead of via the retired virtual
components.

Usage
-----
    cd PulsimGUI
    PYTHONPATH=src python3 scripts/sim_buck_closed_loop.py

Optional: ``--plot`` renders V_out + duty with matplotlib.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pulsim as ps


# ---------------------------------------------------------------------------
# Plant constants — match examples/buck_converter_closed_loop.pulsim
# ---------------------------------------------------------------------------
V_IN  = 12.0
V_REF = 6.0
L_H   = 220e-6
C_F   = 220e-6
R_OHM = 8.0
F_PWM = 10e3


def build_plant() -> ps.CircuitBuilder:
    """Recreate the buck_converter_closed_loop.pulsim plant directly via
    :class:`CircuitBuilder`. Six lines of topology — the .pulsim file is
    the same circuit serialised to JSON; bypassing the GUI converter
    keeps this script self-contained while we wait for the closed-loop
    runner to learn the v1.5 idiom natively.
    """
    b = ps.CircuitBuilder()
    b.add_voltage_source("V1", "vin", "gnd", V_IN)
    b.add_mosfet_with_body_diode(
        "Q1", "vin", "sw", R_on=1e-3, R_off=1e9, V_F=0.7,
    )
    b.add_diode("D1", "gnd", "sw", 1e3, 1e-9, V_th=0.7)
    b.add_inductor("L1", "sw", "vout", L_H)
    b.add_capacitor("Cout", "vout", "gnd", C_F)
    b.add_resistor("R_L", "vout", "gnd", R_OHM)
    return b


def run(t_stop: float = 20e-3, dt: float = 2e-6, plot: bool = False) -> int:
    print(f"Plant:  V_in={V_IN} V → buck (D≈{V_REF/V_IN:.3f}) → V_ref={V_REF} V")
    print(f"        L={L_H*1e6:.0f} µH, C={C_F*1e6:.0f} µF, R={R_OHM} Ω, "
           f"f_PWM={F_PWM/1e3:.0f} kHz")

    b = build_plant()
    pi = ps.PIController(
        Kp=0.08, Ki=40.0, output_min=0.05, output_max=0.95,
    )
    loop = ps.bind_pi_to_switch(
        b, pi=pi,
        measured=lambda x: x[b.node_id_of("vout")],
        setpoint=V_REF,
        switch="Q1",      # name → switch_index_of resolves the bit
        freq=F_PWM,
    )

    print(f"\nRunning closed-loop transient ({t_stop*1e3:.1f} ms, "
           f"dt={dt*1e6:.1f} µs) …")
    res = ps.simulate(b, t_end=t_stop, dt=dt, closed_loops=[loop])
    print(f"  samples: {res.num_steps()}")

    # KPIs via v1.5 named accessor — no `n_nodes + idx` arithmetic.
    v_out = res.v("vout")
    v_out_ss = float(np.mean(v_out[-1000:]))
    error_pct = abs(v_out_ss - V_REF) / V_REF * 100.0
    final_duty = loop.duty_history[-1][1] if loop.duty_history else float("nan")

    print(f"\n{'='*55}")
    print(f"  V_out steady-state: {v_out_ss:.4f} V  (target {V_REF})")
    print(f"  Final duty:         {final_duty:.4f}  "
           f"(ideal {V_REF/V_IN:.4f})")
    print(f"  Steady-state ε:     {error_pct:.2f} %")
    converged = error_pct < 5.0
    print(f"  Converged:          {'YES ✓' if converged else 'NO ✗'}")
    print(f"{'='*55}\n")

    if plot:
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print("matplotlib not installed — skipping plot")
            return 0 if converged else 1
        times = np.asarray(res.times) * 1e3
        d_t, d_v = (
            np.asarray(loop.duty_history).T
            if loop.duty_history else (np.array([]), np.array([]))
        )
        fig, (ax_v, ax_d) = plt.subplots(2, 1, figsize=(10, 5), sharex=True)
        ax_v.plot(times, v_out, lw=0.8, label="V_out")
        ax_v.axhline(V_REF, color="r", ls="--", lw=1, label="V_ref")
        ax_v.set_ylabel("V_out [V]"); ax_v.grid(alpha=0.3); ax_v.legend()
        ax_v.set_title("Closed-loop buck via pulsim.bind_pi_to_switch")
        ax_d.plot(d_t * 1e3, d_v, lw=0.8, color="tab:orange")
        ax_d.axhline(V_REF / V_IN, color="r", ls="--", lw=1,
                      label=f"ideal {V_REF/V_IN:.3f}")
        ax_d.set_ylabel("duty"); ax_d.set_xlabel("t [ms]")
        ax_d.grid(alpha=0.3); ax_d.legend()
        fig.tight_layout()
        plt.show()

    return 0 if converged else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Closed-loop buck — v1.5 idiom (bind_pi_to_switch).",
    )
    parser.add_argument(
        "--t-stop", type=float, default=20e-3,
        help="Stop time in seconds (default: 20 ms)",
    )
    parser.add_argument(
        "--dt", type=float, default=2e-6, help="Time step (default: 2 µs)",
    )
    parser.add_argument("--plot", action="store_true",
                          help="Render V_out + duty with matplotlib.")
    args, _ = parser.parse_known_args()
    sys.exit(run(t_stop=args.t_stop, dt=args.dt, plot=args.plot))
