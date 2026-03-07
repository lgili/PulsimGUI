"""Simulation service for running Pulsim simulations."""

from __future__ import annotations

import copy
import math
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QMutex, QObject, QThread, QTimer, QWaitCondition, Signal

from pulsimgui.services.backend_adapter import (
    BackendCallbacks,
    BackendInfo,
    BackendLoader,
    SimulationBackend,
)
from pulsimgui.services.backend_runtime_service import (
    BackendInstallResult,
    BackendRuntimeConfig,
    BackendRuntimeService,
)
from pulsimgui.services.backend_types import (
    ACResult as BackendACResult,
)
from pulsimgui.services.backend_types import (
    ACSettings,
    DCSettings,
)
from pulsimgui.services.backend_types import (
    DCResult as BackendDCResult,
)
from pulsimgui.services.circuit_data_builder import CircuitDataBuilder
from pulsimgui.utils.net_utils import build_node_alias_map, build_node_map

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from pulsimgui.services.settings_service import SettingsService


class SimulationState(Enum):
    """State of the simulation."""

    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    CANCELLED = auto()
    COMPLETED = auto()
    ERROR = auto()


_LEGACY_SOLVER_ALIASES = {
    "rk4": "trapezoidal",
    "rk45": "trapezoidal",
    "bdf": "bdf2",
}

_SUPPORTED_INTEGRATION_METHODS = {
    "auto",
    "trapezoidal",
    "bdf1",
    "bdf2",
    "bdf3",
    "bdf4",
    "bdf5",
    "gear",
    "trbdf2",
    "rosenbrockw",
    "sdirk2",
}

_SWITCHABLE_TARGET_TYPES = frozenset({
    "MOSFET_N",
    "MOSFET_P",
    "MOSFET",
    "IGBT",
    "SWITCH",
    "VOLTAGE_CONTROLLED_SWITCH",
    "VCSWITCH",
})

_THERMAL_SUPPORTED_COMPONENT_TYPES = frozenset({
    "RESISTOR",
    "DIODE",
    "MOSFET_N",
    "MOSFET_P",
    "MOSFET",
    "IGBT",
    "BJT_NPN",
    "BJT_PNP",
})

_NON_ELECTRICAL_COMPONENT_TYPES = frozenset({
    "PI_CONTROLLER",
    "PID_CONTROLLER",
    "MATH_BLOCK",
    "PWM_GENERATOR",
    "GAIN",
    "SUM",
    "SUBTRACTOR",
    "CONSTANT",
    "INTEGRATOR",
    "DIFFERENTIATOR",
    "LIMITER",
    "RATE_LIMITER",
    "HYSTERESIS",
    "LOOKUP_TABLE",
    "TRANSFER_FUNCTION",
    "DELAY_BLOCK",
    "SAMPLE_HOLD",
    "STATE_MACHINE",
    "VOLTAGE_PROBE",
    "VOLTAGE_PROBE_GND",
    "CURRENT_PROBE",
    "POWER_PROBE",
    "ELECTRICAL_SCOPE",
    "THERMAL_SCOPE",
    "SIGNAL_MUX",
    "SIGNAL_DEMUX",
    "GOTO_LABEL",
    "FROM_LABEL",
    "SUBCIRCUIT",
    "GROUND",
})


def normalize_integration_method(value: str | None) -> str:
    """Normalize persisted method names to supported backend identifiers."""
    raw = (value or "").strip().lower()
    if not raw:
        return "auto"
    normalized = _LEGACY_SOLVER_ALIASES.get(raw, raw)
    return normalized if normalized in _SUPPORTED_INTEGRATION_METHODS else "auto"


def normalize_step_mode(value: str | None) -> str:
    """Normalize transient step mode setting."""
    raw = (value or "").strip().lower()
    if raw in {"fixed", "variable"}:
        return raw
    return "fixed"


def normalize_thermal_network(value: str | None) -> str:
    """Normalize thermal network setting."""
    raw = (value or "").strip().lower()
    return raw if raw in {"foster", "cauer"} else "foster"


def normalize_thermal_policy(value: str | None) -> str:
    """Normalize electrothermal coupling policy setting."""
    raw = (value or "").strip().lower()
    aliases = {
        "losswithtemperaturescaling": "loss_with_temperature_scaling",
        "temperature_scaling": "loss_with_temperature_scaling",
        "loss_only": "loss_only",
        "lossonly": "loss_only",
    }
    normalized = aliases.get(raw, raw)
    if normalized not in {"loss_only", "loss_with_temperature_scaling"}:
        return "loss_with_temperature_scaling"
    return normalized


def normalize_formulation_mode(value: str | None) -> str:
    """Normalize transient formulation mode setting."""
    raw = (value or "").strip().lower()
    aliases = {
        "projected": "projected_wrapper",
        "projectedwrapper": "projected_wrapper",
        "native": "projected_wrapper",
        "directdae": "direct",
        "dae": "direct",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in {"projected_wrapper", "direct"} else "projected_wrapper"


def normalize_control_mode(value: str | None) -> str:
    """Normalize control update scheduling mode setting."""
    raw = (value or "").strip().lower()
    aliases = {
        "sampled": "discrete",
        "sample": "discrete",
        "continuous_time": "continuous",
    }
    normalized = aliases.get(raw, raw)
    return normalized if normalized in {"auto", "continuous", "discrete"} else "auto"


@dataclass
class SimulationSettings:
    """Settings for transient simulation."""

    # Time settings
    t_start: float = 0.0
    t_stop: float = 1e-3  # 1ms default
    t_step: float = 1e-6  # 1us default

    # Integration settings
    solver: str = "auto"  # auto, trapezoidal, bdf1..bdf5, gear, trbdf2, rosenbrockw, sdirk2
    step_mode: str = "fixed"  # fixed, variable
    max_step: float = 1e-6
    rel_tol: float = 1e-4
    abs_tol: float = 1e-6
    enable_events: bool = True
    max_step_retries: int = 8

    # Newton solver settings
    max_newton_iterations: int = 100
    enable_voltage_limiting: bool = False
    max_voltage_step: float = 5.0

    # DC analysis settings
    dc_strategy: str = "auto"  # auto, direct, gmin, source, pseudo
    gmin_initial: float = 1e-3
    gmin_final: float = 1e-12
    dc_source_steps: int = 10

    # Transient stability settings
    transient_robust_mode: bool = True
    transient_auto_regularize: bool = True

    # Output settings
    output_points: int = 10000
    enable_losses: bool = True

    # Thermal/loss post-processing settings
    thermal_ambient: float = 25.0
    thermal_include_switching_losses: bool = True
    thermal_include_conduction_losses: bool = True
    thermal_network: str = "foster"
    thermal_policy: str = "loss_with_temperature_scaling"
    thermal_default_rth: float = 1.0
    thermal_default_cth: float = 0.1

    # Transient formulation mode (supported by pulsim>=0.6.1)
    formulation_mode: str = "projected_wrapper"
    direct_formulation_fallback: bool = True
    control_mode: str = "auto"
    control_sample_time: float = 0.0


@dataclass
class SimulationResult:
    """Results from a simulation run."""

    time: list[float] = field(default_factory=list)
    signals: dict[str, list[float]] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if results are valid."""
        return len(self.time) > 0 and not self.error_message


@dataclass
class DCResult:
    """Results from DC operating point analysis."""

    node_voltages: dict[str, float] = field(default_factory=dict)
    branch_currents: dict[str, float] = field(default_factory=dict)
    power_dissipation: dict[str, float] = field(default_factory=dict)
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if results are valid."""
        return not self.error_message


@dataclass
class ACResult:
    """Results from AC analysis."""

    frequencies: list[float] = field(default_factory=list)
    magnitude: dict[str, list[float]] = field(default_factory=dict)
    phase: dict[str, list[float]] = field(default_factory=dict)
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if results are valid."""
        return len(self.frequencies) > 0 and not self.error_message


@dataclass
class ParameterSweepSettings:
    """Configuration for single-parameter sweeps."""

    component_id: str
    component_name: str
    parameter_name: str
    start_value: float
    end_value: float
    points: int = 5
    scale: str = "linear"
    output_signal: str = "V(out)"
    parallel_workers: int = 1
    baseline_value: float = 1.0

    def generate_values(self) -> list[float]:
        """Generate sweep points."""
        if self.points <= 1:
            return [self.start_value]

        if self.scale == "log":
            if self.start_value <= 0 or self.end_value <= 0:
                raise ValueError("Logarithmic sweeps require positive bounds")
            start = math.log10(self.start_value)
            stop = math.log10(self.end_value)
            step = (stop - start) / (self.points - 1)
            return [10 ** (start + i * step) for i in range(self.points)]

        step = (self.end_value - self.start_value) / (self.points - 1)
        return [self.start_value + i * step for i in range(self.points)]

    def compute_scale_factor(self, value: float) -> float:
        """Return amplitude scaling for placeholder simulation."""
        if abs(self.baseline_value) < 1e-30:
            return 1.0
        return value / self.baseline_value


@dataclass
class ParameterSweepRun:
    """Result of an individual sweep point."""

    order: int
    parameter_value: float
    result: SimulationResult


@dataclass
class ParameterSweepResult:
    """Aggregated sweep results."""

    settings: ParameterSweepSettings
    runs: list[ParameterSweepRun] = field(default_factory=list)
    duration: float = 0.0

    def sorted_runs(self) -> list[ParameterSweepRun]:
        """Return runs in configured order."""
        return sorted(self.runs, key=lambda run: run.order)

    def to_waveform_result(self) -> SimulationResult:
        """Build a SimulationResult aggregating sweep traces."""
        combined = SimulationResult()
        ordered = self.sorted_runs()
        if not ordered:
            return combined

        combined.time = ordered[0].result.time.copy()

        for run in ordered:
            signal = run.result.signals.get(self.settings.output_signal)
            if not signal:
                continue
            label = (
                f"{self.settings.output_signal}"
                f" [{self.settings.parameter_name}={run.parameter_value:g}]"
            )
            combined.signals[label] = signal

        combined.statistics = {
            "sweep_points": len(ordered),
            "parameter": self.settings.parameter_name,
        }
        return combined

    def xy_dataset(self) -> tuple[list[float], list[float]]:
        """Return (parameter, output) pairs for XY plotting."""
        xs: list[float] = []
        ys: list[float] = []

        for run in self.sorted_runs():
            xs.append(run.parameter_value)
            signal = run.result.signals.get(self.settings.output_signal)
            ys.append(signal[-1] if signal else 0.0)

        return xs, ys


class SimulationWorker(QThread):
    """Worker thread for running simulations via the active backend."""

    progress = Signal(float, str)  # progress (0-100), message
    data_point = Signal(float, dict)  # time, signal_values
    finished_signal = Signal(SimulationResult)
    error = Signal(str)

    def __init__(
        self,
        backend: SimulationBackend,
        circuit_data: dict | None,
        settings: SimulationSettings,
        *,
        circuit_source: Any | None = None,
        circuit_builder: Callable[[Any], dict] | None = None,
        contract_validator: Callable[[dict], str | None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self._backend = backend
        self._circuit_data = circuit_data
        self._settings = settings
        self._circuit_source = circuit_source
        self._circuit_builder = circuit_builder
        self._contract_validator = contract_validator
        self._cancelled = False
        self._paused = False
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()
        self._thread_ident: int | None = None

    def run(self) -> None:
        """Run the simulation."""
        result = SimulationResult()

        try:
            self._thread_ident = threading.get_ident()

            if self._circuit_data is None:
                if self._circuit_builder is None:
                    raise ValueError("Circuit builder is required when circuit_data is not provided.")
                self.progress.emit(-1, "Preparing circuit model...")
                self._circuit_data = self._circuit_builder(self._circuit_source)
                if not isinstance(self._circuit_data, dict):
                    raise ValueError("Circuit builder returned invalid data format.")

            if self._cancelled:
                result.error_message = "Simulation cancelled"
                self.finished_signal.emit(result)
                return

            if self._contract_validator is not None:
                contract_issue = self._contract_validator(self._circuit_data)
                if contract_issue:
                    result.error_message = contract_issue
                    self.error.emit(contract_issue)
                    self.finished_signal.emit(result)
                    return

            # Emit initial progress immediately so user sees feedback
            self.progress.emit(0, "Starting simulation...")

            callbacks = BackendCallbacks(
                progress=lambda value, message: self.progress.emit(value, message),
                data_point=lambda t, data: self.data_point.emit(t, data),
                check_cancelled=lambda: self._cancelled,
                wait_if_paused=self._wait_if_paused,
            )

            backend_result = self._backend.run_transient(
                self._circuit_data,
                self._settings,
                callbacks,
            )

            result.time = self._as_list_fast(backend_result.time)
            result.signals = {
                name: self._as_list_fast(values)
                for name, values in backend_result.signals.items()
            }
            result.statistics = (
                backend_result.statistics
                if isinstance(backend_result.statistics, dict)
                else dict(backend_result.statistics)
            )
            result.error_message = backend_result.error_message

            self._append_runtime_contract_checks(result)

            if self._cancelled and not result.error_message:
                result.error_message = "Simulation cancelled"

            if result.error_message:
                self.error.emit(result.error_message)
            self.finished_signal.emit(result)

        except Exception as e:  # pragma: no cover - defensive path
            result.error_message = str(e)
            self.error.emit(str(e))
            self.finished_signal.emit(result)
        finally:
            self._thread_ident = None

    @staticmethod
    def _as_list_fast(values: Any) -> list[Any]:
        """Return list-like data with minimal overhead.

        Backend adapters already emit Python lists in the common path.
        Reusing list instances avoids expensive large copies at simulation end.
        """
        if isinstance(values, list):
            return values
        return list(values)

    def _wait_if_paused(self) -> None:
        self._mutex.lock()
        try:
            while self._paused and not self._cancelled:
                self._pause_condition.wait(self._mutex)
        finally:
            self._mutex.unlock()

    def cancel(self) -> None:
        """Cancel the simulation."""
        self._cancelled = True
        self._paused = False
        self._pause_condition.wakeAll()
        self._notify_backend_control("request_stop")

    def pause(self) -> None:
        """Pause the simulation."""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()
        self._notify_backend_control("request_pause")

    def resume(self) -> None:
        """Resume a paused simulation."""
        self._mutex.lock()
        self._paused = False
        self._mutex.unlock()
        self._pause_condition.wakeAll()
        self._notify_backend_control("request_resume")

    @property
    def is_paused(self) -> bool:
        """Check if simulation is paused."""
        return self._paused

    def _notify_backend_control(self, method_name: str) -> None:
        run_id = self._thread_ident
        if run_id is None:
            return
        handler = getattr(self._backend, method_name, None)
        if handler is None:
            return
        try:
            handler(run_id)
        except TypeError:  # Backends that ignore run identifiers
            handler()
        except Exception:
            pass

    def _append_runtime_contract_checks(self, result: SimulationResult) -> None:
        """Attach physical-consistency checks and KPI-style diagnostics."""
        stats = result.statistics
        warnings: list[str] = []
        diagnostic_code = str(stats.get("diagnostic", "") or "").strip().lower()
        if diagnostic_code == "invalid_thermal_configuration":
            warnings.append(
                "Backend diagnostic invalid_thermal_configuration: check global and per-device thermal parameters."
            )
            if not result.error_message:
                result.error_message = (
                    "invalid_thermal_configuration: check simulation thermal defaults "
                    "and per-component thermal parameters."
                )
        execution_path = str(stats.get("execution_path", "") or "").strip().lower()
        simulator_options_failure = str(
            stats.get("simulator_options_error") or stats.get("simulator_options_exception") or ""
        ).strip()
        if simulator_options_failure and execution_path != "simulator_options":
            stats["runtime_used_compatibility_fallback"] = True
            warnings.append(
                "SimulationOptions path failed and compatibility transient fallback was used; "
                "advanced control/thermal telemetry may be degraded."
            )
        else:
            stats["runtime_used_compatibility_fallback"] = False

        if not result.time:
            stats["runtime_contract_ok"] = False
            if not warnings:
                warnings.append("No transient samples returned.")
            stats["runtime_contract_warnings"] = warnings
            return

        final_time = float(result.time[-1])
        target_time = float(getattr(self._settings, "t_stop", final_time))
        time_tol = max(1e-12, abs(target_time) * 1e-3, float(getattr(self._settings, "t_step", 0.0)) * 2.0)
        time_ok = abs(final_time - target_time) <= time_tol
        stats["runtime_time_target"] = target_time
        stats["runtime_time_final"] = final_time
        stats["runtime_time_within_tolerance"] = time_ok
        if not time_ok:
            warnings.append("Final time does not match configured tstop within tolerance.")

        components = (
            self._circuit_data.get("components", [])
            if isinstance(self._circuit_data, dict)
            else []
        )
        pwm_components = [
            comp for comp in components
            if str(comp.get("type", "")).strip().upper() == "PWM_GENERATOR"
        ]
        pi_components = [
            comp for comp in components
            if str(comp.get("type", "")).strip().upper() in {"PI_CONTROLLER", "PID_CONTROLLER"}
        ]

        missing_channels: list[str] = []
        for component in pi_components:
            name = str(component.get("name") or "").strip()
            if name and name not in result.signals:
                missing_channels.append(name)
        for component in pwm_components:
            name = str(component.get("name") or "").strip()
            duty_key = f"{name}.duty" if name else ""
            if duty_key and duty_key not in result.signals:
                missing_channels.append(duty_key)
        if missing_channels:
            warnings.append(f"Missing expected control channels: {', '.join(sorted(set(missing_channels)))}.")
        stats["runtime_missing_control_channels"] = sorted(set(missing_channels))

        duty_limit_ok = True
        for component in pwm_components:
            name = str(component.get("name") or "").strip()
            if not name:
                continue
            duty_key = f"{name}.duty"
            duty_series = result.signals.get(duty_key)
            if not duty_series:
                continue
            params = component.get("parameters", {}) if isinstance(component.get("parameters"), dict) else {}
            duty_min = float(params.get("duty_min", 0.0))
            duty_max = float(params.get("duty_max", 1.0))
            if any((value < duty_min - 1e-9) or (value > duty_max + 1e-9) for value in duty_series):
                duty_limit_ok = False
                warnings.append(f"Channel {duty_key} exceeded configured limits [{duty_min}, {duty_max}].")
        stats["runtime_pwm_duty_within_limits"] = duty_limit_ok

        duration = max(0.0, float(result.time[-1] - result.time[0]))
        stats["runtime_duration"] = duration

        loss_summary = stats.get("loss_summary") if isinstance(stats.get("loss_summary"), dict) else {}
        thermal_summary = (
            stats.get("thermal_summary") if isinstance(stats.get("thermal_summary"), dict) else {}
        )
        component_rows = (
            stats.get("component_electrothermal")
            if isinstance(stats.get("component_electrothermal"), list)
            else []
        )

        total_loss = float(loss_summary.get("total_loss", 0.0) or 0.0)
        stats["runtime_total_loss_positive"] = total_loss > 0.0 if self._settings.enable_losses else True
        if self._settings.enable_losses and total_loss <= 0.0:
            warnings.append("Loss summary reported non-positive total loss in a losses-enabled run.")

        thermal_enabled = bool(thermal_summary.get("enabled", False))
        ambient = float(thermal_summary.get("ambient", self._settings.thermal_ambient) or self._settings.thermal_ambient)
        max_temperature = float(thermal_summary.get("max_temperature", ambient) or ambient)
        thermal_ok = (not self._settings.enable_losses) or (thermal_enabled and max_temperature >= ambient)
        stats["runtime_thermal_summary_ok"] = thermal_ok
        if self._settings.enable_losses and not thermal_ok:
            warnings.append("Thermal summary is inconsistent (disabled or max_temperature < ambient).")

        non_virtual_components = [
            comp for comp in components
            if str(comp.get("type", "")).strip().upper() not in _NON_ELECTRICAL_COMPONENT_TYPES
        ]
        expected_component_count = len(non_virtual_components)
        observed_component_count = len(component_rows)
        coverage_rate = (
            float(observed_component_count) / float(expected_component_count)
            if expected_component_count > 0
            else 1.0
        )
        coverage_gap = max(0, expected_component_count - observed_component_count)
        stats["component_coverage_rate"] = coverage_rate
        stats["component_coverage_gap"] = coverage_gap
        if coverage_gap > 0:
            warnings.append(
                f"Component electrothermal coverage gap: expected {expected_component_count}, got {observed_component_count}."
            )

        total_energy = 0.0
        for row in component_rows:
            if not isinstance(row, dict):
                continue
            total_energy += float(row.get("total_energy", 0.0) or 0.0)
        expected_energy = total_loss * duration
        loss_consistency_error = (
            abs(total_energy - expected_energy) / max(abs(expected_energy), 1e-12)
            if expected_energy > 0.0
            else 0.0
        )
        stats["component_loss_summary_consistency_error"] = loss_consistency_error
        if loss_consistency_error > 5e-2:
            warnings.append("High loss consistency error between component energies and loss_summary.")

        thermal_by_name: dict[str, float] = {}
        for entry in thermal_summary.get("device_temperatures", []) if isinstance(thermal_summary.get("device_temperatures"), list) else []:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("device_name") or "").strip()
            if not name:
                continue
            thermal_by_name[name] = float(entry.get("peak_temperature", entry.get("final_temperature", ambient)) or ambient)

        max_peak_delta = 0.0
        for row in component_rows:
            if not isinstance(row, dict):
                continue
            name = str(row.get("component_name") or "").strip()
            if not name or name not in thermal_by_name:
                continue
            row_peak = float(row.get("peak_temperature", row.get("final_temperature", ambient)) or ambient)
            max_peak_delta = max(max_peak_delta, abs(row_peak - thermal_by_name[name]))
        stats["component_thermal_summary_consistency_error"] = max_peak_delta
        if max_peak_delta > 2.0:
            warnings.append("High thermal consistency error between component_electrothermal and thermal_summary.")

        runtime_ok = not warnings and not result.error_message
        stats["runtime_contract_ok"] = runtime_ok
        stats["runtime_contract_warnings"] = warnings


class ParameterSweepWorker(QThread):
    """Worker that runs multiple simulations for parameter sweeps."""

    progress = Signal(float, str)
    finished_signal = Signal(ParameterSweepResult)
    error = Signal(str)

    def __init__(
        self,
        backend: SimulationBackend,
        circuit_data: dict,
        sweep_settings: ParameterSweepSettings,
        base_settings: SimulationSettings,
        parent=None,
    ):
        super().__init__(parent)
        self._backend = backend
        self._circuit_data = circuit_data
        self._sweep_settings = sweep_settings
        self._base_settings = base_settings
        self._cancelled = False

    def run(self) -> None:
        """Execute the sweep."""
        runs: list[ParameterSweepRun] = []
        start_time = time.time()

        try:
            values = self._sweep_settings.generate_values()
            total = len(values)
            if total == 0:
                raise ValueError("No sweep points configured")

            parallel = max(1, self._sweep_settings.parallel_workers)
            if parallel > 1:
                with ThreadPoolExecutor(max_workers=parallel) as executor:
                    futures = {
                        executor.submit(self._simulate_value, idx, value): idx
                        for idx, value in enumerate(values)
                    }
                    for future in as_completed(futures):
                        if self._cancelled:
                            break
                        run = future.result()
                        runs.append(run)
                        self._emit_progress(len(runs), total)
            else:
                for idx, value in enumerate(values):
                    if self._cancelled:
                        break
                    runs.append(self._simulate_value(idx, value))
                    self._emit_progress(len(runs), total)

            if not self._cancelled:
                self._emit_progress(total, total)

            duration = time.time() - start_time
            result = ParameterSweepResult(
                settings=self._sweep_settings,
                runs=runs,
                duration=duration,
            )
            self.finished_signal.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
            result = ParameterSweepResult(settings=self._sweep_settings, runs=runs)
            self.finished_signal.emit(result)

    def cancel(self) -> None:
        """Request cancellation."""
        self._cancelled = True

    @property
    def was_cancelled(self) -> bool:
        """Return whether cancellation was requested."""
        return self._cancelled

    def _emit_progress(self, completed: int, total: int) -> None:
        if not total:
            return
        percent = (completed / total) * 100.0
        self.progress.emit(percent, f"Sweep {completed}/{total}")

    def _simulate_value(self, order: int, value: float) -> ParameterSweepRun:
        circuit_copy = copy.deepcopy(self._circuit_data)
        self._apply_parameter_value(circuit_copy, value)
        settings_copy = replace(self._base_settings)

        callbacks = BackendCallbacks(
            progress=lambda *_: None,
            data_point=lambda *_: None,
            check_cancelled=lambda: self._cancelled,
            wait_if_paused=lambda: None,
        )
        backend_result = self._backend.run_transient(circuit_copy, settings_copy, callbacks)
        sim_result = SimulationResult(
            time=list(backend_result.time),
            signals={name: list(series) for name, series in backend_result.signals.items()},
            statistics=dict(backend_result.statistics),
            error_message=backend_result.error_message,
        )
        return ParameterSweepRun(order=order, parameter_value=value, result=sim_result)

    def _apply_parameter_value(self, circuit_data: dict, value: float) -> None:
        for component in circuit_data.get("components", []):
            if component.get("id") == self._sweep_settings.component_id:
                params = component.setdefault("parameters", {})
                params[self._sweep_settings.parameter_name] = value
                return
        raise ValueError("Target component not found in circuit data")


class SimulationService(QObject):
    """Service for managing simulations."""

    _READY_STATUSES = {"available", "detected"}

    # Signals
    state_changed = Signal(SimulationState)
    progress = Signal(float, str)
    data_point = Signal(float, dict)
    simulation_finished = Signal(SimulationResult)
    dc_finished = Signal(DCResult)
    ac_finished = Signal(ACResult)
    parameter_sweep_finished = Signal(ParameterSweepResult)
    error = Signal(str)
    backend_changed = Signal(BackendInfo)

    def __init__(self, settings_service: SettingsService | None = None, parent=None):
        super().__init__(parent)

        self._state = SimulationState.IDLE
        self._worker: SimulationWorker | None = None
        self._sweep_worker: ParameterSweepWorker | None = None
        self._settings = SimulationSettings()
        self._last_result: SimulationResult | None = None
        self._last_convergence_info = None  # Store last DC convergence info for diagnostics
        self._settings_service = settings_service
        self._runtime_service = BackendRuntimeService()
        self._circuit_data_builder = CircuitDataBuilder()
        self._runtime_config = BackendRuntimeConfig()
        self._runtime_issue: str | None = None
        preferred_backend = None
        if settings_service is not None:
            preferred_backend = settings_service.get_backend_preference()

            # Load persisted simulation settings
            sim_settings = settings_service.get_simulation_settings()
            self._settings.t_stop = sim_settings.get("t_stop", self._settings.t_stop)
            self._settings.t_step = sim_settings.get("t_step", self._settings.t_step)
            self._settings.solver = normalize_integration_method(
                sim_settings.get("solver", self._settings.solver)
            )
            self._settings.step_mode = normalize_step_mode(
                sim_settings.get("step_mode", self._settings.step_mode)
            )
            self._settings.max_step = sim_settings.get("max_step", self._settings.max_step)
            self._settings.rel_tol = sim_settings.get("rel_tol", self._settings.rel_tol)
            self._settings.abs_tol = sim_settings.get("abs_tol", self._settings.abs_tol)
            self._settings.output_points = sim_settings.get("output_points", self._settings.output_points)
            self._settings.enable_events = bool(
                sim_settings.get("enable_events", self._settings.enable_events)
            )
            self._settings.max_step_retries = int(
                sim_settings.get("max_step_retries", self._settings.max_step_retries)
            )
            self._settings.enable_losses = bool(
                sim_settings.get("enable_losses", self._settings.enable_losses)
            )

            # Load persisted solver settings
            solver_settings = settings_service.get_solver_settings()
            self._settings.max_newton_iterations = solver_settings.get("max_newton_iterations", self._settings.max_newton_iterations)
            self._settings.enable_voltage_limiting = solver_settings.get(
                "enable_voltage_limiting",
                self._settings.enable_voltage_limiting,
            )
            self._settings.max_voltage_step = solver_settings.get("max_voltage_step", self._settings.max_voltage_step)
            self._settings.dc_strategy = solver_settings.get("dc_strategy", self._settings.dc_strategy)
            self._settings.gmin_initial = solver_settings.get("gmin_initial", self._settings.gmin_initial)
            self._settings.gmin_final = solver_settings.get("gmin_final", self._settings.gmin_final)
            self._settings.dc_source_steps = solver_settings.get("dc_source_steps", self._settings.dc_source_steps)
            self._settings.transient_robust_mode = solver_settings.get(
                "transient_robust_mode",
                self._settings.transient_robust_mode,
            )
            self._settings.transient_auto_regularize = solver_settings.get(
                "transient_auto_regularize",
                self._settings.transient_auto_regularize,
            )
            self._settings.thermal_ambient = float(
                solver_settings.get("thermal_ambient", self._settings.thermal_ambient)
            )
            self._settings.thermal_include_switching_losses = bool(
                solver_settings.get(
                    "thermal_include_switching_losses",
                    self._settings.thermal_include_switching_losses,
                )
            )
            self._settings.thermal_include_conduction_losses = bool(
                solver_settings.get(
                    "thermal_include_conduction_losses",
                    self._settings.thermal_include_conduction_losses,
                )
            )
            self._settings.thermal_network = str(
                normalize_thermal_network(
                    solver_settings.get("thermal_network", self._settings.thermal_network)
                )
            )
            self._settings.thermal_policy = str(
                normalize_thermal_policy(
                    solver_settings.get("thermal_policy", self._settings.thermal_policy)
                )
            )
            self._settings.thermal_default_rth = max(
                0.0,
                float(
                    solver_settings.get(
                        "thermal_default_rth",
                        self._settings.thermal_default_rth,
                    )
                ),
            )
            self._settings.thermal_default_cth = max(
                0.0,
                float(
                    solver_settings.get(
                        "thermal_default_cth",
                        self._settings.thermal_default_cth,
                    )
                ),
            )
            self._settings.formulation_mode = str(
                normalize_formulation_mode(
                    solver_settings.get("formulation_mode", self._settings.formulation_mode)
                )
            )
            self._settings.direct_formulation_fallback = bool(
                solver_settings.get(
                    "direct_formulation_fallback",
                    self._settings.direct_formulation_fallback,
                )
            )
            self._settings.control_mode = str(
                normalize_control_mode(
                    solver_settings.get("control_mode", self._settings.control_mode)
                )
            )
            self._settings.control_sample_time = max(
                0.0,
                float(
                    solver_settings.get(
                        "control_sample_time",
                        self._settings.control_sample_time,
                    )
                ),
            )

            # Load backend runtime settings
            runtime_settings = settings_service.get_backend_runtime_settings()
            self._runtime_config = BackendRuntimeConfig.from_dict(runtime_settings)

        if self._runtime_config.auto_sync:
            sync_result = self._runtime_service.ensure_target_version(self._runtime_config, force=False)
            if sync_result.success:
                self._runtime_issue = None
                if sync_result.changed:
                    self._runtime_service.invalidate_backend_import_cache()
            else:
                self._runtime_issue = sync_result.message

        self._backend_loader = BackendLoader(preferred_backend_id=preferred_backend)
        self._backend = self._backend_loader.backend

    @property
    def state(self) -> SimulationState:
        """Get current simulation state."""
        return self._state

    @property
    def settings(self) -> SimulationSettings:
        """Get simulation settings."""
        return self._settings

    @settings.setter
    def settings(self, value: SimulationSettings) -> None:
        """Set simulation settings."""
        self._settings = value
        self._settings.solver = normalize_integration_method(self._settings.solver)
        self._settings.step_mode = normalize_step_mode(self._settings.step_mode)
        self._settings.thermal_network = normalize_thermal_network(self._settings.thermal_network)
        self._settings.thermal_policy = normalize_thermal_policy(self._settings.thermal_policy)
        self._settings.thermal_default_rth = max(0.0, float(self._settings.thermal_default_rth))
        self._settings.thermal_default_cth = max(0.0, float(self._settings.thermal_default_cth))
        self._settings.formulation_mode = normalize_formulation_mode(
            self._settings.formulation_mode
        )
        self._settings.control_mode = normalize_control_mode(self._settings.control_mode)
        self._settings.control_sample_time = max(0.0, float(self._settings.control_sample_time))
        self._circuit_data_builder.clear()
        self._persist_simulation_settings()

    @property
    def last_result(self) -> SimulationResult | None:
        """Get the last simulation result."""
        return self._last_result

    @property
    def is_running(self) -> bool:
        """Check if simulation is currently running."""
        return self._state in (SimulationState.RUNNING, SimulationState.PAUSED)

    @property
    def backend_info(self) -> BackendInfo:
        """Return metadata about the active simulation backend."""
        return self._backend.info

    @property
    def backend(self):
        """Return the active simulation backend for direct access."""
        return self._backend

    @property
    def backend_runtime_config(self) -> BackendRuntimeConfig:
        """Return backend runtime provisioning settings."""
        return self._runtime_config

    @property
    def last_convergence_info(self):
        """Return the last DC/transient convergence info for diagnostics."""
        return self._last_convergence_info

    def has_capability(self, name: str) -> bool:
        """Check if the backend supports a specific capability.

        Args:
            name: Capability name (e.g., "dc", "ac", "thermal", "transient")

        Returns:
            True if the capability is supported.
        """
        return self._backend.has_capability(name)

    def apply_project_simulation_settings(self, project: Any, *, persist: bool = False) -> None:
        """Mirror ``project.simulation_settings`` into runtime settings."""
        project_settings = getattr(project, "simulation_settings", None)
        if project_settings is None:
            return

        runtime_settings = self._settings
        runtime_settings.t_start = float(getattr(project_settings, "tstart", runtime_settings.t_start))
        runtime_settings.t_stop = float(getattr(project_settings, "tstop", runtime_settings.t_stop))
        runtime_settings.t_step = float(getattr(project_settings, "dt", runtime_settings.t_step))
        runtime_settings.max_step = float(
            getattr(project_settings, "max_step", runtime_settings.max_step)
        )
        runtime_settings.abs_tol = max(
            float(getattr(project_settings, "abstol", runtime_settings.abs_tol)),
            1e-10,
        )
        runtime_settings.rel_tol = float(getattr(project_settings, "reltol", runtime_settings.rel_tol))
        runtime_settings.solver = normalize_integration_method(
            getattr(project_settings, "solver", runtime_settings.solver)
        )
        runtime_settings.step_mode = normalize_step_mode(
            getattr(project_settings, "step_mode", runtime_settings.step_mode)
        )
        runtime_settings.output_points = int(
            getattr(project_settings, "output_points", runtime_settings.output_points)
        )
        runtime_settings.enable_events = bool(
            getattr(project_settings, "enable_events", runtime_settings.enable_events)
        )
        runtime_settings.max_step_retries = int(
            getattr(project_settings, "max_step_retries", runtime_settings.max_step_retries)
        )
        runtime_settings.max_newton_iterations = int(
            getattr(project_settings, "max_iterations", runtime_settings.max_newton_iterations)
        )
        runtime_settings.enable_voltage_limiting = bool(
            getattr(project_settings, "enable_voltage_limiting", runtime_settings.enable_voltage_limiting)
        )
        runtime_settings.max_voltage_step = float(
            getattr(project_settings, "max_voltage_step", runtime_settings.max_voltage_step)
        )
        runtime_settings.dc_strategy = str(
            getattr(project_settings, "dc_strategy", runtime_settings.dc_strategy)
        )
        runtime_settings.gmin_initial = float(
            getattr(project_settings, "gmin_initial", runtime_settings.gmin_initial)
        )
        runtime_settings.gmin_final = float(
            getattr(project_settings, "gmin_final", runtime_settings.gmin_final)
        )
        runtime_settings.dc_source_steps = int(
            getattr(project_settings, "dc_source_steps", runtime_settings.dc_source_steps)
        )
        runtime_settings.transient_robust_mode = bool(
            getattr(project_settings, "transient_robust_mode", runtime_settings.transient_robust_mode)
        )
        runtime_settings.transient_auto_regularize = bool(
            getattr(project_settings, "transient_auto_regularize", runtime_settings.transient_auto_regularize)
        )
        runtime_settings.enable_losses = bool(
            getattr(project_settings, "enable_losses", runtime_settings.enable_losses)
        )
        runtime_settings.thermal_ambient = float(
            getattr(project_settings, "thermal_ambient", runtime_settings.thermal_ambient)
        )
        runtime_settings.thermal_include_switching_losses = bool(
            getattr(
                project_settings,
                "thermal_include_switching_losses",
                runtime_settings.thermal_include_switching_losses,
            )
        )
        runtime_settings.thermal_include_conduction_losses = bool(
            getattr(
                project_settings,
                "thermal_include_conduction_losses",
                runtime_settings.thermal_include_conduction_losses,
            )
        )
        runtime_settings.thermal_network = normalize_thermal_network(
            str(
                getattr(project_settings, "thermal_network", runtime_settings.thermal_network)
                or runtime_settings.thermal_network
            )
        )
        runtime_settings.thermal_policy = normalize_thermal_policy(
            str(
                getattr(project_settings, "thermal_policy", runtime_settings.thermal_policy)
                or runtime_settings.thermal_policy
            )
        )
        runtime_settings.thermal_default_rth = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "thermal_default_rth",
                    runtime_settings.thermal_default_rth,
                )
            ),
        )
        runtime_settings.thermal_default_cth = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "thermal_default_cth",
                    runtime_settings.thermal_default_cth,
                )
            ),
        )
        runtime_settings.formulation_mode = normalize_formulation_mode(
            getattr(project_settings, "formulation_mode", runtime_settings.formulation_mode)
        )
        runtime_settings.direct_formulation_fallback = bool(
            getattr(
                project_settings,
                "direct_formulation_fallback",
                runtime_settings.direct_formulation_fallback,
            )
        )
        runtime_settings.control_mode = normalize_control_mode(
            getattr(project_settings, "control_mode", runtime_settings.control_mode)
        )
        runtime_settings.control_sample_time = max(
            0.0,
            float(
                getattr(
                    project_settings,
                    "control_sample_time",
                    runtime_settings.control_sample_time,
                )
            ),
        )
        self._circuit_data_builder.clear()
        if persist:
            self._persist_simulation_settings()

    @property
    def available_backends(self) -> list[BackendInfo]:
        """Available backend options discovered at runtime."""
        return self._backend_loader.available_backends

    @property
    def is_backend_ready(self) -> bool:
        """Return True when a real simulation backend is available."""
        info = self._backend.info
        status = (info.status or "").lower()
        return info.identifier != "placeholder" and status in self._READY_STATUSES

    @property
    def backend_issue_message(self) -> str | None:
        """Human-friendly description when the backend cannot be used."""
        if self.is_backend_ready:
            return None

        if self._runtime_issue:
            return self._runtime_issue

        info = self._backend.info
        detail = (info.message or "").strip()
        if detail:
            return detail
        if info.identifier == "placeholder":
            return "No simulation backend detected. Install Pulsim to enable simulations."
        status = info.status or "unavailable"
        return f"Backend '{info.name}' is not available (status: {status})."

    def set_backend_preference(self, identifier: str) -> BackendInfo:
        """Switch to the requested backend if possible."""
        if self.is_running:
            raise RuntimeError("Cannot change backend while a simulation is running")
        info = self._backend_loader.activate(identifier)
        self._backend = self._backend_loader.backend
        if self._settings_service is not None:
            self._settings_service.set_backend_preference(identifier)
        self.backend_changed.emit(info)
        return info

    def update_backend_runtime_config(self, config: BackendRuntimeConfig) -> None:
        """Persist and apply backend runtime configuration."""
        self._runtime_config = config
        if self._settings_service is not None:
            self._settings_service.set_backend_runtime_settings(config.to_dict())

    def install_backend_runtime(
        self,
        config: BackendRuntimeConfig | None = None,
        *,
        force: bool = True,
    ) -> BackendInstallResult:
        """Install or synchronize backend runtime according to configuration."""
        if self.is_running:
            return BackendInstallResult(
                success=False,
                message="Cannot install backend while a simulation is running.",
            )

        effective_config = config or self._runtime_config
        if config is not None:
            self.update_backend_runtime_config(config)

        result = self._runtime_service.ensure_target_version(effective_config, force=force)
        if not result.success:
            self._runtime_issue = result.message
            return result

        self._runtime_issue = None
        if result.changed:
            self._runtime_service.invalidate_backend_import_cache()

        self._reload_backend_loader(emit_signal=True)
        return result

    def _reload_backend_loader(self, *, emit_signal: bool) -> None:
        preferred_backend = None
        if self._settings_service is not None:
            preferred_backend = self._settings_service.get_backend_preference()
        elif self._backend_loader.active_backend_id:
            preferred_backend = self._backend_loader.active_backend_id

        self._backend_loader = BackendLoader(preferred_backend_id=preferred_backend)
        self._backend = self._backend_loader.backend
        if emit_signal:
            self.backend_changed.emit(self._backend.info)

    def _persist_simulation_settings(self) -> None:
        """Persist simulation and solver settings when available."""
        if self._settings_service is None:
            return
        self._settings_service.set_simulation_settings(
            {
                "t_stop": self._settings.t_stop,
                "t_step": self._settings.t_step,
                "solver": normalize_integration_method(self._settings.solver),
                "step_mode": normalize_step_mode(self._settings.step_mode),
                "max_step": self._settings.max_step,
                "rel_tol": self._settings.rel_tol,
                "abs_tol": self._settings.abs_tol,
                "output_points": self._settings.output_points,
                "enable_events": self._settings.enable_events,
                "max_step_retries": self._settings.max_step_retries,
                "enable_losses": self._settings.enable_losses,
            }
        )
        self._settings_service.set_solver_settings(
            {
                "max_newton_iterations": self._settings.max_newton_iterations,
                "enable_voltage_limiting": self._settings.enable_voltage_limiting,
                "max_voltage_step": self._settings.max_voltage_step,
                "dc_strategy": self._settings.dc_strategy,
                "gmin_initial": self._settings.gmin_initial,
                "gmin_final": self._settings.gmin_final,
                "dc_source_steps": self._settings.dc_source_steps,
                "transient_robust_mode": self._settings.transient_robust_mode,
                "transient_auto_regularize": self._settings.transient_auto_regularize,
                "thermal_ambient": self._settings.thermal_ambient,
                "thermal_include_switching_losses": self._settings.thermal_include_switching_losses,
                "thermal_include_conduction_losses": self._settings.thermal_include_conduction_losses,
                "thermal_network": normalize_thermal_network(self._settings.thermal_network),
                "thermal_policy": normalize_thermal_policy(self._settings.thermal_policy),
                "thermal_default_rth": max(0.0, float(self._settings.thermal_default_rth)),
                "thermal_default_cth": max(0.0, float(self._settings.thermal_default_cth)),
                "formulation_mode": normalize_formulation_mode(self._settings.formulation_mode),
                "direct_formulation_fallback": bool(
                    self._settings.direct_formulation_fallback
                ),
                "control_mode": normalize_control_mode(self._settings.control_mode),
                "control_sample_time": max(0.0, float(self._settings.control_sample_time)),
            }
        )

    def _ensure_backend_ready(self) -> bool:
        """Emit a user-facing error if no backend is currently usable."""
        if self.is_backend_ready:
            return True
        issue = self.backend_issue_message or "Simulation backend unavailable."
        self.error.emit(f"Simulation backend unavailable: {issue}")
        return False

    @staticmethod
    def _normalize_component_type(raw_value: Any) -> str:
        raw = str(raw_value or "").strip().upper().replace("-", "_")
        aliases = {
            "M": "MOSFET",
            "NMOS": "MOSFET_N",
            "PMOS": "MOSFET_P",
            "Q": "IGBT",
            "BJTNPN": "BJT_NPN",
            "BJTPNP": "BJT_PNP",
            "VCSWITCH": "VOLTAGE_CONTROLLED_SWITCH",
            "S": "SWITCH",
        }
        return aliases.get(raw, raw)

    @staticmethod
    def _to_finite_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(parsed):
            return None
        return parsed

    @staticmethod
    def _to_finite_float_sequence(value: Any) -> list[float]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            tokens = [part.strip() for part in text.replace(";", ",").split(",")]
            out: list[float] = []
            for token in tokens:
                if not token:
                    continue
                parsed = SimulationService._to_finite_float(token)
                if parsed is None:
                    return []
                out.append(parsed)
            return out
        if isinstance(value, (list, tuple)):
            out: list[float] = []
            for item in value:
                parsed = SimulationService._to_finite_float(item)
                if parsed is None:
                    return []
                out.append(parsed)
            return out
        return []

    @staticmethod
    def _normalize_component_thermal_network(
        raw_value: Any,
        *,
        stage_mode_requested: bool = False,
    ) -> str | None:
        raw = str(raw_value or "").strip().lower()
        aliases = {
            "single": "single_rc",
            "single-rc": "single_rc",
            "singlerc": "single_rc",
            "rc": "single_rc",
        }
        normalized = aliases.get(raw, raw)
        if not normalized:
            return "foster" if stage_mode_requested else "single_rc"
        if normalized in {"single_rc", "foster", "cauer"}:
            return normalized
        return None

    @staticmethod
    def _strictly_increasing(values: list[float]) -> bool:
        return all(values[index] > values[index - 1] for index in range(1, len(values)))

    @staticmethod
    def _first_value_from_maps(
        primary: dict[str, Any],
        secondary: dict[str, Any],
        keys: tuple[str, ...],
    ) -> tuple[bool, Any]:
        for key in keys:
            if key in primary:
                return True, primary.get(key)
            if key in secondary:
                return True, secondary.get(key)
        return False, None

    @staticmethod
    def _component_thermal_payload(component: dict[str, Any], parameters: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        component_thermal = component.get("thermal")
        if isinstance(component_thermal, dict):
            if "enabled" in component_thermal:
                payload["thermal_enabled"] = component_thermal.get("enabled")
            for key in (
                "network",
                "rth",
                "cth",
                "rth_stages",
                "cth_stages",
                "temp_init",
                "temp_ref",
                "alpha",
                "shared_sink_id",
                "shared_sink_rth",
                "shared_sink_cth",
            ):
                if key in component_thermal:
                    payload[f"thermal_{key}"] = component_thermal.get(key)

        nested_thermal = parameters.get("thermal")
        if isinstance(nested_thermal, dict):
            if "enabled" in nested_thermal and "thermal_enabled" not in payload:
                payload["thermal_enabled"] = nested_thermal.get("enabled")
            for key in (
                "network",
                "rth",
                "cth",
                "rth_stages",
                "cth_stages",
                "temp_init",
                "temp_ref",
                "alpha",
                "shared_sink_id",
                "shared_sink_rth",
                "shared_sink_cth",
            ):
                thermal_key = f"thermal_{key}"
                if key in nested_thermal and thermal_key not in payload:
                    payload[thermal_key] = nested_thermal.get(key)

        for key in (
            "thermal_enabled",
            "enable_thermal_port",
            "thermal_network",
            "thermal_rth",
            "thermal_cth",
            "thermal_rth_stages",
            "thermal_cth_stages",
            "thermal_temp_init",
            "thermal_temp_ref",
            "thermal_alpha",
            "thermal_shared_sink_id",
            "thermal_shared_sink_rth",
            "thermal_shared_sink_cth",
            "network",
            "rth",
            "cth",
            "rth_stages",
            "cth_stages",
            "temp_init",
            "temp_ref",
            "alpha",
            "shared_sink_id",
            "shared_sink_rth",
            "shared_sink_cth",
        ):
            if key in parameters:
                payload[key] = parameters.get(key)
        return payload

    @staticmethod
    def _component_thermal_enabled(thermal_payload: dict[str, Any]) -> bool:
        return bool(
            thermal_payload.get("thermal_enabled", False)
            or thermal_payload.get("enable_thermal_port", False)
        )

    def _prevalidate_runtime_contract(self, circuit_data: dict[str, Any]) -> str | None:
        """Validate control and electrothermal constraints before backend execution."""
        control_mode = normalize_control_mode(self._settings.control_mode)
        sample_time = float(self._settings.control_sample_time)
        if control_mode == "discrete" and sample_time <= 0.0:
            return (
                "PULSIM_YAML_E_CONTROL_SAMPLE_TIME_REQUIRED: "
                "control.mode=discrete requires control.sample_time > 0."
            )

        components = circuit_data.get("components", []) if isinstance(circuit_data, dict) else []
        by_name: dict[str, str] = {}
        thermal_enabled_components = 0
        shared_sink_defs: dict[str, tuple[float, float]] = {}
        simulation_cfg = circuit_data.get("simulation", {}) if isinstance(circuit_data, dict) else {}
        thermal_cfg = simulation_cfg.get("thermal", {}) if isinstance(simulation_cfg, dict) else {}

        for component_index, component in enumerate(components):
            if component_index and component_index % 128 == 0:
                time.sleep(0)
            comp_type = self._normalize_component_type(component.get("type", ""))
            comp_name = str(component.get("name") or component.get("id") or "").strip()
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            if comp_name:
                by_name[comp_name] = comp_type

            if comp_type != "PWM_GENERATOR":
                continue
            target = str(params.get("target_component") or "").strip()
            if not target:
                continue
            target_type = by_name.get(target)
            if target_type is None:
                return (
                    "PULSIM_YAML_E_CONTROL_TARGET_INVALID: "
                    f"PWM target_component '{target}' was not found."
                )
            if target_type not in _SWITCHABLE_TARGET_TYPES:
                return (
                    "PULSIM_YAML_E_CONTROL_TARGET_INVALID: "
                    f"target_component '{target}' must be switchable (mosfet/igbt/switch/vcswitch)."
                )

        for component_index, component in enumerate(components):
            if component_index and component_index % 128 == 0:
                time.sleep(0)
            comp_type = self._normalize_component_type(component.get("type", ""))
            comp_name = str(component.get("name") or component.get("id") or comp_type).strip()
            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}

            component_loss = component.get("loss")
            if not isinstance(component_loss, dict):
                component_loss = {}
            nested_loss = params.get("loss")
            if not isinstance(nested_loss, dict):
                nested_loss = {}
            loss_payload: dict[str, Any] = {}
            loss_payload.update(component_loss)
            loss_payload.update(nested_loss)
            loss_model_raw_found, loss_model_raw = self._first_value_from_maps(
                loss_payload,
                params,
                ("model", "switching_loss_model"),
            )
            loss_model = str(loss_model_raw or "").strip().lower()
            if not loss_model:
                loss_model = "scalar"
            if loss_model not in {"scalar", "datasheet"}:
                return (
                    "PULSIM_YAML_E_LOSS_MODEL_INVALID: "
                    f"component '{comp_name}' has unsupported loss.model '{loss_model}'."
                )

            if loss_model == "datasheet":
                axes = loss_payload.get("axes")
                axes = axes if isinstance(axes, dict) else {}
                current_raw = axes.get("current")
                voltage_raw = axes.get("voltage")
                temperature_raw = axes.get("temperature")
                if current_raw is None:
                    current_raw = params.get("switching_loss_axes_current", params.get("switching_loss_axis_current"))
                if voltage_raw is None:
                    voltage_raw = params.get("switching_loss_axes_voltage", params.get("switching_loss_axis_voltage"))
                if temperature_raw is None:
                    temperature_raw = params.get(
                        "switching_loss_axes_temperature",
                        params.get("switching_loss_axis_temperature"),
                    )

                current_axis = self._to_finite_float_sequence(current_raw)
                voltage_axis = self._to_finite_float_sequence(voltage_raw)
                temperature_axis = self._to_finite_float_sequence(temperature_raw)
                if (
                    not current_axis
                    or not voltage_axis
                    or not temperature_axis
                    or not self._strictly_increasing(current_axis)
                    or not self._strictly_increasing(voltage_axis)
                    or not self._strictly_increasing(temperature_axis)
                ):
                    return (
                        "PULSIM_YAML_E_LOSS_DIMENSION_INVALID: "
                        f"component '{comp_name}' datasheet loss requires finite strictly increasing axes."
                    )

                expected_size = len(current_axis) * len(voltage_axis) * len(temperature_axis)
                eon_raw_found, eon_raw = self._first_value_from_maps(
                    loss_payload,
                    params,
                    ("eon", "switching_loss_eon_table"),
                )
                eoff_raw_found, eoff_raw = self._first_value_from_maps(
                    loss_payload,
                    params,
                    ("eoff", "switching_loss_eoff_table"),
                )
                _, err_raw = self._first_value_from_maps(
                    loss_payload,
                    params,
                    ("err", "switching_loss_err_table"),
                )
                eon_table = self._to_finite_float_sequence(eon_raw)
                eoff_table = self._to_finite_float_sequence(eoff_raw)
                err_table = self._to_finite_float_sequence(err_raw)
                if not eon_raw_found or not eoff_raw_found:
                    return (
                        "PULSIM_YAML_E_LOSS_DIMENSION_INVALID: "
                        f"component '{comp_name}' datasheet loss requires eon and eoff tables."
                    )
                if len(eon_table) != expected_size or len(eoff_table) != expected_size:
                    return (
                        "PULSIM_YAML_E_LOSS_DIMENSION_INVALID: "
                        f"component '{comp_name}' datasheet loss tables must match axes size."
                    )
                if err_table and len(err_table) != expected_size:
                    return (
                        "PULSIM_YAML_E_LOSS_DIMENSION_INVALID: "
                        f"component '{comp_name}' datasheet err table must match axes size."
                    )
                if any(value < 0.0 for value in eon_table + eoff_table + err_table):
                    return (
                        "PULSIM_YAML_E_LOSS_RANGE_INVALID: "
                        f"component '{comp_name}' datasheet loss entries must be >= 0."
                    )
            elif loss_model_raw_found or any(
                key in params
                for key in (
                    "switching_eon_j",
                    "switching_eoff_j",
                    "switching_err_j",
                    "switching_eon",
                    "switching_eoff",
                    "switching_err",
                )
            ):
                for key_aliases, field_name in (
                    (("switching_eon_j", "switching_eon", "e_on", "eon"), "eon"),
                    (("switching_eoff_j", "switching_eoff", "e_off", "eoff"), "eoff"),
                    (("switching_err_j", "switching_err", "e_rr", "err"), "err"),
                ):
                    found, raw_value = self._first_value_from_maps(
                        loss_payload,
                        params,
                        key_aliases,
                    )
                    if not found:
                        continue
                    parsed = self._to_finite_float(raw_value)
                    if parsed is None or parsed < 0.0:
                        return (
                            "PULSIM_YAML_E_LOSS_RANGE_INVALID: "
                            f"component '{comp_name}' loss.{field_name} must be finite and >= 0."
                        )

            thermal_payload = self._component_thermal_payload(component, params)
            if not self._component_thermal_enabled(thermal_payload):
                continue

            thermal_enabled_components += 1
            if comp_type not in _THERMAL_SUPPORTED_COMPONENT_TYPES:
                return (
                    "PULSIM_YAML_E_THERMAL_UNSUPPORTED_COMPONENT: "
                    f"component '{comp_name}' ({comp_type}) does not support thermal enablement."
                )
            rth_stages = self._to_finite_float_sequence(
                thermal_payload.get("thermal_rth_stages", thermal_payload.get("rth_stages"))
            )
            cth_stages = self._to_finite_float_sequence(
                thermal_payload.get("thermal_cth_stages", thermal_payload.get("cth_stages"))
            )
            stage_mode_requested = bool(rth_stages or cth_stages)
            network = self._normalize_component_thermal_network(
                thermal_payload.get("thermal_network", thermal_payload.get("network")),
                stage_mode_requested=stage_mode_requested,
            )
            if network is None:
                return (
                    "PULSIM_YAML_E_THERMAL_NETWORK_INVALID: "
                    f"component '{comp_name}' has unsupported thermal.network."
                )

            rth = self._to_finite_float(thermal_payload.get("thermal_rth", thermal_payload.get("rth")))
            cth = self._to_finite_float(thermal_payload.get("thermal_cth", thermal_payload.get("cth")))
            temp_init = self._to_finite_float(
                thermal_payload.get(
                    "thermal_temp_init",
                    thermal_payload.get("temp_init", self._settings.thermal_ambient),
                )
            )
            temp_ref = self._to_finite_float(
                thermal_payload.get(
                    "thermal_temp_ref",
                    thermal_payload.get("temp_ref", self._settings.thermal_ambient),
                )
            )
            alpha = self._to_finite_float(
                thermal_payload.get("thermal_alpha", thermal_payload.get("alpha", 0.004))
            )

            if temp_init is None or temp_ref is None or alpha is None:
                return (
                    "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                    f"component '{comp_name}' requires finite temp_init/temp_ref/alpha."
                )

            if network == "single_rc":
                has_rth = "thermal_rth" in thermal_payload or "rth" in thermal_payload
                has_cth = "thermal_cth" in thermal_payload or "cth" in thermal_payload
                if not has_rth or not has_cth:
                    return (
                        "PULSIM_YAML_E_THERMAL_MISSING_REQUIRED: "
                        f"component '{comp_name}' thermal requires rth and cth."
                    )
                if rth is None or cth is None or rth <= 0.0 or cth < 0.0:
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' requires rth>0 and cth>=0 for single_rc."
                    )
                if rth_stages or cth_stages:
                    return (
                        "PULSIM_YAML_E_THERMAL_NETWORK_INVALID: "
                        f"component '{comp_name}' single_rc cannot use rth_stages/cth_stages."
                    )
            else:
                if not rth_stages or not cth_stages:
                    return (
                        "PULSIM_YAML_E_THERMAL_MISSING_REQUIRED: "
                        f"component '{comp_name}' staged thermal requires rth_stages and cth_stages."
                    )
                if len(rth_stages) != len(cth_stages):
                    return (
                        "PULSIM_YAML_E_THERMAL_DIMENSION_INVALID: "
                        f"component '{comp_name}' staged thermal requires matching rth_stages/cth_stages."
                    )
                if any(value <= 0.0 for value in rth_stages):
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' requires every rth_stages[i] > 0."
                    )
                if any(value < 0.0 for value in cth_stages):
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' requires every cth_stages[i] >= 0."
                    )
                if rth is not None and rth <= 0.0:
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' optional rth must be > 0."
                    )
                if cth is not None and cth < 0.0:
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' optional cth must be >= 0."
                    )

            shared_sink_id = str(
                thermal_payload.get(
                    "thermal_shared_sink_id",
                    thermal_payload.get("shared_sink_id", ""),
                )
                or ""
            ).strip()
            shared_sink_rth = self._to_finite_float(
                thermal_payload.get(
                    "thermal_shared_sink_rth",
                    thermal_payload.get("shared_sink_rth"),
                )
            )
            shared_sink_cth = self._to_finite_float(
                thermal_payload.get(
                    "thermal_shared_sink_cth",
                    thermal_payload.get("shared_sink_cth"),
                )
            )
            # Thermal-capable components carry shared-sink defaults (0.0) in GUI
            # parameters. Treat only non-zero values as explicit shared-sink usage
            # when no shared_sink_id is provided.
            has_shared_sink_rth = (
                shared_sink_rth is not None and abs(shared_sink_rth) > 1e-15
            )
            has_shared_sink_cth = (
                shared_sink_cth is not None and abs(shared_sink_cth) > 1e-15
            )

            if shared_sink_id:
                if (
                    shared_sink_rth is None
                    or shared_sink_rth <= 0.0
                    or shared_sink_cth is None
                    or shared_sink_cth < 0.0
                ):
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' shared sink requires shared_sink_rth>0 and shared_sink_cth>=0."
                    )
                previous = shared_sink_defs.get(shared_sink_id)
                if previous is None:
                    shared_sink_defs[shared_sink_id] = (shared_sink_rth, shared_sink_cth)
                elif (
                    abs(previous[0] - shared_sink_rth) > 1e-12
                    or abs(previous[1] - shared_sink_cth) > 1e-12
                ):
                    return (
                        "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                        f"component '{comp_name}' shared sink '{shared_sink_id}' must reuse identical shared_sink_rth/shared_sink_cth."
                    )
            elif has_shared_sink_rth or has_shared_sink_cth:
                return (
                    "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                    f"component '{comp_name}' shared_sink_rth/shared_sink_cth require shared_sink_id."
                )

        if thermal_enabled_components > 0:
            thermal_enabled = bool(
                thermal_cfg.get("enabled", bool(self._settings.enable_losses))
            ) if isinstance(thermal_cfg, dict) else bool(self._settings.enable_losses)
            if not thermal_enabled:
                return (
                    "PULSIM_YAML_E_THERMAL_MISSING_REQUIRED: "
                    "component thermal requires simulation.thermal.enabled=true."
                )
            if not bool(self._settings.enable_losses):
                return (
                    "PULSIM_YAML_E_THERMAL_MISSING_REQUIRED: "
                    "thermal-enabled components require simulation.enable_losses=true."
                )
            ambient = self._to_finite_float(self._settings.thermal_ambient)
            default_rth = self._to_finite_float(self._settings.thermal_default_rth)
            default_cth = self._to_finite_float(self._settings.thermal_default_cth)
            if (
                ambient is None
                or default_rth is None
                or default_cth is None
                or default_rth <= 0.0
                or default_cth < 0.0
            ):
                return (
                    "PULSIM_YAML_E_THERMAL_RANGE_INVALID: "
                    "global thermal config requires finite ambient, default_rth>0, default_cth>=0."
                )

        return None

    def run_transient(self, circuit_data: dict) -> None:
        """Run a transient simulation."""
        if not self._ensure_backend_ready():
            return
        contract_issue = self._prevalidate_runtime_contract(circuit_data)
        if contract_issue:
            self.error.emit(contract_issue)
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)

        # Emit immediate feedback so UI shows activity right away
        self.progress.emit(-1, "Starting simulation...")

        # Create worker thread (deferred start to let UI paint first)
        worker = SimulationWorker(self._backend, circuit_data, self._settings)
        self._attach_and_schedule_worker(worker)

    def run_transient_project(self, project: Any) -> None:
        """Run transient simulation converting the GUI project off the UI thread."""
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return
        self.apply_project_simulation_settings(project)

        self._set_state(SimulationState.RUNNING)
        self.progress.emit(-1, "Preparing simulation...")

        worker = SimulationWorker(
            self._backend,
            None,
            self._settings,
            circuit_source=project,
            circuit_builder=self.convert_gui_circuit_cached,
            contract_validator=self._prevalidate_runtime_contract,
        )
        self._attach_and_schedule_worker(worker)

    def _attach_and_schedule_worker(self, worker: SimulationWorker) -> None:
        """Attach worker signals and start on next event-loop turn."""
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.data_point.connect(self._on_data_point)
        worker.finished_signal.connect(self._on_finished)
        worker.error.connect(self._on_error)
        worker.finished.connect(worker.deleteLater)
        QTimer.singleShot(0, self._start_pending_worker)

    def _start_pending_worker(self) -> None:
        """Start the queued simulation worker if state is still running."""
        worker = self._worker
        if worker is None:
            return
        if self._state not in (SimulationState.RUNNING, SimulationState.PAUSED):
            return
        if worker.isRunning():
            return
        worker.start(QThread.Priority.LowPriority)

    def run_dc_operating_point(
        self,
        circuit_data: dict,
        dc_settings: DCSettings | None = None,
    ) -> None:
        """Run DC operating point analysis.

        Args:
            circuit_data: Dictionary representation of the circuit.
            dc_settings: DC analysis settings. If None, builds from SimulationSettings.
        """
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)
        self.progress.emit(0, "Running DC analysis...")

        # Build DC settings from SimulationSettings if not provided
        if dc_settings is None:
            dc_settings = DCSettings(
                strategy=self._settings.dc_strategy,
                max_iterations=self._settings.max_newton_iterations,
                enable_limiting=self._settings.enable_voltage_limiting,
                max_voltage_step=self._settings.max_voltage_step,
                gmin_initial=self._settings.gmin_initial,
                gmin_final=self._settings.gmin_final,
                source_steps=self._settings.dc_source_steps,
            )

        result = DCResult()

        try:
            # Check if backend supports DC analysis
            if self._backend.has_capability("dc"):
                # Use backend with strategy fallback to improve robustness for
                # switching circuits where a single DC method may fail.
                backend_result = self._run_dc_with_fallback(circuit_data, dc_settings)

                # Convert backend result to local DCResult
                result.node_voltages = backend_result.node_voltages.copy()
                result.branch_currents = backend_result.branch_currents.copy()
                result.power_dissipation = backend_result.power_dissipation.copy()
                result.error_message = backend_result.error_message

                # Store convergence info for potential diagnostics dialog
                self._last_convergence_info = backend_result.convergence_info

                if backend_result.error_message:
                    self._set_state(SimulationState.ERROR)
                    self.error.emit(backend_result.error_message)
                else:
                    self.progress.emit(100, "DC analysis complete")
                    self._set_state(SimulationState.COMPLETED)
            else:
                result.error_message = (
                    f"DC analysis is not available in backend {self._backend.info.label()}."
                )
                self._set_state(SimulationState.ERROR)
                self.error.emit(result.error_message)

            self.dc_finished.emit(result)

        except Exception as e:
            result.error_message = str(e)
            self._set_state(SimulationState.ERROR)
            self.error.emit(str(e))
            self.dc_finished.emit(result)

    def _run_dc_with_fallback(self, circuit_data: dict, dc_settings: DCSettings) -> BackendDCResult:
        """Run DC analysis using configured strategy and deterministic fallbacks."""
        attempts = self._build_dc_fallback_attempts(dc_settings)
        errors: list[str] = []
        first_result: BackendDCResult | None = None
        last_result: BackendDCResult | None = None

        for index, attempt in enumerate(attempts):
            if index > 0:
                self.progress.emit(
                    0,
                    f"Retrying DC with '{attempt.strategy}' strategy...",
                )
            backend_result = self._backend.run_dc(circuit_data, attempt)
            if first_result is None:
                first_result = backend_result
            last_result = backend_result
            if not backend_result.error_message:
                return backend_result
            errors.append(f"{attempt.strategy}: {backend_result.error_message}")

        if last_result is None:
            return BackendDCResult(
                error_message="DC analysis backend returned no result.",
            )

        if errors:
            summarized = " | ".join(errors)
            last_result.error_message = f"DC analysis failed after fallback attempts: {summarized}"
        return last_result

    @staticmethod
    def _build_dc_fallback_attempts(base: DCSettings) -> list[DCSettings]:
        """Build ordered DC strategy attempts for robust operating-point solves."""
        normalized = replace(
            base,
            strategy=str(base.strategy or "auto").strip().lower() or "auto",
            source_steps=max(1, int(base.source_steps)),
            max_iterations=max(1, int(base.max_iterations)),
            max_voltage_step=max(0.05, float(base.max_voltage_step)),
            gmin_initial=max(1e-12, float(base.gmin_initial)),
            gmin_final=max(1e-15, float(base.gmin_final)),
        )
        if normalized.gmin_final >= normalized.gmin_initial:
            normalized = replace(normalized, gmin_final=max(1e-15, normalized.gmin_initial * 1e-3))

        tuned_gmin_initial = min(normalized.gmin_initial, 1e-3)
        tuned_gmin_final = min(normalized.gmin_final, tuned_gmin_initial * 1e-3)
        tuned_gmin_final = max(1e-15, tuned_gmin_final)
        if tuned_gmin_final >= tuned_gmin_initial:
            tuned_gmin_final = max(1e-15, tuned_gmin_initial * 1e-3)

        preferred_order = {
            "gmin": ("gmin", "direct", "auto", "source", "pseudo"),
            "direct": ("direct", "auto", "gmin", "source", "pseudo"),
            "source": ("source", "auto", "gmin", "direct", "pseudo"),
            "pseudo": ("pseudo", "auto", "gmin", "direct", "source"),
            "auto": ("auto", "direct", "gmin", "source", "pseudo"),
        }.get(normalized.strategy, ("auto", "direct", "gmin", "source", "pseudo"))

        attempts: list[DCSettings] = []
        seen: set[tuple[str, float, float, int, int, bool, float]] = set()

        def add_attempt(candidate: DCSettings) -> None:
            key = (
                str(candidate.strategy),
                float(candidate.gmin_initial),
                float(candidate.gmin_final),
                int(candidate.source_steps),
                int(candidate.max_iterations),
                bool(candidate.enable_limiting),
                float(candidate.max_voltage_step),
            )
            if key in seen:
                return
            seen.add(key)
            attempts.append(candidate)

        add_attempt(normalized)
        for strategy in preferred_order:
            if strategy == "gmin":
                add_attempt(
                    replace(
                        normalized,
                        strategy="gmin",
                        gmin_initial=tuned_gmin_initial,
                        gmin_final=tuned_gmin_final,
                        enable_limiting=True,
                        max_voltage_step=min(normalized.max_voltage_step, 2.0),
                    )
                )
            elif strategy == "source":
                add_attempt(
                    replace(
                        normalized,
                        strategy="source",
                        source_steps=max(normalized.source_steps, 20),
                        enable_limiting=True,
                    )
                )
            else:
                add_attempt(
                    replace(
                        normalized,
                        strategy=strategy,
                        enable_limiting=True,
                    )
                )
        return attempts

    def run_ac_analysis(
        self,
        circuit_data: dict,
        f_start: float,
        f_stop: float,
        points_per_decade: int = 10,
        ac_settings: ACSettings | None = None,
    ) -> None:
        """Run AC frequency sweep analysis.

        Args:
            circuit_data: Dictionary representation of the circuit.
            f_start: Start frequency (Hz).
            f_stop: Stop frequency (Hz).
            points_per_decade: Number of points per decade.
            ac_settings: AC analysis settings. If None, uses parameters above.
        """
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)
        self.progress.emit(0, "Running AC analysis...")

        # Build settings if not provided
        if ac_settings is None:
            ac_settings = ACSettings(
                f_start=f_start,
                f_stop=f_stop,
                points_per_decade=points_per_decade,
            )

        result = ACResult()

        try:
            # Check if backend supports AC analysis
            if self._backend.has_capability("ac"):
                # Use real backend for AC analysis
                backend_result: BackendACResult = self._backend.run_ac(circuit_data, ac_settings)

                # Convert backend result to local ACResult
                result.frequencies = backend_result.frequencies.copy()
                result.magnitude = {k: list(v) for k, v in backend_result.magnitude.items()}
                result.phase = {k: list(v) for k, v in backend_result.phase.items()}
                result.error_message = backend_result.error_message

                if backend_result.error_message:
                    self._set_state(SimulationState.ERROR)
                    self.error.emit(backend_result.error_message)
                else:
                    self.progress.emit(100, "AC analysis complete")
                    self._set_state(SimulationState.COMPLETED)
            else:
                result.error_message = (
                    f"AC analysis is not available in backend {self._backend.info.label()}."
                )
                self._set_state(SimulationState.ERROR)
                self.error.emit(result.error_message)

            self.ac_finished.emit(result)

        except Exception as e:
            result.error_message = str(e)
            self._set_state(SimulationState.ERROR)
            self.error.emit(str(e))
            self.ac_finished.emit(result)

    def run_parameter_sweep(
        self, circuit_data: dict, sweep_settings: ParameterSweepSettings
    ) -> None:
        """Run a parameter sweep across multiple simulations."""
        if not self._ensure_backend_ready():
            return
        contract_issue = self._prevalidate_runtime_contract(circuit_data)
        if contract_issue:
            self.error.emit(contract_issue)
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)

        self._sweep_worker = ParameterSweepWorker(
            self._backend,
            circuit_data,
            sweep_settings,
            self._settings,
        )
        self._sweep_worker.progress.connect(self._on_progress)
        self._sweep_worker.finished_signal.connect(self._on_parameter_sweep_finished)
        self._sweep_worker.error.connect(self._on_error)
        self._sweep_worker.finished.connect(self._on_sweep_thread_finished)
        self._sweep_worker.start()

    def stop(self) -> None:
        """Stop the current simulation."""
        if self._worker:
            self._worker.cancel()
            if self._worker.isRunning():
                self._worker.wait(5000)  # Wait up to 5 seconds
            if self._state in (SimulationState.RUNNING, SimulationState.PAUSED):
                self._set_state(SimulationState.CANCELLED)

        if self._sweep_worker and self._sweep_worker.isRunning():
            self._sweep_worker.cancel()
            self._sweep_worker.wait(5000)
            self._set_state(SimulationState.CANCELLED)

    def pause(self) -> None:
        """Pause the current simulation."""
        if self._worker and self._state == SimulationState.RUNNING:
            self._worker.pause()
            self._set_state(SimulationState.PAUSED)

    def resume(self) -> None:
        """Resume a paused simulation."""
        if self._worker and self._state == SimulationState.PAUSED:
            self._worker.resume()
            self._set_state(SimulationState.RUNNING)

    def _set_state(self, state: SimulationState) -> None:
        """Set state and emit signal."""
        self._state = state
        self.state_changed.emit(state)

    def _on_progress(self, value: float, message: str) -> None:
        """Handle progress update from worker."""
        self.progress.emit(value, message)

    def _on_data_point(self, time: float, signals: dict) -> None:
        """Handle data point from worker."""
        self.data_point.emit(time, signals)

    def _on_finished(self, result: SimulationResult) -> None:
        """Handle simulation completion."""
        self._last_result = result
        if result.error_message == "Simulation cancelled":
            self._set_state(SimulationState.CANCELLED)
        elif result.error_message:
            self._set_state(SimulationState.ERROR)
        else:
            self._set_state(SimulationState.COMPLETED)
        self.simulation_finished.emit(result)

    def _on_parameter_sweep_finished(self, result: ParameterSweepResult) -> None:
        """Handle completion of a parameter sweep."""
        if self._sweep_worker and self._sweep_worker.was_cancelled:
            self._set_state(SimulationState.CANCELLED)
        elif not result.runs:
            self._set_state(SimulationState.ERROR)
        else:
            self._set_state(SimulationState.COMPLETED)

        self.parameter_sweep_finished.emit(result)

    def _on_sweep_thread_finished(self) -> None:
        """Clear sweep worker reference when the thread ends."""
        self._sweep_worker = None

    def _on_error(self, message: str) -> None:
        """Handle error from worker."""
        self._set_state(SimulationState.ERROR)
        self.error.emit(message)

    def convert_gui_circuit(self, project) -> dict:
        """Convert GUI project/circuit to simulation data format."""
        return self._circuit_data_builder.build(
            project,
            settings=self._settings,
            normalize_step_mode=normalize_step_mode,
            normalize_formulation_mode=normalize_formulation_mode,
            normalize_thermal_policy=normalize_thermal_policy,
            normalize_control_mode=normalize_control_mode,
            build_node_map=build_node_map,
            build_node_alias_map=build_node_alias_map,
            copy_result=True,
            cooperative_yield=True,
        )

    def convert_gui_circuit_cached(self, project) -> dict:
        """Convert GUI circuit using cache-optimized worker semantics.

        Returns payload references directly from conversion cache. Callers must
        treat the returned dict as read-only.
        """
        return self._circuit_data_builder.build(
            project,
            settings=self._settings,
            normalize_step_mode=normalize_step_mode,
            normalize_formulation_mode=normalize_formulation_mode,
            normalize_thermal_policy=normalize_thermal_policy,
            normalize_control_mode=normalize_control_mode,
            build_node_map=build_node_map,
            build_node_alias_map=build_node_alias_map,
            copy_result=False,
            cooperative_yield=False,
        )

    def _convert_gui_circuit_for_worker(self, project) -> dict:
        """Backward-compatible alias for worker conversion path."""
        return self.convert_gui_circuit_cached(project)
