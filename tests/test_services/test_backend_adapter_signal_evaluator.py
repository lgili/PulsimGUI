"""Tests for the SignalEvaluator integration inside PulsimBackend.

Covers:
- Circuits **without** signal blocks run normally (no evaluator overhead).
- ``AlgebraicLoopError`` raised by the evaluator is propagated as
  ``result.error_message``.
- ``set_pwm_duty_callback`` is registered for each PWM with a DUTY_IN wire.
- When ``set_pwm_duty_callback`` is absent, falls back to ``set_pwm_duty``
  (one-shot static duty).
- The duty callback fires and returns clamped values.
- Multiple PWM components each get their own callback.
- Probe feedback: ``update_probes`` is NOT called from the adapter
  automatically (probe feedback is done via the duty callback closure).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.simulation_service import SimulationSettings


# ---------------------------------------------------------------------------
# Shared fakes
# ---------------------------------------------------------------------------

class _FakeTolerances:
    def __init__(self) -> None:
        self.voltage_abstol = 0.0
        self.voltage_reltol = 0.0
        self.current_abstol = 0.0
        self.current_reltol = 0.0

    @staticmethod
    def defaults() -> "_FakeTolerances":
        return _FakeTolerances()


class _FakeNewtonOptions:
    def __init__(self) -> None:
        self.max_iterations = 0
        self.enable_limiting = False
        self.max_voltage_step = 0.0
        self.num_nodes = 0
        self.num_branches = 0
        self.tolerances: Any = None


class _FakeCircuit:
    """Minimal circuit stub used in most tests."""

    def __init__(self) -> None:
        self._nodes: dict[str, int] = {}
        self._duty_callbacks: dict[str, Any] = {}
        self._duty_static: dict[str, float] = {}

    @staticmethod
    def ground() -> int:
        return 0

    def add_node(self, name: str) -> int:
        if name not in self._nodes:
            self._nodes[name] = len(self._nodes) + 1
        return self._nodes[name]

    def add_voltage_source(self, *_: Any) -> None: ...
    def add_resistor(self, *_: Any) -> None: ...

    def node_names(self) -> list[str]:
        return list(self._nodes)

    def num_nodes(self) -> int:
        return len(self._nodes)

    def num_branches(self) -> int:
        return 0

    def set_timestep(self, _: float) -> None: ...

    def set_pwm_duty_callback(self, name: str, cb: Any) -> None:
        self._duty_callbacks[name] = cb

    def set_pwm_duty(self, name: str, value: float) -> None:
        self._duty_static[name] = value


class _CircuitWithoutDutyCallback(_FakeCircuit):
    """Circuit that only exposes set_pwm_duty (older backend API)."""

    def set_pwm_duty_callback(self, *_: Any) -> None:  # type: ignore[override]
        raise AttributeError("not supported")

    def set_pwm_duty(self, name: str, value: float) -> None:
        self._duty_static[name] = value


# Variants of _FakeCircuit to simulate missing set_pwm_duty_callback attr
class _CircuitNoDutyCb(_FakeCircuit):
    pass


# ---------------------------------------------------------------------------
# Circuit-data helpers
# ---------------------------------------------------------------------------

def _pin(index: int, name: str) -> dict:
    return {"index": index, "name": name, "x": 0.0, "y": 0.0}


def _resistor_circuit_data() -> dict:
    """Minimal 2-component circuit with NO signal blocks."""
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {"waveform": {"type": "dc", "value": 5.0}},
                "pin_nodes": ["1", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 1000.0},
                "pin_nodes": ["1", "0"],
            },
        ],
        "node_map": {"v1": ["1", "0"], "r1": ["1", "0"]},
        "node_aliases": {"1": "OUT", "0": "0"},
        "wires": [],
    }


def _pwm_circuit_data(duty: float = 0.6) -> dict:
    """Circuit data with CONSTANT → PWM chain (DUTY_IN connected)."""
    return {
        "components": [
            {
                "id": "v1",
                "type": "VOLTAGE_SOURCE",
                "name": "V1",
                "parameters": {"waveform": {"type": "dc", "value": 12.0}},
                "pin_nodes": ["1", "0"],
            },
            {
                "id": "r1",
                "type": "RESISTOR",
                "name": "R1",
                "parameters": {"resistance": 10.0},
                "pin_nodes": ["1", "2"],
            },
            {
                "id": "c1",
                "type": "CONSTANT",
                "name": "REF",
                "parameters": {"value": duty},
                "pins": [_pin(0, "OUT")],
                "pin_nodes": [],
            },
            {
                "id": "pwm1",
                "type": "PWM_GENERATOR",
                "name": "PWM1",
                "parameters": {"frequency": 10000, "duty_cycle": 0.5},
                "pins": [_pin(0, "OUT"), _pin(1, "DUTY_IN")],
                "pin_nodes": ["2", ""],
            },
        ],
        "node_map": {"v1": ["1", "0"], "r1": ["1", "2"], "pwm1": ["2", ""]},
        "node_aliases": {"1": "VIN", "2": "SW", "0": "0"},
        "wires": [
            {
                "start_connection": {"component_id": "c1",   "pin_index": 0},
                "end_connection":   {"component_id": "pwm1", "pin_index": 1},
            }
        ],
    }


def _two_pwm_circuit_data() -> dict:
    """Circuit with two independent CONSTANT → PWM chains."""
    return {
        "components": [
            {
                "id": "c1",
                "type": "CONSTANT",
                "name": "REF1",
                "parameters": {"value": 0.3},
                "pins": [_pin(0, "OUT")],
                "pin_nodes": [],
            },
            {
                "id": "c2",
                "type": "CONSTANT",
                "name": "REF2",
                "parameters": {"value": 0.7},
                "pins": [_pin(0, "OUT")],
                "pin_nodes": [],
            },
            {
                "id": "pwm1",
                "type": "PWM_GENERATOR",
                "name": "PWM1",
                "parameters": {"frequency": 10000, "duty_cycle": 0.5},
                "pins": [_pin(0, "OUT"), _pin(1, "DUTY_IN")],
                "pin_nodes": [],
            },
            {
                "id": "pwm2",
                "type": "PWM_GENERATOR",
                "name": "PWM2",
                "parameters": {"frequency": 10000, "duty_cycle": 0.5},
                "pins": [_pin(0, "OUT"), _pin(1, "DUTY_IN")],
                "pin_nodes": [],
            },
        ],
        "node_map": {},
        "node_aliases": {},
        "wires": [
            {
                "start_connection": {"component_id": "c1",   "pin_index": 0},
                "end_connection":   {"component_id": "pwm1", "pin_index": 1},
            },
            {
                "start_connection": {"component_id": "c2",   "pin_index": 0},
                "end_connection":   {"component_id": "pwm2", "pin_index": 1},
            },
        ],
    }


def _algebraic_loop_circuit_data() -> dict:
    """Two GAIN blocks in a direct feed-through cycle → AlgebraicLoopError."""
    return {
        "components": [
            {
                "id": "g1",
                "type": "GAIN",
                "name": "G1",
                "parameters": {"gain": 1.0},
                "pins": [_pin(0, "IN"), _pin(1, "OUT")],
                "pin_nodes": [],
            },
            {
                "id": "g2",
                "type": "GAIN",
                "name": "G2",
                "parameters": {"gain": 1.0},
                "pins": [_pin(0, "IN"), _pin(1, "OUT")],
                "pin_nodes": [],
            },
        ],
        "node_map": {},
        "node_aliases": {},
        "wires": [
            {
                "start_connection": {"component_id": "g1", "pin_index": 1},
                "end_connection":   {"component_id": "g2", "pin_index": 0},
            },
            {
                "start_connection": {"component_id": "g2", "pin_index": 1},
                "end_connection":   {"component_id": "g1", "pin_index": 0},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Backend factory
# ---------------------------------------------------------------------------

_DEFAULT_SETTINGS = SimulationSettings(
    t_start=0.0,
    t_stop=1e-3,
    t_step=1e-6,
    max_step=5e-6,
    rel_tol=1e-5,
    abs_tol=1e-8,
)

_DEFAULT_CALLBACKS = BackendCallbacks(
    progress=lambda *_: None,
    data_point=lambda *_: None,
    check_cancelled=lambda: False,
    wait_if_paused=lambda: None,
)


def _make_backend(circuit_class: type = _FakeCircuit) -> PulsimBackend:
    """Return a PulsimBackend backed by a simple fake module."""

    def run_transient(circuit, t_start, t_stop, dt, *args, **kwargs):  # noqa: ANN001
        _ = (circuit, t_start, t_stop, dt, args, kwargs)
        # Return two time-points with a single node signal
        states: list[list[float]] = [[0.0], [5.0]]
        return [t_start, t_stop], states, True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=circuit_class,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
    )
    return PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )


def _run_with_fake_circuit(
    circuit_data: dict,
    fake_circuit: _FakeCircuit | None = None,
    circuit_class: type = _FakeCircuit,
) -> tuple[Any, _FakeCircuit]:
    """Run transient with CircuitConverter.build patched to ``fake_circuit``.

    Bypasses the need for real pulsim types (PWMParams etc.) while exercising
    the full adapter -> signal-evaluator -> _attach_signal_evaluator path.
    Returns (result, fake_circuit).
    """
    if fake_circuit is None:
        fake_circuit = circuit_class()
    backend = _make_backend(circuit_class)
    with patch.object(backend._converter, "build", return_value=fake_circuit):
        result = backend.run_transient(circuit_data, _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS)
    return result, fake_circuit


# ---------------------------------------------------------------------------
# Tests: no-signal-blocks path
# ---------------------------------------------------------------------------

class TestNoSignalBlocks:
    def test_plain_circuit_runs_successfully(self) -> None:
        backend = _make_backend()
        result = backend.run_transient(
            _resistor_circuit_data(), _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS
        )
        assert result.error_message == ""

    def test_plain_circuit_does_not_call_set_pwm_duty(self) -> None:
        circuit_instance: list[_FakeCircuit] = []

        class _CapturingCircuit(_FakeCircuit):
            def __init__(self) -> None:
                super().__init__()
                circuit_instance.append(self)

        backend = _make_backend(_CapturingCircuit)
        backend.run_transient(_resistor_circuit_data(), _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS)

        assert circuit_instance, "circuit was never instantiated"
        # No duty interactions expected on a plain resistor circuit
        assert circuit_instance[-1]._duty_callbacks == {}
        assert circuit_instance[-1]._duty_static == {}


# ---------------------------------------------------------------------------
# Tests: AlgebraicLoopError propagation
# ---------------------------------------------------------------------------

class TestAlgebraicLoopErrorPropagation:
    def test_algebraic_loop_gives_non_empty_error_message(self) -> None:
        backend = _make_backend()
        result = backend.run_transient(
            _algebraic_loop_circuit_data(), _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS
        )
        assert result.error_message != ""

    def test_algebraic_loop_error_message_mentions_block_name(self) -> None:
        backend = _make_backend()
        result = backend.run_transient(
            _algebraic_loop_circuit_data(), _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS
        )
        # Error should reference at least one of the looping blocks
        msg = result.error_message.upper()
        assert "G1" in msg or "G2" in msg or "LOOP" in msg or "ALGEBRAIC" in msg

    def test_algebraic_loop_does_not_reach_run_transient(self) -> None:
        calls: dict[str, int] = {"count": 0}

        def run_transient(*_args, **_kwargs):  # noqa: ANN001
            calls["count"] += 1
            return [0.0, 1e-3], [[0.0], [1.0]], True, ""

        fake_module = SimpleNamespace(
            __version__="2.0.0",
            Circuit=_FakeCircuit,
            NewtonOptions=_FakeNewtonOptions,
            Tolerances=_FakeTolerances,
            run_transient=run_transient,
        )
        backend = PulsimBackend(
            fake_module,
            BackendInfo(identifier="pulsim", name="Pulsim", version="2.0.0", status="available"),
        )
        backend.run_transient(_algebraic_loop_circuit_data(), _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS)
        # run_transient must NOT have been called — error is caught before simulation
        assert calls["count"] == 0


# ---------------------------------------------------------------------------
# Tests: set_pwm_duty_callback registered
# ---------------------------------------------------------------------------

class TestDutyCallbackRegistration:
    def test_one_callback_registered_for_pwm_component(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data())
        assert len(circuit._duty_callbacks) == 1

    def test_callback_key_is_pwm_component_name(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data())
        assert "PWM1" in circuit._duty_callbacks

    def test_callback_is_callable(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data())
        assert callable(circuit._duty_callbacks["PWM1"])

    def test_callback_returns_correct_duty(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data(duty=0.6))
        assert abs(circuit._duty_callbacks["PWM1"](0.0) - 0.6) < 1e-9

    def test_callback_clamps_duty_above_one(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data(duty=1.8))
        assert circuit._duty_callbacks["PWM1"](0.0) <= 1.0

    def test_callback_clamps_duty_below_zero(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data(duty=-0.5))
        assert circuit._duty_callbacks["PWM1"](0.0) >= 0.0

    def test_callback_accepts_any_time_argument(self) -> None:
        _, circuit = _run_with_fake_circuit(_pwm_circuit_data(duty=0.5))
        cb = circuit._duty_callbacks["PWM1"]
        for t in (0.0, 1e-6, 1e-3, 1.0):
            assert 0.0 <= cb(t) <= 1.0

    def test_two_pwm_components_each_get_own_callback(self) -> None:
        _, circuit = _run_with_fake_circuit(_two_pwm_circuit_data())
        assert "PWM1" in circuit._duty_callbacks
        assert "PWM2" in circuit._duty_callbacks

    def test_two_pwm_callbacks_return_independent_values(self) -> None:
        _, circuit = _run_with_fake_circuit(_two_pwm_circuit_data())
        assert abs(circuit._duty_callbacks["PWM1"](0.0) - 0.3) < 1e-9
        assert abs(circuit._duty_callbacks["PWM2"](0.0) - 0.7) < 1e-9


# ---------------------------------------------------------------------------
# Tests: static duty fallback (older backend without set_pwm_duty_callback)
# ---------------------------------------------------------------------------

class TestStaticDutyFallback:
    """When backend only exposes ``set_pwm_duty``, a one-shot value must be written."""

    def _run_static(self, duty: float = 0.4) -> Any:
        class _NoDutyCbCircuit:
            """Circuit that intentionally lacks set_pwm_duty_callback."""

            def __init__(self) -> None:
                self._nodes: dict[str, int] = {}
                self._duty_static: dict[str, float] = {}

            @staticmethod
            def ground() -> int:
                return 0

            def add_node(self, name: str) -> int:
                if name not in self._nodes:
                    self._nodes[name] = len(self._nodes) + 1
                return self._nodes[name]

            def add_voltage_source(self, *_: Any) -> None: ...
            def add_resistor(self, *_: Any) -> None: ...
            def node_names(self) -> list[str]: return list(self._nodes)
            def num_nodes(self) -> int: return len(self._nodes)
            def num_branches(self) -> int: return 0
            def set_timestep(self, _: float) -> None: ...

            def set_pwm_duty(self, name: str, value: float) -> None:
                self._duty_static[name] = value

        fake = _NoDutyCbCircuit()
        _, result_circuit = _run_with_fake_circuit(
            _pwm_circuit_data(duty),
            fake_circuit=fake,  # type: ignore[arg-type]
        )
        return result_circuit

    def test_static_duty_written_when_callback_unavailable(self) -> None:
        circuit = self._run_static(duty=0.4)
        assert len(circuit._duty_static) == 1

    def test_static_duty_value_is_correct(self) -> None:
        circuit = self._run_static(duty=0.4)
        value = next(iter(circuit._duty_static.values()))
        assert abs(value - 0.4) < 1e-9

    def test_static_duty_is_clamped_to_0_1(self) -> None:
        circuit = self._run_static(duty=2.5)
        value = next(iter(circuit._duty_static.values()))
        assert 0.0 <= value <= 1.0


# ---------------------------------------------------------------------------
# Tests: simulation still succeeds with signal blocks present
# ---------------------------------------------------------------------------

class TestTransientSuccessWithSignalBlocks:
    def test_run_succeeds_with_constant_to_pwm(self) -> None:
        result, _ = _run_with_fake_circuit(_pwm_circuit_data(0.5))
        assert result.error_message == ""

    def test_run_returns_time_vector(self) -> None:
        result, _ = _run_with_fake_circuit(_pwm_circuit_data(0.5))
        assert len(result.time) >= 2

    def test_run_succeeds_two_pwm_components(self) -> None:
        result, _ = _run_with_fake_circuit(_two_pwm_circuit_data())
        assert result.error_message == ""
