"""Compatibility tests for transient execution across Pulsim API variants."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from pulsimgui.services.backend_adapter import BackendCallbacks, BackendInfo, PulsimBackend
from pulsimgui.services.backend_types import ThermalSettings, TransientResult
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


def test_transient_skips_simulation_options_for_legacy_backend_versions() -> None:
    """Legacy backends should use compatibility transient path even if Simulator exists."""
    seen: dict[str, int] = {"run_transient_calls": 0, "simulator_calls": 0}

    class _SimulationOptions:
        pass

    class _Simulator:
        def __init__(self, _circuit, _options):  # noqa: ANN001
            pass

        def run_transient(self, *_args):  # noqa: ANN002
            seen["simulator_calls"] += 1
            return SimpleNamespace(time=[0.0, 1e-3], states=[[0.0], [1.0]], success=True, message="")

    def run_transient(circuit, t_start, t_stop, dt, *args, **_kwargs):  # noqa: ANN001
        _ = (circuit, dt, args)
        seen["run_transient_calls"] += 1
        return [t_start, t_stop], [[0.0], [1.0]], True, ""

    fake_module = SimpleNamespace(
        __version__="0.5.1",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
        SimulationOptions=_SimulationOptions,
        Simulator=_Simulator,
    )

    backend = PulsimBackend(
        fake_module,
        BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version="0.5.1",
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
    assert seen["run_transient_calls"] == 1
    assert seen["simulator_calls"] == 0


def test_transient_uses_simulation_options_without_modern_markers() -> None:
    """SimulationOptions path should work even when progress marker classes are absent."""
    seen: dict[str, int] = {"run_transient_calls": 0, "simulator_calls": 0}

    class _SimulationOptions:
        pass

    class _Simulator:
        def __init__(self, _circuit, _options):  # noqa: ANN001
            pass

        def run_transient(self, *_args):  # noqa: ANN002
            seen["simulator_calls"] += 1
            return SimpleNamespace(time=[0.0, 1e-3], states=[[0.0], [1.0]], success=True, message="")

    def run_transient(circuit, t_start, t_stop, dt, *args, **_kwargs):  # noqa: ANN001
        _ = (circuit, dt, args)
        seen["run_transient_calls"] += 1
        return [t_start, t_stop], [[0.0], [1.0]], True, ""

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        run_transient=run_transient,
        SimulationOptions=_SimulationOptions,
        Simulator=_Simulator,
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
    assert seen["run_transient_calls"] == 0
    assert seen["simulator_calls"] == 1


def test_transient_uses_simulation_options_for_new_backend_controls() -> None:
    """Adapter should use SimulationOptions path when advanced controls are requested."""
    seen: dict[str, Any] = {"run_transient_calls": 0}

    class _StepMode:
        Fixed = "fixed"
        Variable = "variable"

    class _Integrator:
        Trapezoidal = "trap"
        TRBDF2 = "trbdf2"

    class _FormulationMode:
        ProjectedWrapper = "projected"
        Direct = "direct"

    class _ControlUpdateMode:
        Auto = "auto"
        Continuous = "continuous"
        Discrete = "discrete"

    class _ThermalDeviceTelemetry:
        def __init__(self) -> None:
            self.device_name = "M1"
            self.enabled = True
            self.final_temperature = 61.0
            self.peak_temperature = 73.0
            self.average_temperature = 58.0

    class _ThermalSummary:
        def __init__(self) -> None:
            self.enabled = True
            self.ambient = 25.0
            self.max_temperature = 73.0
            self.device_temperatures = [_ThermalDeviceTelemetry()]

    class _ComponentElectrothermal:
        def __init__(self) -> None:
            self.component_name = "M1"
            self.thermal_enabled = True
            self.conduction = 1.2
            self.turn_on = 0.3
            self.turn_off = 0.25
            self.reverse_recovery = 0.0
            self.total_loss = 1.75
            self.total_energy = 0.0175
            self.average_power = 1.75
            self.peak_power = 3.1
            self.final_temperature = 61.0
            self.peak_temperature = 73.0
            self.average_temperature = 58.0

    class _LinearSolverTelemetry:
        def __init__(self) -> None:
            self.total_solve_calls = 11
            self.total_analyze_calls = 4
            self.total_factorize_calls = 4
            self.total_iterations = 19
            self.total_fallbacks = 0
            self.last_iterations = 2
            self.last_error = 0.0
            self.total_analyze_time_seconds = 0.001
            self.total_factorize_time_seconds = 0.002
            self.total_solve_time_seconds = 0.003
            self.last_analyze_time_seconds = 0.0001
            self.last_factorize_time_seconds = 0.0002
            self.last_solve_time_seconds = 0.0003
            self.last_solver = "KLU"
            self.last_preconditioner = "none"

    class _BackendTelemetry:
        def __init__(self) -> None:
            self.requested_backend = "auto"
            self.selected_backend = "native"
            self.solver_family = "dae"
            self.formulation_mode = "projected_wrapper"
            self.function_evaluations = 50
            self.jacobian_evaluations = 12
            self.nonlinear_iterations = 23
            self.nonlinear_convergence_failures = 0
            self.error_test_failures = 0
            self.escalation_count = 0
            self.reinitialization_count = 0
            self.backend_recovery_count = 0
            self.state_space_primary_steps = 200
            self.dae_fallback_steps = 0
            self.segment_non_admissible_steps = 0
            self.segment_model_cache_hits = 10
            self.segment_model_cache_misses = 2
            self.linear_factor_cache_hits = 15
            self.linear_factor_cache_misses = 1
            self.linear_factor_cache_invalidations = 0
            self.linear_factor_cache_last_invalidation_reason = ""
            self.reserved_output_samples = 4096
            self.time_series_reallocations = 0
            self.state_series_reallocations = 0
            self.virtual_channel_reallocations = 0
            self.equation_assemble_system_calls = 300
            self.equation_assemble_residual_calls = 0
            self.equation_assemble_system_time_seconds = 0.01
            self.equation_assemble_residual_time_seconds = 0.0
            self.model_regularization_events = 0
            self.model_regularization_last_changed = ""
            self.model_regularization_last_intensity = 0.0
            self.failure_reason = ""

    class _FallbackTraceEntry:
        def __init__(self) -> None:
            self.step_index = 7
            self.retry_index = 1
            self.time = 2.0e-6
            self.dt = 5.0e-7
            self.reason = "nonlinear_residual"
            self.solver_status = "RetryScheduled"
            self.action = "reduce_dt"

    class _LossBreakdown:
        def __init__(self) -> None:
            self.conduction = 1.2
            self.turn_on = 0.3
            self.turn_off = 0.25
            self.reverse_recovery = 0.0

    class _LossResult:
        def __init__(self) -> None:
            self.device_name = "M1"
            self.breakdown = _LossBreakdown()
            self.total_energy = 0.0175
            self.average_power = 1.75
            self.peak_power = 3.1
            self.rms_current = 4.2
            self.avg_current = 3.0
            self.efficiency_contribution = 0.98

    class _SystemLossSummary:
        def __init__(self) -> None:
            self.device_losses = {"M1": _LossResult()}
            self.total_loss = 1.75
            self.total_conduction = 1.2
            self.total_switching = 0.55
            self.input_power = 100.0
            self.output_power = 98.25
            self.efficiency = 98.25

    class _SimulationOptions:
        class _Thermal:
            def __init__(self) -> None:
                self.ambient = 25.0
                self.enable = True
                self.policy = None
                self.default_rth = 1.0
                self.default_cth = 0.1

        def __init__(self) -> None:
            self.tstart = 0.0
            self.tstop = 0.0
            self.dt = 0.0
            self.dt_min = 0.0
            self.dt_max = 0.0
            self.newton_options = None
            self.linear_solver = None
            self.adaptive_timestep = False
            self.step_mode = _StepMode.Fixed
            self.integrator = _Integrator.TRBDF2
            self.enable_events = True
            self.max_step_retries = 8
            self.enable_losses = True
            self.formulation_mode = _FormulationMode.ProjectedWrapper
            self.direct_formulation_fallback = True
            self.control_mode = _ControlUpdateMode.Auto
            self.control_sample_time = 0.0
            self.thermal = self._Thermal()
            self.switching_energy: dict[str, Any] = {}
            self.thermal_devices: dict[str, Any] = {}

    class _ThermalCouplingPolicy:
        LossOnly = object()
        LossWithTemperatureScaling = object()

    class _SwitchingEnergy:
        def __init__(self) -> None:
            self.eon = 0.0
            self.eoff = 0.0
            self.err = 0.0

    class _ThermalDeviceConfig:
        def __init__(self) -> None:
            self.enabled = True
            self.rth = 1.0
            self.cth = 0.1
            self.temp_init = 25.0
            self.temp_ref = 25.0
            self.alpha = 0.004

    class _SimulationController:
        pass

    class _ProgressCallbackConfig:
        pass

    class _SimulationProgress:
        pass

    class _VirtualChannelMeta:
        def __init__(self, component_type: str, source_component: str, domain: str, unit: str) -> None:
            self.component_type = component_type
            self.source_component = source_component
            self.domain = domain
            self.unit = unit

    class _Simulator:
        def __init__(self, circuit, options) -> None:  # noqa: ANN001
            _ = circuit
            seen["options"] = options

        def run_transient(self, x0=None):  # noqa: ANN001
            _ = x0
            return SimpleNamespace(
                time=[0.0, 1e-6],
                states=[[0.0], [1.25]],
                virtual_channels={
                    "PI1": [0.2, 0.25],
                    "PWM1.duty": [0.45, 0.5],
                    "Xout": [0.0, 1.25],
                    "T(M1)": [25.0, 26.5],
                },
                virtual_channel_metadata={
                    "PI1": _VirtualChannelMeta("pi_controller", "PI1", "control", ""),
                    "PWM1.duty": _VirtualChannelMeta("pwm_generator", "PWM1", "control", ""),
                    "Xout": _VirtualChannelMeta("voltage_probe", "Xout", "instrumentation", "V"),
                    "T(M1)": _VirtualChannelMeta("thermal_trace", "M1", "thermal", "degC"),
                },
                success=True,
                message="",
                total_steps=2,
                newton_iterations_total=3,
                timestep_rejections=0,
                total_time_seconds=0.004,
                final_status=SimpleNamespace(name="Success"),
                diagnostic=SimpleNamespace(name="None"),
                linear_solver_telemetry=_LinearSolverTelemetry(),
                fallback_trace=[_FallbackTraceEntry()],
                backend_telemetry=_BackendTelemetry(),
                loss_summary=_SystemLossSummary(),
                thermal_summary=_ThermalSummary(),
                component_electrothermal=[_ComponentElectrothermal()],
            )

    def run_transient(*_args, **_kwargs):  # noqa: ANN001
        seen["run_transient_calls"] += 1
        return [], [], False, "legacy path should not be used"

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        NewtonOptions=_FakeNewtonOptions,
        Tolerances=_FakeTolerances,
        SimulationOptions=_SimulationOptions,
        Simulator=_Simulator,
        StepMode=_StepMode,
        Integrator=_Integrator,
        FormulationMode=_FormulationMode,
        ControlUpdateMode=_ControlUpdateMode,
        ThermalCouplingPolicy=_ThermalCouplingPolicy,
        SwitchingEnergy=_SwitchingEnergy,
        ThermalDeviceConfig=_ThermalDeviceConfig,
        SimulationController=_SimulationController,
        ProgressCallbackConfig=_ProgressCallbackConfig,
        SimulationProgress=_SimulationProgress,
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

    settings = SimulationSettings(
        solver="trapezoidal",
        step_mode="variable",
        enable_events=False,
        max_step_retries=12,
        enable_losses=False,
        thermal_policy="loss_only",
        thermal_default_rth=2.1,
        thermal_default_cth=0.33,
        formulation_mode="direct",
        direct_formulation_fallback=False,
        control_mode="discrete",
        control_sample_time=5e-6,
        t_start=0.0,
        t_stop=1e-3,
        t_step=1e-6,
    )

    circuit_data = _simple_circuit_data()
    circuit_data["components"][1]["parameters"].update(
        {
            "switching_eon_j": 1.2e-6,
            "switching_eoff_j": 2.4e-6,
            "switching_err_j": 3.6e-6,
            "thermal_enabled": False,
            "thermal_rth": 4.4,
            "thermal_cth": 0.55,
            "thermal_temp_init": 45.0,
            "thermal_temp_ref": 35.0,
            "thermal_alpha": 0.007,
        }
    )

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
    assert result.signals["V(OUT)"] == [0.0, 1.25]
    assert result.signals["PI1"] == [0.2, 0.25]
    assert result.signals["PWM1.duty"] == [0.45, 0.5]
    assert result.signals["Xout"] == [0.0, 1.25]
    assert result.signals["T(M1)"] == [25.0, 26.5]
    assert seen["run_transient_calls"] == 0
    assert seen["options"].adaptive_timestep is True
    assert seen["options"].step_mode == _StepMode.Variable
    assert seen["options"].integrator == _Integrator.Trapezoidal
    assert seen["options"].enable_events is False
    assert seen["options"].max_step_retries == 12
    assert seen["options"].enable_losses is False
    assert seen["options"].formulation_mode == _FormulationMode.Direct
    assert seen["options"].direct_formulation_fallback is False
    assert seen["options"].control_mode == _ControlUpdateMode.Discrete
    assert seen["options"].control_sample_time == 5e-6
    assert seen["options"].thermal.default_rth == 2.1
    assert seen["options"].thermal.default_cth == 0.33
    assert seen["options"].thermal.policy == _ThermalCouplingPolicy.LossOnly
    assert "R1" in seen["options"].switching_energy
    assert seen["options"].switching_energy["R1"].eon == 1.2e-6
    assert seen["options"].switching_energy["R1"].eoff == 2.4e-6
    assert seen["options"].switching_energy["R1"].err == 3.6e-6
    assert "R1" in seen["options"].thermal_devices
    assert seen["options"].thermal_devices["R1"].enabled is False
    assert seen["options"].thermal_devices["R1"].rth == 4.4
    assert seen["options"].thermal_devices["R1"].cth == 0.55
    assert seen["options"].thermal_devices["R1"].temp_init == 45.0
    assert seen["options"].thermal_devices["R1"].temp_ref == 35.0
    assert seen["options"].thermal_devices["R1"].alpha == 0.007
    assert result.statistics["total_steps"] == 2.0
    assert result.statistics["status"] == "Success"
    assert result.statistics["diagnostic"] == "None"
    assert result.statistics["linear_solver_telemetry"]["total_solve_calls"] == 11.0
    assert result.statistics["backend_telemetry"]["selected_backend"] == "native"
    assert result.statistics["fallback_trace_count"] == 1
    assert result.statistics["fallback_trace"][0]["action"] == "reduce_dt"
    assert result.statistics["virtual_channel_metadata"]["T(M1)"]["domain"] == "thermal"
    assert result.statistics["virtual_channel_metadata"]["T(M1)"]["source_component"] == "M1"
    assert result.statistics["virtual_channel_metadata"]["T(M1)"]["unit"] == "degC"
    assert "T(M1)" in result.statistics["virtual_thermal_channels"]
    assert result.statistics["loss_summary"]["total_loss"] == 1.75
    assert result.statistics["loss_summary"]["device_losses"]["M1"]["device_name"] == "M1"
    assert (
        result.statistics["loss_summary"]["device_losses"]["M1"]["breakdown"]["turn_on"] == 0.3
    )
    assert result.statistics["loss_device_count"] == 1
    assert result.statistics["thermal_summary"]["enabled"] is True
    assert result.statistics["thermal_summary"]["max_temperature"] == 73.0
    assert result.statistics["electrothermal_component_count"] == 1
    assert result.statistics["component_electrothermal"][0]["component_name"] == "M1"


def test_run_thermal_fails_when_native_api_is_missing() -> None:
    class _FallbackThermalSimulator:
        def __init__(self, *args: Any) -> None:  # noqa: ANN401
            self._args = args

        def simulate(self, times: list[float], powers: list[float]) -> list[float]:
            _ = times
            return [30.0 + float(power) * 0.1 for power in powers]

    fake_module = SimpleNamespace(
        __version__="2.0.0",
        Circuit=_FakeCircuit,
        ThermalSimulator=_FallbackThermalSimulator,
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

    electrical_result = TransientResult(
        time=[0.0, 1e-6, 2e-6],
        signals={"P(R1)": [1.0, 2.0, 3.0]},
    )
    thermal_result = backend.run_thermal(
        _simple_circuit_data(),
        electrical_result,
        ThermalSettings(ambient_temperature=25.0),
    )

    assert "no compatible native thermal api" in thermal_result.error_message.lower()
    assert thermal_result.time == []
    assert thermal_result.devices == []
    assert thermal_result.is_synthetic is False
