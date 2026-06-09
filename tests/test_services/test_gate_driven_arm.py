"""Tests for the gate-driven (externally-commanded) MMC/M3C arm.

Drives a single arm with a known constant current and external gate signals,
through a real pulsim simulation, to verify: capacitors charge under insertion,
bypass holds them, the aggregate/spread telemetry is correct, and — the whole
point — there is NO internal balancing (uniform external gates preserve a seeded
submodule spread), while an external sort-and-select CAN balance it.
"""
from __future__ import annotations

import pulsim as p

from pulsimgui.services.gate_driven_arm import (
    GateDrivenArm,
    GateDrivenArmParams,
    add_gate_driven_arm,
    make_gate_driven_arm_observers,
)


def _run(gate_source, *, current=120.0, n_sm=6, c_sm=680e-6, v_c0=4000.0,
         v_c0_per_sm=None, t_end=0.02, dt=1e-5, sm_type="full_bridge"):
    """One gate-driven arm carrying a constant current; return the arm."""
    b = p.CircuitBuilder()
    b.ground()
    params = GateDrivenArmParams(n_sm=n_sm, c_sm=c_sm, v_c0=v_c0,
                                 sm_type=sm_type)
    arm = add_gate_driven_arm(b, name="ARM", node_a="a", node_b="0",
                              params=params, gate_source=gate_source,
                              v_c0_per_sm=v_c0_per_sm)
    # Force a constant current through the arm (parallel between 'a' and gnd).
    b.add_current_source("I0", "0", "a", current)
    so, b_extra = make_gate_driven_arm_observers(b, [arm], dt=dt)
    p.simulate(b, t_end=t_end, dt=dt, b_extra_fn=b_extra, step_observer=so)
    return arm


def test_caps_charge_uniformly_under_full_insertion() -> None:
    """All submodules inserted ⇒ every cap moves by ~i_b·t/C, the aggregate is
    the sum, and v_b equals the aggregate (all inserted)."""
    arm = _run(lambda t, a: [1.0] * a.params.n_sm)
    v = arm.v_C_per_sm
    # all six moved by the same (nonzero) amount from 4000 V
    delta = [vi - 4000.0 for vi in v]
    assert all(abs(d) > 200.0 for d in delta)               # actually charging
    assert max(delta) - min(delta) < 1.0                    # uniform
    assert abs(arm.v_C - sum(v)) < 1e-6                      # aggregate = sum
    # v_b (all inserted +1) equals the aggregate within a step
    assert abs(abs(arm.v_b) - abs(arm.v_C)) < abs(arm.v_C) * 0.05


def test_bypass_holds_capacitors() -> None:
    """All submodules bypassed ⇒ caps hold and the arm sources ~0 V."""
    arm = _run(lambda t, a: [0.0] * a.params.n_sm)
    assert all(abs(vi - 4000.0) < 1.0 for vi in arm.v_C_per_sm)
    assert abs(arm.v_b) < 1.0


def test_no_internal_balancing_preserves_seeded_spread() -> None:
    """THE point: with uniform external gates the arm does NOT balance — a
    seeded submodule spread is preserved (every cap shifts by the same amount).
    This is the opposite of the L3 sort-and-select arm."""
    seed = [4500.0, 4300.0, 4000.0, 3800.0, 3600.0, 3700.0]
    spread0 = max(seed) - min(seed)
    arm = _run(lambda t, a: [1.0] * a.params.n_sm, v_c0_per_sm=seed)
    # spread essentially unchanged (uniform charge shifts all caps equally)
    assert abs(arm.v_C_spread - spread0) < 1.0


def test_external_sort_and_select_balances() -> None:
    """An EXTERNAL sort-and-select gate source (insert the lowest caps when
    charging, the highest when discharging) DOES shrink a seeded spread — the
    balancing lives entirely in the controller, not the model."""
    seed = [4800.0, 4600.0, 4000.0, 3600.0, 3400.0, 3600.0]
    spread0 = max(seed) - min(seed)
    n_insert = 3                          # insert 3 of 6 each step

    def sort_and_select(t: float, arm: GateDrivenArm):
        v = arm.v_C_per_sm
        order = sorted(range(len(v)), key=lambda k: v[k])
        s = [0.0] * len(v)
        # charging (i_b>0): insert the LOWEST caps; discharging: the HIGHEST
        picks = order[:n_insert] if arm.i_b >= 0 else order[-n_insert:]
        for k in picks:
            s[k] = 1.0
        return s

    arm = _run(sort_and_select, v_c0_per_sm=seed, t_end=0.03)
    assert arm.v_C_spread < 0.5 * spread0          # external balancer converges


def test_full_bridge_negative_insertion() -> None:
    """Full-bridge SMs can insert negative (−v_C): all −1 ⇒ v_b ≈ −aggregate."""
    arm = _run(lambda t, a: [-1.0] * a.params.n_sm)
    assert arm.v_b < 0.0
    assert abs(abs(arm.v_b) - arm.v_C) < arm.v_C * 0.05
