"""Tests for the C_BLOCK execution bridge — running a compiled
fast_block control law inside the simulate loop.

``PulsimBackend._build_cblock_closed_loops`` turns a
``cblock_loop_descriptor`` into a ClosedLoop whose step-observer runs
the user's Python control law each (throttled) step and whose
switch_fn drives a PWM mask from the resulting duty.

The assertions probe the bridge MECHANISM deterministically — they
run the loop's observer with a known state vector and then measure the
effective duty by sampling ``switch_fn`` across one PWM period. This
proves the full chain (compile → observer reads ``x`` → law computes →
duty → switch mask) without depending on emergent converter physics.
A final smoke test confirms a real ``pulsim.simulate`` run accepts the
loop and stays finite.
"""
from __future__ import annotations

import types

import numpy as np
import pulsim as p
import pytest

from pulsimgui.services.backend_adapter import PulsimBackend


def _adapter() -> PulsimBackend:
    a = PulsimBackend.__new__(PulsimBackend)
    a._module = p  # type: ignore[attr-defined]
    return a


def _buck_builder():
    """Proper buck: Vin → HS switch → freewheel diode → L → Cout‖Rload.
    Used for the simulate smoke test + to give the builder real
    ``node_id_of`` / ``switch_index_of`` lookups."""
    b = p.CircuitBuilder()
    b.add_voltage_source("Vin", "vin", "gnd", 24.0)
    b.add_switch("M_HS", "vin", "sw", g_on=1e3, g_off=1e-9)
    b.add_diode("Dfw", "gnd", "sw", g_on=1e3, g_off=1e-9)
    b.add_inductor("L", "sw", "vout", 100e-6)
    b.add_capacitor("Cout", "vout", "gnd", 100e-6)
    b.add_resistor("Rload", "vout", "gnd", 5.0)
    return b


def _descriptor(source: str, **over) -> dict:
    d = {
        "source": source,
        "n_states": 1,
        "feedback_node": "vout",
        "switch_device": "M_HS",
        "pwm_frequency": 50_000.0,
        "sample_time": 2e-5,
        "setpoint_value": 12.0,
        "output_min": 0.0,
        "output_max": 1.0,
    }
    d.update(over)
    return d


def _build_loop(builder, descriptor: dict):
    loops = _adapter()._build_cblock_closed_loops([descriptor], builder, 0.0)
    return loops[0] if loops else None


def _effective_duty(loop, switch_idx: int = 0, freq: float = 50_000.0) -> float:
    """Sample ``switch_fn`` across one PWM period and return the
    fraction of samples where the switch bit is ON — i.e. the duty the
    loop is currently commanding."""
    t_pwm = 1.0 / freq
    n = 200
    on = 0
    for k in range(n):
        # Sample within the FIRST period so phase = t*freq sweeps 0→1.
        t = (k / n) * t_pwm
        mask = loop.switch_fn(t)
        if mask.get(switch_idx):
            on += 1
    return on / n


def _feed(loop, builder, vout_value: float, t: float = 2e-5) -> None:
    """Run the loop's step-observer once with a state vector whose
    feedback node carries ``vout_value``."""
    x = np.zeros(builder.pool.state_size(builder.graph))
    x[builder.node_id_of("vout")] = vout_value
    loop.step_observer(t, x)


# ---------------------------------------------------------------------------
# Bridge mechanism — deterministic, no sim physics.
# ---------------------------------------------------------------------------
def test_output_duty_reaches_switch() -> None:
    """A law returning a constant duty must make ``switch_fn`` command
    exactly that duty after the observer runs."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, setpoint, dt, state):\n    return 0.75\n"
    ))
    assert loop is not None
    _feed(loop, b, 0.0)
    assert _effective_duty(loop) == pytest.approx(0.75, abs=0.02)


def test_feedback_signal_reaches_law() -> None:
    """A law that returns ``measured`` directly proves the live
    feedback value is delivered: feeding vout=0.3 → duty 0.3."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, setpoint, dt, state):\n    return measured\n"
    ))
    assert loop is not None
    _feed(loop, b, 0.30)
    assert _effective_duty(loop) == pytest.approx(0.30, abs=0.02)
    # Feed a different value → duty tracks it.
    _feed(loop, b, 0.60, t=6e-5)
    assert _effective_duty(loop) == pytest.approx(0.60, abs=0.02)


def test_setpoint_delivered_to_law() -> None:
    """The descriptor's setpoint_value must reach the law (arg 2 of a
    4-arg signature): law returns ``setpoint`` scaled → duty reflects
    the configured 0.4."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, setpoint, dt, state):\n    return setpoint\n",
        setpoint_value=0.4,
    ))
    assert loop is not None
    _feed(loop, b, 99.0)  # measured ignored by this law
    assert _effective_duty(loop) == pytest.approx(0.4, abs=0.02)


def test_state_persists_across_observer_calls() -> None:
    """A pure-integrator law's commanded duty must grow with each
    observer call — proving ``state`` persists in the closure."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, setpoint, dt, state):\n"
        "    state[0] += 0.1\n"
        "    return state[0]\n",
    ))
    assert loop is not None
    _feed(loop, b, 0.0, t=2e-5)
    d1 = _effective_duty(loop)
    _feed(loop, b, 0.0, t=6e-5)
    _feed(loop, b, 0.0, t=10e-5)
    d3 = _effective_duty(loop)
    assert d3 > d1 + 0.1, f"integrator didn't accumulate: d1={d1}, d3={d3}"


def test_duty_clamped_to_output_limits() -> None:
    """A law returning out-of-range output is clamped to
    [output_min, output_max]."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, setpoint, dt, state):\n    return 5.0\n",
        output_max=0.8,
    ))
    assert loop is not None
    _feed(loop, b, 0.0)
    assert _effective_duty(loop) == pytest.approx(0.8, abs=0.02)


def test_arity_two_law_supported() -> None:
    """A minimal ``control(measured, state)`` law works — the observer
    adapts the call signature."""
    b = _buck_builder()
    loop = _build_loop(b, _descriptor(
        "def control(measured, state):\n    return 0.55\n"
    ))
    assert loop is not None
    _feed(loop, b, 0.0)
    assert _effective_duty(loop) == pytest.approx(0.55, abs=0.02)


# ---------------------------------------------------------------------------
# Graceful degradation.
# ---------------------------------------------------------------------------
def test_bad_source_skips_loop() -> None:
    b = _buck_builder()
    loops = _adapter()._build_cblock_closed_loops(
        [_descriptor("def control(x):\n    return x\n")], b, 0.0,  # no state param
    )
    assert loops == []


def test_unknown_feedback_node_skips_loop() -> None:
    b = _buck_builder()
    loops = _adapter()._build_cblock_closed_loops(
        [_descriptor(
            "def control(m, sp, dt, state):\n    return 0.5\n",
            feedback_node="does_not_exist",
        )],
        b, 0.0,
    )
    assert loops == []


def test_empty_descriptors_via_closed_loops_returns_none() -> None:
    b = _buck_builder()
    circuit = types.SimpleNamespace(
        closed_loop_descriptors=[], cblock_loop_descriptors=[],
    )
    loop = _adapter()._build_closed_loops(circuit, b, lambda t, x: None, 0.0)
    assert loop is None


def test_cblock_descriptor_routes_through_closed_loops() -> None:
    """The top-level ``_build_closed_loops`` must compose a C_BLOCK
    descriptor into a runnable loop even with no PI descriptors."""
    b = _buck_builder()
    circuit = types.SimpleNamespace(
        closed_loop_descriptors=[],
        cblock_loop_descriptors=[_descriptor(
            "def control(m, sp, dt, state):\n    return 0.5\n"
        )],
    )
    loop = _adapter()._build_closed_loops(circuit, b, lambda t, x: None, 0.0)
    assert loop is not None
    assert hasattr(loop, "switch_fn") and hasattr(loop, "step_observer")


# ---------------------------------------------------------------------------
# Integration smoke — a real simulate run accepts the loop.
# ---------------------------------------------------------------------------
def test_simulate_accepts_cblock_loop_and_stays_finite() -> None:
    b = _buck_builder()
    circuit = types.SimpleNamespace(
        closed_loop_descriptors=[],
        cblock_loop_descriptors=[_descriptor(
            "def control(measured, setpoint, dt, state):\n"
            "    err = setpoint - measured\n"
            "    state[0] += 8.0 * dt * err\n"
            "    return 0.02 * err + state[0]\n"
        )],
    )
    loop = _adapter()._build_closed_loops(circuit, b, lambda t, x: None, 0.0)
    assert loop is not None
    res = p.simulate(b, t_end=4e-3, dt=2e-6, closed_loops=[loop])
    states = np.array(res.states)
    assert states.size > 0
    assert np.all(np.isfinite(states))
