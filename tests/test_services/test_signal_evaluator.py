"""Tests for SignalEvaluator – signal-flow closed-loop control block."""

from __future__ import annotations

import pytest

from pulsim.signal_evaluator import AlgebraicLoopError, SignalEvaluator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pin(index: int, name: str) -> dict:
    return {"index": index, "name": name, "x": 0.0, "y": 0.0}


def _wire(src_id: str, src_pin: int, dst_id: str, dst_pin: int) -> dict:
    return {
        "start_connection": {"component_id": src_id, "pin_index": src_pin},
        "end_connection":   {"component_id": dst_id, "pin_index": dst_pin},
    }


def _circuit(*components, wires=()) -> dict:
    return {
        "components": list(components),
        "wires": list(wires),
        "node_map": {},
        "node_aliases": {},
    }


def _constant(cid: str, value: float) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "CONSTANT",
        "parameters": {"value": value},
        "pins": [_pin(0, "OUT")],
    }


def _gain(cid: str, k: float) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "GAIN",
        "parameters": {"gain": k},
        "pins": [_pin(0, "IN"), _pin(1, "OUT")],
    }


def _limiter(cid: str, lo: float, hi: float) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "LIMITER",
        "parameters": {"lower_limit": lo, "upper_limit": hi},
        "pins": [_pin(0, "IN"), _pin(1, "OUT")],
    }


def _subtractor(cid: str) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "SUBTRACTOR",
        "parameters": {"input_count": 2},
        "pins": [_pin(0, "IN1"), _pin(1, "IN2"), _pin(2, "OUT")],
    }


def _summer(cid: str) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "SUM",
        "parameters": {"input_count": 2, "signs": ["+", "+"]},
        "pins": [_pin(0, "IN1"), _pin(1, "IN2"), _pin(2, "OUT")],
    }


def _pwm(cid: str) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "PWM_GENERATOR",
        "parameters": {"duty_cycle": 0.5, "frequency": 10000},
        "pins": [_pin(0, "OUT"), _pin(1, "DUTY_IN")],
    }


def _probe(cid: str) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "VOLTAGE_PROBE",
        "parameters": {"display_name": "V"},
        "pins": [_pin(0, "OUT")],
    }


def _pi(cid: str, kp: float = 1.0, ki: float = 10.0,
        out_min: float = 0.0, out_max: float = 1.0) -> dict:
    return {
        "id": cid, "name": cid.upper(), "type": "PI_CONTROLLER",
        "parameters": {"kp": kp, "ki": ki, "output_min": out_min, "output_max": out_max},
        "pins": [_pin(0, "IN"), _pin(1, "OUT")],
    }


# ---------------------------------------------------------------------------
# Basic block evaluation
# ---------------------------------------------------------------------------

class TestConstant:
    def test_constant_output(self) -> None:
        cd = _circuit(
            _constant("c", 3.14),
            wires=[],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        state = ev.step(0.0)
        assert abs(state["c"] - 3.14) < 1e-12

    def test_constant_zero_default(self) -> None:
        comp = {
            "id": "c0", "name": "C0", "type": "CONSTANT",
            "parameters": {},
            "pins": [_pin(0, "OUT")],
        }
        cd = _circuit(comp)
        ev = SignalEvaluator(cd)
        ev.build()
        assert ev.step(0.0)["c0"] == 0.0


class TestGain:
    def test_gain_multiplication(self) -> None:
        cd = _circuit(
            _constant("c", 2.0),
            _gain("g", 3.0),
            wires=[_wire("c", 0, "g", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        state = ev.step(0.0)
        assert abs(state["g"] - 6.0) < 1e-12

    def test_gain_no_input_yields_zero(self) -> None:
        cd = _circuit(_gain("g", 5.0))
        ev = SignalEvaluator(cd)
        ev.build()
        assert ev.step(0.0)["g"] == 0.0


class TestLimiter:
    def test_clamp_upper(self) -> None:
        cd = _circuit(
            _constant("c", 2.5),
            _limiter("l", 0.0, 1.0),
            wires=[_wire("c", 0, "l", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["l"] - 1.0) < 1e-12

    def test_clamp_lower(self) -> None:
        cd = _circuit(
            _constant("c", -5.0),
            _limiter("l", -1.0, 1.0),
            wires=[_wire("c", 0, "l", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["l"] - (-1.0)) < 1e-12

    def test_passthrough_within_limits(self) -> None:
        cd = _circuit(
            _constant("c", 0.4),
            _limiter("l", 0.0, 1.0),
            wires=[_wire("c", 0, "l", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["l"] - 0.4) < 1e-12


class TestSubtractor:
    def test_difference(self) -> None:
        sub_comp = _subtractor("sub")
        cd = _circuit(
            _constant("a", 10.0),
            _constant("b", 4.0),
            sub_comp,
            wires=[
                _wire("a", 0, "sub", 0),
                _wire("b", 0, "sub", 1),
            ],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["sub"] - 6.0) < 1e-12


class TestSum:
    def test_addition(self) -> None:
        cd = _circuit(
            _constant("a", 3.0),
            _constant("b", 1.5),
            _summer("s"),
            wires=[_wire("a", 0, "s", 0), _wire("b", 0, "s", 1)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["s"] - 4.5) < 1e-12


# ---------------------------------------------------------------------------
# PWM duty chain
# ---------------------------------------------------------------------------

class TestPWMDuty:
    def test_constant_to_pwm(self) -> None:
        cd = _circuit(
            _constant("c", 0.7),
            _pwm("pwm"),
            wires=[_wire("c", 0, "pwm", 1)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["pwm"] - 0.7) < 1e-12

    def test_pwm_duty_clamped(self) -> None:
        cd = _circuit(
            _constant("c", 1.5),
            _pwm("pwm"),
            wires=[_wire("c", 0, "pwm", 1)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.0)["pwm"] - 1.0) < 1e-12

    def test_chain_constant_gain_limiter_pwm(self) -> None:
        """CONSTANT(0.4) → GAIN(1.5) → LIMITER(0,1) → PWM: duty = 0.6"""
        cd = _circuit(
            _constant("c", 0.4),
            _gain("g", 1.5),
            _limiter("l", 0.0, 1.0),
            _pwm("pwm"),
            wires=[
                _wire("c", 0,   "g",   0),
                _wire("g", 1,   "l",   0),
                _wire("l", 1,   "pwm", 1),
            ],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        state = ev.step(0.001)
        assert abs(state["pwm"] - 0.6) < 1e-9

    def test_pwm_in_pwm_components(self) -> None:
        cd = _circuit(
            _constant("c", 0.5),
            _pwm("pwm"),
            wires=[_wire("c", 0, "pwm", 1)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert "pwm" in ev.pwm_components()

    def test_pwm_without_duty_in_not_in_components(self) -> None:
        """PWM without a DUTY_IN wire should NOT appear in pwm_components."""
        cd = _circuit(_pwm("pwm"))
        ev = SignalEvaluator(cd)
        ev.build()
        assert "pwm" not in ev.pwm_components()


# ---------------------------------------------------------------------------
# Probe feedback
# ---------------------------------------------------------------------------

class TestProbe:
    def test_update_probe_value(self) -> None:
        cd = _circuit(
            _probe("vp"),
            _gain("g", 2.0),
            wires=[_wire("vp", 0, "g", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        ev.update_probes({"vp": 3.0})
        state = ev.step(0.0)
        assert abs(state["g"] - 6.0) < 1e-12


# ---------------------------------------------------------------------------
# PI controller (Python fallback, no pulsim_module)
# ---------------------------------------------------------------------------

class TestPI:
    def test_pi_proportional_only(self) -> None:
        """With ki=0 and short time step, output = kp * error (clamped)."""
        cd = _circuit(
            _constant("ref", 0.5),
            _pi("pi", kp=0.1, ki=0.0, out_min=0.0, out_max=1.0),
            wires=[_wire("ref", 0, "pi", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        state = ev.step(0.001)
        assert abs(state["pi"] - 0.05) < 1e-9

    def test_pi_clamps_output(self) -> None:
        cd = _circuit(
            _constant("ref", 100.0),
            _pi("pi", kp=10.0, ki=0.0, out_min=0.0, out_max=1.0),
            wires=[_wire("ref", 0, "pi", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        assert abs(ev.step(0.001)["pi"] - 1.0) < 1e-12


# ---------------------------------------------------------------------------
# Algebraic loop detection
# ---------------------------------------------------------------------------

class TestAlgebraicLoop:
    def test_direct_cycle_raises(self) -> None:
        cd = _circuit(
            _gain("g1", 1.0),
            _gain("g2", 1.0),
            wires=[
                _wire("g1", 1, "g2", 0),
                _wire("g2", 1, "g1", 0),
            ],
        )
        ev = SignalEvaluator(cd)
        with pytest.raises(AlgebraicLoopError) as exc_info:
            ev.build()
        assert "G1" in str(exc_info.value) or "G2" in str(exc_info.value)

    def test_loop_error_contains_block_names(self) -> None:
        cd = _circuit(
            _gain("ga", 1.0),
            _gain("gb", 1.0),
            wires=[
                _wire("ga", 1, "gb", 0),
                _wire("gb", 1, "ga", 0),
            ],
        )
        err = AlgebraicLoopError(["GA", "GB"])
        assert "GA" in str(err)
        assert "GB" in str(err)


# ---------------------------------------------------------------------------
# has_signal_blocks
# ---------------------------------------------------------------------------

class TestHasSignalBlocks:
    def test_empty_circuit_has_no_blocks(self) -> None:
        cd = _circuit()
        ev = SignalEvaluator(cd)
        ev.build()
        assert not ev.has_signal_blocks()

    def test_circuit_with_constant_has_blocks(self) -> None:
        cd = _circuit(_constant("c", 1.0))
        ev = SignalEvaluator(cd)
        ev.build()
        assert ev.has_signal_blocks()


# ---------------------------------------------------------------------------
# reset()
# ---------------------------------------------------------------------------

class TestReset:
    def test_reset_clears_pi_integral(self) -> None:
        cd = _circuit(
            _constant("ref", 1.0),
            _pi("pi", kp=0.0, ki=1.0, out_min=-100.0, out_max=100.0),
            wires=[_wire("ref", 0, "pi", 0)],
        )
        ev = SignalEvaluator(cd)
        ev.build()
        # Let integral accumulate
        ev.step(0.0)
        ev.step(0.1)
        out_before_reset = ev.step(0.2)["pi"]
        assert out_before_reset != 0.0
        ev.reset()
        out_after_reset = ev.step(0.0)["pi"]
        # After reset the integral should be 0, kp=0 so output=0
        assert abs(out_after_reset) < 1e-9
