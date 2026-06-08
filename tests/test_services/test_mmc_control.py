"""Unit tests for the closed-loop MMC controller's control law (no kernel)."""
from __future__ import annotations

import math

from pulsimgui.services.mmc_control import MmcClosedLoopController


def _ctrl(**kw) -> MmcClosedLoopController:
    base = dict(
        phase_arms=[("ARM_uA", "ARM_lA"), ("ARM_uB", "ARM_lB"), ("ARM_uC", "ARM_lC")],
        vdc_half=400.0, vc_ref=800.0, freq=60.0, mod_index=0.6,
        arm_l=5e-3, arm_r=0.1, control_dt=1e-5,
    )
    base.update(kw)
    return MmcClosedLoopController(**base)


def _all_vc(value: float) -> dict[str, float]:
    return {n: value for ph in (("ARM_uA", "ARM_lA"), ("ARM_uB", "ARM_lB"),
                                ("ARM_uC", "ARM_lC")) for n in ph}


def _zero_i() -> dict[str, float]:
    return _all_vc(0.0)


def test_park_inverse_round_trip() -> None:
    for theta in (0.0, 0.7, 2.1, -1.3):
        abc = MmcClosedLoopController._inv_park(12.0, -5.0, theta)
        d, q = MmcClosedLoopController._park(abc, theta)
        assert math.isclose(d, 12.0, abs_tol=1e-9)
        assert math.isclose(q, -5.0, abs_tol=1e-9)


def test_park_balanced_set_is_constant_in_dq() -> None:
    # A balanced positive-sequence current at angle theta projects to a steady
    # d component (= amplitude) and ~zero q when aligned.
    amp = 7.0
    theta = 1.234
    abc = [amp * math.cos(theta + off) for off in (0.0, -2 * math.pi / 3, 2 * math.pi / 3)]
    d, q = MmcClosedLoopController._park(abc, theta)
    assert math.isclose(d, amp, rel_tol=1e-6)
    assert math.isclose(q, 0.0, abs_tol=1e-6)


def test_sample_and_hold_only_updates_each_control_dt() -> None:
    c = _ctrl(control_dt=1e-5)
    c.update(0.0, _zero_i(), _all_vc(800.0))
    first = c.m_ref("ARM_uA")
    # within the same control period: held, no recompute even with new data
    c.update(2e-6, _zero_i(), _all_vc(100.0))
    assert c.m_ref("ARM_uA") == first
    # past the period: recompute reacts to the (now very different) cap voltage
    c.update(1.1e-5, _zero_i(), _all_vc(100.0))
    assert c.last_vc_avg == 100.0


def test_energy_loop_sign_low_caps_command_positive_circulating_current() -> None:
    c = _ctrl()
    # caps well below reference → controller should pull power in (i_circ_ref > 0)
    t = 0.0
    for _ in range(50):
        c.update(t, _zero_i(), _all_vc(600.0))
        t += c.control_dt
    assert c.last_i_circ_ref > 0.0
    # and high caps → negative reference (push energy back)
    c2 = _ctrl()
    t = 0.0
    for _ in range(50):
        c2.update(t, _zero_i(), _all_vc(950.0))
        t += c2.control_dt
    assert c2.last_i_circ_ref < 0.0


def test_insertion_indices_stay_in_unit_interval() -> None:
    c = _ctrl(current_control=False)
    t = 0.0
    # sweep a fundamental period with healthy caps; m must remain a valid duty
    while t < 1.0 / 60.0:
        c.update(t, _zero_i(), _all_vc(800.0))
        for up, lo in c.phase_arms:
            assert 0.0 <= c.m_ref(up) <= 1.0
            assert 0.0 <= c.m_ref(lo) <= 1.0
        t += c.control_dt


def test_open_loop_voltage_produces_complementary_arm_modulation() -> None:
    # With healthy balanced caps and i_z≈0, at a phase angle where sin>0 the
    # upper arm should insert less than the lower arm (push the phase node up).
    c = _ctrl(current_control=False, mod_index=0.6)
    # advance to a quarter period of phase A (theta = pi/2 → sin = 1)
    t = 0.25 / 60.0
    c.update(t, _zero_i(), _all_vc(800.0))
    assert c.m_ref("ARM_uA") < c.m_ref("ARM_lA")


def test_current_control_mode_runs_and_holds_valid_duty() -> None:
    c = _ctrl(current_control=True, id_ref=5.0, iq_ref=0.0, load_l=10e-3, load_r=15.0)
    t = 0.0
    while t < 2.0 / 60.0:
        c.update(t, _zero_i(), _all_vc(800.0))
        for up, lo in c.phase_arms:
            assert 0.0 <= c.m_ref(up) <= 1.0
            assert 0.0 <= c.m_ref(lo) <= 1.0
        t += c.control_dt


def test_soft_start_holds_output_near_zero_at_t0() -> None:
    # At t≈0 the soft-start ramp is ~0, so with healthy caps both arms insert
    # ~0.5 (no AC swing yet); past the ramp the modulation is complementary.
    c = _ctrl(soft_start_time=0.01)
    c.update(0.0, _zero_i(), _all_vc(800.0))
    assert abs(c.m_ref("ARM_uA") - 0.5) < 0.05
    assert abs(c.m_ref("ARM_lA") - 0.5) < 0.05
    c2 = _ctrl(soft_start_time=0.001)
    c2.update(0.25 / 60.0, _zero_i(), _all_vc(800.0))  # quarter period, ramp done
    assert c2.m_ref("ARM_uA") < c2.m_ref("ARM_lA")


def test_per_phase_energy_mode_runs_and_holds_valid_duty() -> None:
    c = _ctrl(per_phase_energy=True, soft_start_time=0.0)
    t = 0.0
    while t < 2.0 / 60.0:
        c.update(t, _zero_i(), _all_vc(750.0))  # sagging caps exercise the loop
        for up, lo in c.phase_arms:
            assert 0.0 <= c.m_ref(up) <= 1.0
            assert 0.0 <= c.m_ref(lo) <= 1.0
        t += c.control_dt
    assert c.last_i_circ_ref > 0.0  # low caps → positive recharge ref
