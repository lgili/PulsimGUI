"""Backend adapter control-path tests without legacy SignalEvaluator usage."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.simulation_service import SimulationSettings


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
    def __init__(self) -> None:
        self._nodes: dict[str, int] = {}
        self.virtual_components: list[tuple[str, str, list[int], dict[str, float], dict[str, str]]] = []
        self.switches: list[tuple[str, int, int, bool, float, float]] = []

    @staticmethod
    def ground() -> int:
        return 0

    def add_node(self, name: str) -> int:
        if name not in self._nodes:
            self._nodes[name] = len(self._nodes) + 1
        return self._nodes[name]

    def node_names(self) -> list[str]:
        return list(self._nodes)

    def num_nodes(self) -> int:
        return len(self._nodes)

    def num_branches(self) -> int:
        return 0

    def set_timestep(self, _: float) -> None:
        return

    def add_virtual_component(
        self,
        comp_type: str,
        name: str,
        nodes: list[int],
        numeric_params: dict[str, float],
        metadata: dict[str, str],
    ) -> None:
        self.virtual_components.append((comp_type, name, list(nodes), dict(numeric_params), dict(metadata)))

    def add_switch(
        self,
        name: str,
        n1: int,
        n2: int,
        closed: bool,
        g_on: float,
        g_off: float,
    ) -> None:
        self.switches.append((name, n1, n2, closed, g_on, g_off))


class _NoLegacyDutyCircuit(_FakeCircuit):
    """Fails fast if any legacy Python duty path is called."""

    def set_pwm_duty_callback(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("legacy set_pwm_duty_callback must not be used")

    def set_pwm_duty(self, *_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("legacy set_pwm_duty must not be used")


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


def _make_backend(circuit_class: type, *, call_counter: dict[str, int] | None = None) -> PulsimBackend:
    def run_transient(circuit, t_start, t_stop, dt, *args, **kwargs):  # noqa: ANN001
        _ = (circuit, t_start, t_stop, dt, args, kwargs)
        if call_counter is not None:
            call_counter["calls"] += 1
        return [t_start, t_stop], [[0.0], [1.0]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=circuit_class,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
    )
    return PulsimBackend(
        fake_module,
        BackendInfo(identifier="pulsim", name="Pulsim", version="2.0.0", status="available"),
    )


def test_control_circuit_does_not_use_legacy_python_duty_callbacks() -> None:
    backend = _make_backend(_NoLegacyDutyCircuit)
    circuit_data = {
        "components": [
            {
                "id": "pi1",
                "type": "PI_CONTROLLER",
                "name": "PI1",
                "parameters": {"kp": 0.1, "ki": 10.0, "output_min": 0.0, "output_max": 0.95},
                "pin_nodes": ["1", "2", "0"],
            },
            {
                "id": "pwm1",
                "type": "PWM_GENERATOR",
                "name": "PWM1",
                "parameters": {
                    "frequency": 10000.0,
                    "duty_cycle": 0.5,
                    "duty_from_channel": "PI1",
                    "target_component": "S1",
                },
                "pin_nodes": ["3"],
            },
            {
                "id": "s1",
                "type": "SWITCH",
                "name": "S1",
                "parameters": {"initial_state": False, "ron": 1e-3, "roff": 1e9},
                "pin_nodes": ["3", "4"],
            },
        ],
        "node_map": {
            "pi1": ["1", "2", "0"],
            "pwm1": ["3"],
            "s1": ["3", "4"],
        },
        "node_aliases": {"0": "0", "1": "REF", "2": "FB", "3": "GATE", "4": "SW"},
    }

    result = backend.run_transient(circuit_data, _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS)

    assert result.error_message == ""


def test_signal_blocks_are_executed_by_backend_without_frontend_precheck_block() -> None:
    call_counter = {"calls": 0}
    backend = _make_backend(_FakeCircuit, call_counter=call_counter)
    circuit_data = {
        "components": [
            {
                "id": "g1",
                "type": "GAIN",
                "name": "G1",
                "parameters": {"gain": 2.0},
                "pin_nodes": ["1", "2"],
            }
        ],
        "node_map": {"g1": ["1", "2"]},
        "node_aliases": {"1": "IN", "2": "OUT", "0": "0"},
    }

    result = backend.run_transient(circuit_data, _DEFAULT_SETTINGS, _DEFAULT_CALLBACKS)

    assert result.error_message == ""
    assert call_counter["calls"] == 1
