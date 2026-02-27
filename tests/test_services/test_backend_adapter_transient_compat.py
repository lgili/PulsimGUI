"""Compatibility tests for transient execution across Pulsim API variants."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.simulation_service import SimulationSettings


class _FakeCircuit:
    def __init__(self) -> None:
        self._nodes: dict[str, int] = {}
        self._ordered_nodes: list[str] = []
        self._timestep: float | None = None

    @staticmethod
    def ground() -> int:
        return 0

    def add_node(self, name: str) -> int:
        if name in self._nodes:
            return self._nodes[name]
        idx = len(self._ordered_nodes) + 1
        self._nodes[name] = idx
        self._ordered_nodes.append(name)
        return idx

    def add_voltage_source(self, name: str, npos: int, nneg: int, value: float) -> None:
        _ = (name, npos, nneg, value)

    def add_resistor(self, name: str, n1: int, n2: int, resistance: float) -> None:
        _ = (name, n1, n2, resistance)

    def node_names(self) -> list[str]:
        return self._ordered_nodes.copy()

    def num_nodes(self) -> int:
        return len(self._ordered_nodes)

    def num_branches(self) -> int:
        return 0

    def set_timestep(self, dt: float) -> None:
        self._timestep = dt


class _FakeCircuitWithSignals(_FakeCircuit):
    def signal_names(self) -> list[str]:
        return ["V(OUT)", "I(V1)"]

    def num_branches(self) -> int:
        return 1


class _FakeTolerances:
    def __init__(self) -> None:
        self.voltage_abstol = 0.0
        self.voltage_reltol = 0.0
        self.current_abstol = 0.0
        self.current_reltol = 0.0

    @staticmethod
    def defaults() -> _FakeTolerances:
        return _FakeTolerances()


class _FakeNewtonOptions:
    def __init__(self) -> None:
        self.max_iterations = 0
        self.enable_limiting = False
        self.max_voltage_step = 0.0
        self.num_nodes = 0
        self.num_branches = 0
        self.tolerances: Any = None


def _simple_circuit_data() -> dict[str, Any]:
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


def test_transient_runs_without_linear_solver_stack() -> None:
    """Backend adapter should support APIs where LinearSolverStackConfig is absent."""

    seen: dict[str, Any] = {}

    def run_transient_streaming(circuit, t_start, t_stop, dt, *args):  # noqa: ANN001
        # Expected shape for modern API:
        # (newton_opts, data_cb, progress_cb, cancel_cb, emit_interval)
        assert len(args) == 5
        newton_opts, data_callback, progress_callback, cancel_check, emit_interval = args
        assert isinstance(newton_opts, _FakeNewtonOptions)
        assert callable(data_callback)
        assert callable(progress_callback)
        assert callable(cancel_check)
        assert emit_interval >= 1

        seen["arg_count"] = len(args)
        seen["dt"] = dt
        progress_callback(50.0, "Halfway")
        data_callback(t_stop, {"V(OUT)": 1.0})
        return [t_start, t_stop], [[0.0], [1.0]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient_streaming=run_transient_streaming,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )

    settings = SimulationSettings(
        t_start=0.0,
        t_stop=1e-3,
        t_step=1e-6,
        max_step=5e-6,
        rel_tol=1e-5,
        abs_tol=1e-8,
    )
    circuit_data = _simple_circuit_data()

    result = backend.run_transient(
        circuit_data,
        settings,
        BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        ),
    )

    assert result.error_message == ""
    assert len(result.time) == 2
    assert result.signals["V(OUT)"] == [0.0, 1.0]
    assert seen["arg_count"] == 5
    assert seen["dt"] == settings.t_step


def test_transient_retries_convergence_failures_with_stronger_profile() -> None:
    """Transient should retry with stronger options when Newton diverges."""
    calls: list[dict[str, Any]] = []

    def run_transient_streaming(circuit, t_start, t_stop, dt, *args):  # noqa: ANN001
        newton_opts = args[0]
        calls.append(
            {
                "dt": dt,
                "max_iterations": newton_opts.max_iterations,
                "enable_limiting": newton_opts.enable_limiting,
                "max_voltage_step": newton_opts.max_voltage_step,
            }
        )
        if len(calls) == 1:
            return [], [], False, "Transient failed at t=0.000020: Newton iteration diverging"
        return [t_start, t_stop], [[0.0], [1.5]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient_streaming=run_transient_streaming,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )

    settings = SimulationSettings(
        t_start=0.0,
        t_stop=1e-3,
        t_step=1e-6,
        max_step=5e-6,
        rel_tol=1e-5,
        abs_tol=1e-8,
        max_newton_iterations=50,
        enable_voltage_limiting=False,
        max_voltage_step=5.0,
    )

    result = backend.run_transient(
        _simple_circuit_data(),
        settings,
        BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        ),
    )

    assert result.error_message == ""
    assert len(result.time) == 2
    assert result.signals["V(OUT)"] == [0.0, 1.5]
    assert len(calls) == 2
    assert calls[0]["max_iterations"] == 50
    assert calls[1]["max_iterations"] >= 100
    assert result.statistics["convergence_retry_profile"] == "gmin-seed"
    assert result.statistics["convergence_retries"] == 1


def test_transient_does_not_retry_non_convergence_errors() -> None:
    """Transient retries should not run for non-convergence failures."""
    calls = {"count": 0}

    def run_transient_streaming(circuit, t_start, t_stop, dt, *args):  # noqa: ANN001
        _ = (circuit, t_start, t_stop, dt, args)
        calls["count"] += 1
        return [], [], False, "Unsupported transient API signature"

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient_streaming=run_transient_streaming,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )

    result = backend.run_transient(
        _simple_circuit_data(),
        SimulationSettings(),
        BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        ),
    )

    assert calls["count"] == 1
    assert result.error_message == "Unsupported transient API signature"


def test_transient_prefers_run_transient_and_passes_robust_kwargs() -> None:
    """Adapter should prefer run_transient and forward robust mode kwargs."""
    seen: dict[str, Any] = {"streaming_calls": 0}

    def run_transient(circuit, t_start, t_stop, dt, *args, robust=True, auto_regularize=True):  # noqa: ANN001
        _ = (circuit, t_start, dt)
        newton_opts = args[0]
        seen["robust"] = robust
        seen["auto_regularize"] = auto_regularize
        seen["max_iterations"] = newton_opts.max_iterations
        return [t_start, t_stop], [[0.0], [2.0]], True, ""

    def run_transient_streaming(*_args, **_kwargs):  # noqa: ANN001
        seen["streaming_calls"] += 1
        return [], [], False, "should not be called"

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
        run_transient_streaming=run_transient_streaming,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )

    settings = SimulationSettings(
        transient_robust_mode=False,
        transient_auto_regularize=False,
        max_newton_iterations=77,
    )

    result = backend.run_transient(
        _simple_circuit_data(),
        settings,
        BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        ),
    )

    assert result.error_message == ""
    assert result.signals["V(OUT)"] == [0.0, 2.0]
    assert seen["robust"] is False
    assert seen["auto_regularize"] is False
    assert seen["max_iterations"] == 77
    assert seen["streaming_calls"] == 0


def test_transient_uses_signal_names_when_available() -> None:
    """Adapter should expose full signal_names() (including branch currents)."""

    def run_transient(circuit, t_start, t_stop, dt, *args, **_kwargs):  # noqa: ANN001
        _ = (circuit, t_start, t_stop, dt, args)
        return [t_start, t_stop], [[0.0, -0.001], [1.0, -0.002]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuitWithSignals,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="2.0.0",
            status="available",
        ),
    )

    result = backend.run_transient(
        _simple_circuit_data(),
        SimulationSettings(),
        BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: False,
            wait_if_paused=lambda: None,
        ),
    )

    assert result.error_message == ""
    assert result.signals["V(OUT)"] == [0.0, 1.0]
    assert result.signals["I(V1)"] == [-0.001, -0.002]
