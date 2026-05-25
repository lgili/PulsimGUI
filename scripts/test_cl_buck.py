"""Closed-loop buck converter — modern (pulsim 1.3+) standalone test.

V_in = 12 V, V_ref = 5 V, 220 µH / 220 µF / 8 Ω, 10 kHz PWM.
The PI controller closes the loop on V_out toward V_ref by adjusting
the PWM duty between the configured ``output_min`` / ``output_max``
bounds. Steady-state should land within ±10 % of V_ref.

This script is the v1.3 idiom check — same circuit as the legacy v0
``test_cl_buck.py`` (which used ``ps.Circuit()`` +
``add_virtual_component`` for the PI/PWM blocks), now built against
the modern surface:

  * ``pulsim.CircuitBuilder`` with string-named nodes.
  * ``pulsim.add_mosfet_with_body_diode`` so the eager cache build
    doesn't reject the all-off mask.
  * ``pulsim.PIController`` (control block) driven from a
    ``step_observer`` callback that reads ``V(vout)`` each step,
    feeds it through the PI, and recomputes the PWM duty via a
    mutable closure shared with ``switch_fn``.

The control path uses Python-side blocks rather than v0's "virtual
component" embedded in the kernel — it's slower but trivially
inspectable and matches how the GUI's closed-loop topologies will
eventually drive `simulate()` once the PWM-config dialog (PR #9)
lands.
"""

from __future__ import annotations

import sys

import numpy as np

import pulsim as ps


VIN   = 12.0
VREF  = 5.0
L_H   = 220e-6
C_F   = 220e-6
R_OHM = 8.0
F_PWM = 10e3


def build_plant() -> ps.CircuitBuilder:
    """Open-loop power stage. The PI controller sits outside the
    builder; it observes ``V(vout)`` each step and decides the
    PWM duty.
    """
    b = ps.CircuitBuilder()
    b.add_voltage_source("V1", "vin", "gnd", VIN)
    b.add_mosfet_with_body_diode(
        "Q1", "vin", "sw", R_on=1e-3, R_off=1e9, V_F=0.7,
    )
    b.add_diode("D1", "gnd", "sw", 1e3, 1e-9, V_th=0.7)
    b.add_inductor ("L1",   "sw",   "vout", L_H)
    b.add_capacitor("Cout", "vout", "gnd",  C_F)
    b.add_resistor ("R_L",  "vout", "gnd",  R_OHM)
    return b


def main() -> int:
    builder = build_plant()
    print(f"  num_branches: {builder.num_branches}")
    print(f"  num_switches: {builder.graph.num_switches}")

    vout_idx = builder.node_id_of("vout")

    # PI controller — gains tuned by eyeball; the target is steady-
    # state within ±10 %, not optimal transient. ``Kp``/``Ki`` use
    # the capitalised names from ``pulsim.PIController`` directly.
    pi = ps.PIController(Kp=0.08, Ki=40.0, output_min=0.05, output_max=0.95)

    # Shared state: ``current_duty`` is updated by the step observer
    # and read by ``switch_fn`` on the next PWM evaluation. A
    # 1-element list gives us a mutable scalar callbacks can share
    # without nonlocal trickery. ``last_pi_t`` similarly stores the
    # time of the last PI update so we throttle the loop to the
    # PWM rate.
    current_duty = [0.50]
    last_pi_t = [-1.0 / F_PWM]  # forces the first update to fire

    # PWM switch_fn that reads ``current_duty[0]`` each tick. We
    # cannot use ``make_pwm_switch_fn`` here because that takes a
    # *fixed* duty at construction; closed-loop needs the duty to
    # vary with time. Hand-rolled PWM is straightforward — period
    # T = 1 / f_PWM, ON for the first ``duty · T``.
    T_PWM = 1.0 / F_PWM
    n_switches = builder.graph.num_switches

    def switch_fn(t: float) -> ps.SwitchStateMask:
        mask = ps.SwitchStateMask(n_switches)
        phase_in_period = (t % T_PWM) / T_PWM
        if phase_in_period < current_duty[0]:
            mask.set(0, True)  # Q1 conducting
        return mask

    def step_observer(t: float, x) -> None:
        # PI on the (V_ref − V_out) error. v1.3's ``PIController``
        # takes setpoint + measured as kwargs and does the
        # subtraction internally. We throttle the loop to the PWM
        # period (``T_PWM``) so it averages over each switching
        # cycle instead of chasing ripple.
        if t - last_pi_t[0] < T_PWM:
            return
        last_pi_t[0] = t
        duty = pi.update(setpoint=VREF, measured=float(x[vout_idx]),
                          dt=T_PWM)
        current_duty[0] = float(duty)

    print("\nRunning closed-loop transient ...")
    res = ps.simulate(
        builder,
        t_end=20e-3,
        dt=2e-6,
        switch_fn=switch_fn,
        step_observer=step_observer,
    )

    print(f"  samples: {res.num_steps()}")

    states = np.asarray(res.states)
    times = np.asarray(res.times)
    v_out = states[:, vout_idx]

    # Steady-state: average V_out over the last 2 ms.
    mask = times >= 0.018
    if not mask.any():
        print("  WARNING: no samples in the last 2 ms window")
        return 1
    vout_avg = float(np.mean(v_out[mask]))
    error_pct = abs(vout_avg - VREF) / VREF * 100.0
    print(f"  V_out (avg last 2 ms): {vout_avg:.3f} V   (target {VREF} V)")
    print(f"  Steady-state error: {error_pct:.2f} %")
    print(f"  Final duty: {current_duty[0]:.4f}  (target ≈ {VREF / VIN:.4f})")

    if error_pct > 10.0:
        print(f"\nFAIL — error {error_pct:.1f}% exceeds 10% tolerance")
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
