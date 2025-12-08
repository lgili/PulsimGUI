"""Simulation service for running Pulsim simulations."""

from __future__ import annotations

import copy
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Any, Callable, TYPE_CHECKING

from PySide6.QtCore import QObject, Signal, QMutex, QThread, QWaitCondition

from pulsimgui.services.backend_adapter import (
    BackendCallbacks,
    BackendInfo,
    BackendLoader,
    SimulationBackend,
)
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


@dataclass
class SimulationSettings:
    """Settings for transient simulation."""

    # Time settings
    t_start: float = 0.0
    t_stop: float = 1e-3  # 1ms default
    t_step: float = 1e-6  # 1us default

    # Solver settings
    solver: str = "auto"  # auto, rk4, rk45, bdf
    max_step: float = 1e-6
    rel_tol: float = 1e-4
    abs_tol: float = 1e-6

    # Output settings
    output_points: int = 10000


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
        circuit_data: dict,
        settings: SimulationSettings,
        parent=None,
    ):
        super().__init__(parent)
        self._backend = backend
        self._circuit_data = circuit_data
        self._settings = settings
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

            result.time = list(backend_result.time)
            result.signals = {name: list(values) for name, values in backend_result.signals.items()}
            result.statistics = dict(backend_result.statistics)
            result.error_message = backend_result.error_message

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

    def __init__(self, settings_service: "SettingsService" | None = None, parent=None):
        super().__init__(parent)

        self._state = SimulationState.IDLE
        self._worker: SimulationWorker | None = None
        self._sweep_worker: ParameterSweepWorker | None = None
        self._settings = SimulationSettings()
        self._last_result: SimulationResult | None = None
        self._settings_service = settings_service
        preferred_backend = None
        if settings_service is not None:
            preferred_backend = settings_service.get_backend_preference()
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

    def _ensure_backend_ready(self) -> bool:
        """Emit a user-facing error if no backend is currently usable."""
        if self.is_backend_ready:
            return True
        issue = self.backend_issue_message or "Simulation backend unavailable."
        self.error.emit(f"Simulation backend unavailable: {issue}")
        return False

    def run_transient(self, circuit_data: dict) -> None:
        """Run a transient simulation."""
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)

        # Create and start worker thread
        self._worker = SimulationWorker(self._backend, circuit_data, self._settings)
        self._worker.progress.connect(self._on_progress)
        self._worker.data_point.connect(self._on_data_point)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def run_dc_operating_point(self, circuit_data: dict) -> None:
        """Run DC operating point analysis."""
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)
        self.progress.emit(0, "Running DC analysis...")

        # Placeholder DC analysis
        # In real implementation, this would solve the DC equations
        result = DCResult()

        try:
            # Simulate DC solution - placeholder
            result.node_voltages = {
                "V(out)": 5.0,
                "V(in)": 10.0,
                "V(gnd)": 0.0,
            }
            result.branch_currents = {
                "I(R1)": 0.005,
                "I(V1)": -0.005,
            }
            result.power_dissipation = {
                "P(R1)": 0.025,
            }

            self.progress.emit(100, "DC analysis complete")
            self._set_state(SimulationState.COMPLETED)
            self.dc_finished.emit(result)

        except Exception as e:
            result.error_message = str(e)
            self._set_state(SimulationState.ERROR)
            self.error.emit(str(e))
            self.dc_finished.emit(result)

    def run_ac_analysis(
        self, circuit_data: dict, f_start: float, f_stop: float, points_per_decade: int = 10
    ) -> None:
        """Run AC frequency sweep analysis."""
        if not self._ensure_backend_ready():
            return
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)
        self.progress.emit(0, "Running AC analysis...")

        result = ACResult()

        try:
            import math

            # Generate frequency points (logarithmic)
            decades = math.log10(f_stop / f_start)
            num_points = int(decades * points_per_decade)

            result.frequencies = []
            result.magnitude = {"V(out)/V(in)": []}
            result.phase = {"V(out)/V(in)": []}

            for i in range(num_points + 1):
                f = f_start * (10 ** (i * decades / num_points))
                result.frequencies.append(f)

                # Placeholder: Generate dummy Bode plot data
                # This simulates a simple RC low-pass filter response
                fc = 1000  # cutoff frequency
                mag_db = -10 * math.log10(1 + (f / fc) ** 2)
                phase_deg = -math.degrees(math.atan(f / fc))

                result.magnitude["V(out)/V(in)"].append(mag_db)
                result.phase["V(out)/V(in)"].append(phase_deg)

                progress = (i / num_points) * 100
                self.progress.emit(progress, f"Frequency: {f:.1f}Hz")

            self.progress.emit(100, "AC analysis complete")
            self._set_state(SimulationState.COMPLETED)
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
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)  # Wait up to 5 seconds
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
        circuit_data = {
            "components": [],
            "wires": [],
            "nodes": {},
            "node_map": {},
            "node_aliases": {},
            "metadata": {},
        }

        if not project:
            return circuit_data

        circuit = project.get_active_circuit()
        if circuit is None:
            return circuit_data

        node_map_raw = build_node_map(circuit)
        alias_map = build_node_alias_map(circuit, node_map_raw)
        circuit_data["node_aliases"] = alias_map
        circuit_data["metadata"] = {"name": circuit.name}

        component_node_map: dict[str, list[str]] = {}

        for comp in circuit.components.values():
            comp_dict = comp.to_dict()
            comp_dict["parameters"] = copy.deepcopy(comp.parameters)
            comp_id = str(comp.id)
            pin_nodes: list[str] = []
            for pin_index in range(len(comp.pins)):
                node_name = node_map_raw.get((comp_id, pin_index))
                if node_name is None:
                    node_name = ""
                pin_nodes.append(node_name)
            comp_dict["pin_nodes"] = pin_nodes
            circuit_data["components"].append(comp_dict)
            component_node_map[comp_id] = pin_nodes

        circuit_data["node_map"] = component_node_map

        for wire in circuit.wires.values():
            circuit_data["wires"].append(wire.to_dict())

        return circuit_data
