"""Tests for the pulsim 1.6 ``NativeMultiMaskPwm`` auto-swap in
``switch_fn_builder.assemble_switch_fn``.

When every enabled ``SwitchPwmConfig`` shares the same frequency the
builder should return a native C++ PWM object (no per-step GIL hop);
when the frequencies disagree it must fall back to the existing
Python-callable composition path so cascaded converters / phase-
shifted MMC arms still simulate.
"""
from __future__ import annotations

import math
import types

import pulsim as p

from pulsimgui.services.switch_fn_builder import (
    SwitchPwmConfig,
    assemble_switch_fn,
)


def _fake_circuit(indices: dict[str, int]) -> types.SimpleNamespace:
    """Minimal stub matching what ``assemble_switch_fn`` reads off the
    pulsim_v0 compat shim: ``num_switches`` + ``switch_indices``."""
    return types.SimpleNamespace(
        num_switches=max(indices.values()) + 1 if indices else 0,
        switch_indices=indices,
    )


def _mask_at(switch_fn, t: float, n_switches: int) -> tuple[bool, ...]:
    """Sample ``switch_fn`` at time ``t`` and pull all bits out."""
    mask = switch_fn(t)
    return tuple(bool(mask.get(i)) for i in range(n_switches))


# ---------------------------------------------------------------------------
# Native path — same frequency across all configs.
# ---------------------------------------------------------------------------
def test_single_switch_same_freq_returns_native_multimask() -> None:
    """One switch at 100 kHz, 50% duty → fast-path NativeMultiMaskPwm."""
    circuit = _fake_circuit({"M1": 0})
    sf = assemble_switch_fn(
        circuit,
        {"M1": SwitchPwmConfig(frequency=100e3, duty=0.5)},
        p,
    )
    assert sf is not None
    assert isinstance(sf, p.NativeMultiMaskPwm)


def test_native_multimask_respects_duty_window() -> None:
    """Duty window samples land on the right ON/OFF state."""
    circuit = _fake_circuit({"M1": 0})
    sf = assemble_switch_fn(
        circuit,
        {"M1": SwitchPwmConfig(frequency=100e3, duty=0.5)},
        p,
    )
    # Period = 10 us, ON window = [0, 5us)
    assert _mask_at(sf, 1e-6, 1) == (True,)
    assert _mask_at(sf, 4e-6, 1) == (True,)
    assert _mask_at(sf, 6e-6, 1) == (False,)
    assert _mask_at(sf, 9e-6, 1) == (False,)


def test_native_multimask_handles_phase_shifted_pair() -> None:
    """Two switches at the same frequency with HS+LS pattern (phase
    shifted by π) become a single NativeMultiMaskPwm and produce
    complementary masks at the expected times."""
    circuit = _fake_circuit({"HS": 0, "LS": 1})
    sf = assemble_switch_fn(
        circuit,
        {
            "HS": SwitchPwmConfig(frequency=100e3, duty=0.4, phase=0.0),
            "LS": SwitchPwmConfig(
                frequency=100e3, duty=0.6, phase=2.0 * math.pi * 0.4
            ),
        },
        p,
    )
    assert isinstance(sf, p.NativeMultiMaskPwm)
    # HS window: [0, 4us). LS window: [4us, 10us).
    assert _mask_at(sf, 1e-6, 2) == (True, False)
    assert _mask_at(sf, 5e-6, 2) == (False, True)
    assert _mask_at(sf, 9e-6, 2) == (False, True)


def test_native_multimask_handles_phase_wrap_around() -> None:
    """A device with phase > 0 whose ON window wraps past the end of
    the period must split into two boundary segments and still
    produce the correct ON state on both sides of t=0."""
    circuit = _fake_circuit({"M1": 0})
    sf = assemble_switch_fn(
        circuit,
        {
            # 80% duty, starting at 80% phase → ON from t=8us to 10us
            # AND from t=0 to t=6us (wraps).
            "M1": SwitchPwmConfig(
                frequency=100e3, duty=0.8, phase=2.0 * math.pi * 0.8
            )
        },
        p,
    )
    assert isinstance(sf, p.NativeMultiMaskPwm)
    assert _mask_at(sf, 0.5e-6, 1) == (True,)   # wrapped front segment
    assert _mask_at(sf, 5e-6, 1) == (True,)     # still in wrapped front
    assert _mask_at(sf, 7e-6, 1) == (False,)    # in OFF gap
    assert _mask_at(sf, 9e-6, 1) == (True,)     # back to ON before wrap


def test_disabled_config_keeps_switch_off_in_native_path() -> None:
    """``enabled=False`` removes a switch from the active mask
    without affecting any other switch's frequency check."""
    circuit = _fake_circuit({"M1": 0, "M2": 1})
    sf = assemble_switch_fn(
        circuit,
        {
            "M1": SwitchPwmConfig(frequency=100e3, duty=0.5, enabled=False),
            "M2": SwitchPwmConfig(frequency=100e3, duty=0.5, enabled=True),
        },
        p,
    )
    assert isinstance(sf, p.NativeMultiMaskPwm)
    # M1 always off — even mid-window
    for t_us in (1.0, 4.0, 9.0):
        assert _mask_at(sf, t_us * 1e-6, 2)[0] is False, (
            f"M1 should be OFF at t={t_us}us (enabled=False)"
        )
    # M2 follows its 50% window
    assert _mask_at(sf, 1e-6, 2)[1] is True
    assert _mask_at(sf, 9e-6, 2)[1] is False


# ---------------------------------------------------------------------------
# Fallback path — frequencies disagree, must NOT return native.
# ---------------------------------------------------------------------------
def test_mixed_frequencies_fall_back_to_python_path() -> None:
    """Cascaded converter / phase-shifted carriers can't share one
    NativeMultiMaskPwm — the builder must fall back to the existing
    ``make_combined_switch_fn`` Python path so the sim still runs."""
    circuit = _fake_circuit({"M1": 0, "M2": 1})
    sf = assemble_switch_fn(
        circuit,
        {
            "M1": SwitchPwmConfig(frequency=100e3, duty=0.5),
            "M2": SwitchPwmConfig(frequency=200e3, duty=0.5),
        },
        p,
    )
    assert sf is not None
    assert not isinstance(sf, p.NativeMultiMaskPwm), (
        "Mixed-frequency configs must NOT take the native fast path; "
        "the v1.6 NativeMultiMaskPwm only models one period."
    )


def test_all_disabled_falls_back_to_all_off_helper() -> None:
    """When every config is disabled / zero-duty, the builder routes
    to the constant-off Python helper instead of an empty
    NativeMultiMaskPwm (which would violate the C++ ctor invariant)."""
    circuit = _fake_circuit({"M1": 0, "M2": 1})
    sf = assemble_switch_fn(
        circuit,
        {
            "M1": SwitchPwmConfig(frequency=100e3, duty=0.0),
            "M2": SwitchPwmConfig(frequency=100e3, duty=0.5, enabled=False),
        },
        p,
    )
    assert sf is not None
    assert not isinstance(sf, p.NativeMultiMaskPwm)
    # Cross-check semantics: all bits off at any t
    for t_us in (0.5, 5.0, 9.5):
        mask = sf(t_us * 1e-6)
        assert mask.get(0) is False and mask.get(1) is False


def test_no_switches_returns_none() -> None:
    """Zero-switch builder → no switch_fn (existing contract)."""
    circuit = _fake_circuit({})
    sf = assemble_switch_fn(circuit, {}, p)
    assert sf is None


# ---------------------------------------------------------------------------
# Integration smoke — backend accepts the native fast-path result.
# ---------------------------------------------------------------------------
def test_pulsim_simulate_accepts_native_pwm_from_assembler() -> None:
    """End-to-end: build a real ``CircuitBuilder``, hand the native
    switch_fn back to ``pulsim.simulate`` (both engines), and the
    run completes with finite, non-zero waveforms. Catches any drift
    between our boundary conventions and what the bridge.13 PWL /
    DSED detection actually expects.

    We don't assert specific steady-state values here — the buck
    topology's state-vector layout depends on pulsim's internal MNA
    formulation, which is an implementation detail. The important
    contract for this Phase-3 swap is:
      (a) the native instance is what comes back from the assembler;
      (b) both engines accept it (no exception);
      (c) the run produces well-defined finite output (not NaN, not
          frozen at zero).
    """
    import math as _math

    import numpy as np

    b = p.CircuitBuilder()
    b.add_voltage_source("Vin", "vin", "gnd", 24.0)
    b.add_switch("M_HS", "vin", "sw", g_on=1e3, g_off=1e-9)
    b.add_switch("M_LS", "sw", "gnd", g_on=1e3, g_off=1e-9)
    b.add_inductor("L", "sw", "vout", 10e-6)
    b.add_capacitor("Cout", "vout", "gnd", 10e-6)
    b.add_resistor("Rload", "vout", "gnd", 2.4)

    circuit = _fake_circuit({"M_HS": 0, "M_LS": 1})
    sf = assemble_switch_fn(
        circuit,
        {
            "M_HS": SwitchPwmConfig(frequency=100e3, duty=0.5, phase=0.0),
            "M_LS": SwitchPwmConfig(
                frequency=100e3, duty=0.5, phase=_math.pi
            ),
        },
        p,
    )
    assert isinstance(sf, p.NativeMultiMaskPwm)

    res_pwl = p.simulate(b, t_end=2e-3, dt=1e-7, switch_fn=sf)
    states_pwl = np.array(res_pwl.states)
    assert states_pwl.size > 0
    assert np.all(np.isfinite(states_pwl))
    # At least one state varies — proves the switching is being
    # delivered to the kernel.
    assert states_pwl.std() > 0.01, (
        "Native switch_fn produced no observable state variation "
        "in 2ms — PWL didn't accept the NativeMultiMaskPwm"
    )

    # DSED leg uses a deliberately tiny window. The pip-distributed
    # pulsim wheel runs the *pure-Python* DSED scheduler (the native
    # C++ Bridge.11/12 adapter that delivers the changelog's 24×
    # speedup is only present in a from-source build), so a full 2 ms
    # / 100 kHz run would take many seconds. 50 µs = 5 switching
    # periods is enough to prove DSED accepts the NativeMultiMaskPwm
    # without making the test suite slow.
    res_dsed = p.simulate(
        b, t_end=50e-6, engine="dsed",
        rtol=1e-6, atol=1e-9, switch_fn=sf,
    )
    states_dsed = np.array(res_dsed.states)
    assert states_dsed.size > 0
    assert np.all(np.isfinite(states_dsed))
    assert states_dsed.std() > 0.01, (
        "Native switch_fn produced no observable state variation "
        "in 50us — DSED didn't accept the NativeMultiMaskPwm"
    )
