"""Backend discovery and placeholder adapter for simulations."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module, metadata
from pathlib import Path
import threading
from typing import Any, Callable, Protocol, TYPE_CHECKING

import math

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from pulsimgui.services.simulation_service import SimulationSettings

from pulsimgui.services.circuit_converter import CircuitConversionError, CircuitConverter


@dataclass
class BackendInfo:
    """Metadata describing the active simulation backend."""

    identifier: str
    name: str
    version: str
    status: str
    location: str | None = None
    capabilities: set[str] = field(default_factory=set)
    message: str = ""

    def label(self) -> str:
        """Return a human-readable label for UI badges."""
        parts = [self.name, self.version]
        if self.status not in {"available", "detected"}:
            parts.append(f"[{self.status}]")
        return " ".join(filter(None, parts))


@dataclass
class BackendRunResult:
    """Lightweight container for backend simulation output."""

    time: list[float] = field(default_factory=list)
    signals: dict[str, list[float]] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


@dataclass
class BackendCallbacks:
    """Callbacks that a backend should invoke during execution."""

    progress: Callable[[float, str], None]
    data_point: Callable[[float, dict[str, float]], None]
    check_cancelled: Callable[[], bool]
    wait_if_paused: Callable[[], None]


class SimulationBackend(Protocol):
    """Protocol describing the minimal backend surface used by the GUI."""

    info: BackendInfo

    def run_transient(
        self,
        circuit_data: dict,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        ...

    def request_pause(self, run_id: int | None = None) -> None:
        ...

    def request_resume(self, run_id: int | None = None) -> None:
        ...

    def request_stop(self, run_id: int | None = None) -> None:
        ...


class PlaceholderBackend(SimulationBackend):
    """Fallback backend that reuses the GUI's synthetic waveforms."""

    def __init__(self, info: BackendInfo | None = None) -> None:
        self.info = info or BackendInfo(
            identifier="placeholder",
            name="placeholder",
            version="0.0",
            status="placeholder",
            capabilities={"transient"},
            message="Running in demo mode; install pulsit backend to enable real simulations.",
        )

    def run_transient(
        self,
        circuit_data: dict,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        result = BackendRunResult()

        callbacks.progress(0, "Initializing simulation...")
        total_points = max(1, int(settings.output_points))
        duration = max(settings.t_stop - settings.t_start, 1e-12)
        dt = duration / total_points

        callbacks.progress(5, "Building circuit model...")
        time_axis: list[float] = []
        signals: dict[str, list[float]] = {}

        for index in range(total_points + 1):
            if callbacks.check_cancelled():
                result.error_message = "Simulation cancelled"
                return result

            callbacks.wait_if_paused()

            current_time = settings.t_start + index * dt
            time_axis.append(current_time)

            sample = self._simulate_step(current_time)
            for name, value in sample.items():
                signals.setdefault(name, []).append(value)

            if index % 100 == 0:
                callbacks.data_point(current_time, sample)

            if total_points:
                progress_value = 10 + (index / total_points) * 85
                if index % (max(1, total_points // 20)) == 0:
                    callbacks.progress(progress_value, f"Time: {current_time*1e6:.1f}µs")

        callbacks.progress(95, "Finalizing results...")

        result.time = time_axis
        result.signals = signals
        result.statistics = {
            "simulation_time": duration,
            "time_steps": len(time_axis),
            "signals_count": len(signals),
        }

        callbacks.progress(100, "Simulation complete")
        return result

    def _simulate_step(self, t: float) -> dict[str, float]:
        """Generate a deterministic placeholder sample for demos."""
        v_out = 5.0 * (1 - math.exp(-t * 10000)) * math.sin(2 * math.pi * 1000 * t)
        v_in = 10.0 * math.sin(2 * math.pi * 1000 * t)
        return {
            "V(out)": v_out,
            "V(in)": v_in,
            "I(R1)": v_out / 1000.0,
        }

    def request_pause(self, run_id: int | None = None) -> None:  # pragma: no cover - trivial
        """Placeholder backend executes entirely within GUI thread control."""

    def request_resume(self, run_id: int | None = None) -> None:  # pragma: no cover - trivial
        """Placeholder backend executes entirely within GUI thread control."""

    def request_stop(self, run_id: int | None = None) -> None:  # pragma: no cover - trivial
        """Placeholder backend executes entirely within GUI thread control."""


class PulsimBackend(SimulationBackend):
    """Adapter that executes simulations via the native Pulsim backend."""

    def __init__(self, module: Any, info: BackendInfo) -> None:
        self._module = module
        self.info = info
        self._converter = CircuitConverter(module)
        self._controllers: dict[int, Any] = {}
        self._lock = threading.Lock()

    def run_transient(
        self,
        circuit_data: dict,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        result = BackendRunResult()

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            result.error_message = str(exc)
            return result

        options = self._build_options(settings)
        simulator = self._module.Simulator(circuit, options)
        controller = self._module.SimulationController()
        run_id = threading.get_ident()
        self._register_controller(run_id, controller)

        callbacks.progress(0.0, "Starting Pulsim simulation...")

        try:
            progress_callback = self._progress_dispatcher(callbacks, controller)
            sim_result = simulator.run_transient_with_progress(
                callback=None,
                event_callback=None,
                control=controller,
                progress_callback=progress_callback,
                min_interval_ms=50,
                min_steps=200,
            )
            callbacks.progress(95.0, "Collecting waveform data...")
            self._populate_backend_result(result, sim_result)
            if not result.error_message:
                callbacks.progress(100.0, "Simulation complete")
        except Exception as exc:  # pragma: no cover - backend failure path
            result.error_message = str(exc)
        finally:
            self._unregister_controller(run_id)

        return result

    def request_pause(self, run_id: int | None = None) -> None:
        controller = self._controller_for(run_id)
        if controller:
            controller.request_pause()

    def request_resume(self, run_id: int | None = None) -> None:
        controller = self._controller_for(run_id)
        if controller:
            controller.request_resume()

    def request_stop(self, run_id: int | None = None) -> None:
        controller = self._controller_for(run_id)
        if controller:
            controller.request_stop()

    def _register_controller(self, run_id: int, controller: Any) -> None:
        with self._lock:
            self._controllers[run_id] = controller

    def _unregister_controller(self, run_id: int) -> None:
        with self._lock:
            self._controllers.pop(run_id, None)

    def _controller_for(self, run_id: int | None) -> Any | None:
        if run_id is None:
            return None
        with self._lock:
            return self._controllers.get(run_id)

    def _progress_dispatcher(
        self,
        callbacks: BackendCallbacks,
        controller: Any,
    ) -> Callable[[Any], None]:
        def _handler(progress: Any) -> None:
            payload = progress.to_dict() if hasattr(progress, "to_dict") else {}
            percent = float(payload.get("progress_percent", 0.0))
            message = self._format_progress_message(payload)
            callbacks.progress(percent, message)
            if callbacks.check_cancelled():
                controller.request_stop()

        return _handler

    def _format_progress_message(self, payload: dict[str, Any]) -> str:
        current_time = payload.get("current_time")
        if current_time is not None:
            return f"t={current_time*1e6:.2f}µs"
        steps = payload.get("steps_completed")
        if steps is not None:
            return f"Steps: {int(steps)}"
        return "Running..."

    def _populate_backend_result(self, backend_result: BackendRunResult, sim_result: Any) -> None:
        if hasattr(sim_result, "to_dict"):
            payload = sim_result.to_dict()
            backend_result.time = list(payload.get("time", []))
            backend_result.signals = {
                name: list(values) for name, values in payload.get("signals", {}).items()
            }
        else:  # pragma: no cover - fallback path
            backend_result.time = list(getattr(sim_result, "time", []))

        backend_result.statistics = {
            "total_steps": getattr(sim_result, "total_steps", None),
            "elapsed_seconds": getattr(sim_result, "elapsed_seconds", None),
            "signals": list(backend_result.signals.keys()),
        }

        status_value = getattr(sim_result, "final_status", None)
        if status_value is not None:
            try:
                status = self._module.SolverStatus(status_value)
                backend_result.statistics["status"] = status.name
                if status != self._module.SolverStatus.Success:
                    backend_result.error_message = getattr(
                        sim_result,
                        "status_message",
                        f"Solver exited with status {status.name}",
                    )
            except Exception:  # pragma: no cover - best-effort cast
                backend_result.statistics["status"] = status_value

    def _build_options(self, settings: "SimulationSettings") -> Any:
        opts = self._module.SimulationOptions()
        opts.tstart = settings.t_start
        opts.tstop = settings.t_stop
        opts.dt = self._compute_time_step(settings)
        if hasattr(opts, "dtmax"):
            opts.dtmax = settings.max_step
        elif hasattr(opts, "max_step"):
            opts.max_step = settings.max_step
        if hasattr(opts, "abstol"):
            opts.abstol = settings.abs_tol
        if hasattr(opts, "reltol"):
            opts.reltol = settings.rel_tol
        if hasattr(opts, "progress_min_interval_ms"):
            opts.progress_min_interval_ms = 50
        if hasattr(opts, "progress_min_steps"):
            opts.progress_min_steps = 200
        return opts

    def _compute_time_step(self, settings: "SimulationSettings") -> float:
        if settings.t_step > 0:
            return settings.t_step
        duration = max(settings.t_stop - settings.t_start, 1e-12)
        points = max(settings.output_points, 1)
        return duration / points


class BackendLoader:
    """Detect and initialize the best available backend implementation."""

    @dataclass
    class _BackendCandidate:
        info: BackendInfo
        factory: Callable[[], SimulationBackend]

    def __init__(self, preferred_backend_id: str | None = None) -> None:
        self._candidates = self._discover_candidates()
        if not self._candidates:
            placeholder = self._create_placeholder_candidate(
                message="Running in demo mode; install pulsit backend to enable real simulations.",
            )
            self._candidates[placeholder.info.identifier] = placeholder
        self._active_id: str | None = None
        self._backend = self._initialize_active(preferred_backend_id)

    @property
    def backend(self) -> SimulationBackend:
        """Return the active backend (placeholder if discovery failed)."""
        return self._backend

    @property
    def available_backends(self) -> list[BackendInfo]:
        """Return metadata for every discoverable backend."""
        return [candidate.info for candidate in self._candidates.values()]

    @property
    def active_backend_id(self) -> str | None:
        return self._active_id

    def activate(self, identifier: str) -> BackendInfo:
        """Activate the backend with the provided identifier."""
        if identifier not in self._candidates:
            raise ValueError(f"Unknown backend '{identifier}'")
        backend = self._instantiate(identifier)
        self._backend = backend
        self._active_id = identifier
        return backend.info

    def _initialize_active(self, preferred_backend_id: str | None) -> SimulationBackend:
        identifier = preferred_backend_id if preferred_backend_id in self._candidates else None
        if identifier is None:
            identifier = self._pick_default_identifier()
        self._active_id = identifier
        return self._instantiate(identifier)

    def _instantiate(self, identifier: str) -> SimulationBackend:
        candidate = self._candidates[identifier]
        return candidate.factory()

    def _pick_default_identifier(self) -> str:
        for identifier in self._candidates:
            if identifier != "placeholder":
                return identifier
        return next(iter(self._candidates))

    def _discover_candidates(self) -> dict[str, "BackendLoader._BackendCandidate"]:
        candidates: dict[str, BackendLoader._BackendCandidate] = {}

        pulsim_candidate, pulsim_error = self._create_pulsim_candidate()
        if pulsim_candidate:
            candidates[pulsim_candidate.info.identifier] = pulsim_candidate

        for entry_candidate in self._load_entry_point_candidates():
            candidates.setdefault(entry_candidate.info.identifier, entry_candidate)

        placeholder_status = "error" if pulsim_error else "placeholder"
        placeholder_message = (
            f"Pulsim backend unavailable: {pulsim_error}"
            if pulsim_error
            else "Demo mode; install Pulsim for full fidelity."
        )
        placeholder_candidate = self._create_placeholder_candidate(
            message=placeholder_message,
            status=placeholder_status,
        )
        candidates.setdefault(placeholder_candidate.info.identifier, placeholder_candidate)

        return candidates

    def _create_placeholder_candidate(
        self,
        *,
        message: str,
        status: str = "placeholder",
    ) -> "BackendLoader._BackendCandidate":
        info = BackendInfo(
            identifier="placeholder",
            name="Demo backend",
            version="0.0",
            status=status,
            capabilities={"transient"},
            message=message,
        )
        return BackendLoader._BackendCandidate(info=info, factory=lambda: PlaceholderBackend(info))

    def _create_pulsim_candidate(self) -> tuple["BackendLoader._BackendCandidate" | None, str | None]:
        try:
            module = import_module("pulsim")
        except Exception as exc:  # pragma: no cover - pulsim missing
            return None, str(exc)

        try:
            version = getattr(module, "__version__", metadata.version("pulsim"))
        except metadata.PackageNotFoundError:  # pragma: no cover - defensive
            version = getattr(module, "__version__", "unknown")

        location = Path(getattr(module, "__file__", "")).resolve().parent.as_posix()
        capabilities = {"transient"}
        if hasattr(module, "ThermalSimulator"):
            capabilities.add("thermal")
        info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version=version,
            status="available",
            location=location,
            capabilities=capabilities,
            message="Using native Pulsim backend",
        )
        candidate = BackendLoader._BackendCandidate(
            info=info,
            factory=lambda: PulsimBackend(module, info),
        )
        return candidate, None

    def _load_entry_point_candidates(self) -> list["BackendLoader._BackendCandidate"]:
        try:
            entry_points = metadata.entry_points()
        except Exception:  # pragma: no cover - entry point lookup failed
            return []

        if hasattr(entry_points, "select"):
            entries = entry_points.select(group="pulsimgui.backends")
        else:  # pragma: no cover - legacy importlib.metadata API
            entries = entry_points.get("pulsimgui.backends", [])  # type: ignore[attr-defined]

        candidates: list[BackendLoader._BackendCandidate] = []
        for entry in entries:
            identifier = entry.name
            try:
                loaded = entry.load()
            except Exception:
                continue

            if callable(loaded):
                factory_callable = loaded
            else:  # pragma: no cover - unsupported entry type
                continue

            try:
                backend = factory_callable()
            except Exception:
                continue

            info = backend.info
            del backend

            candidates.append(
                BackendLoader._BackendCandidate(
                    info=info,
                    factory=lambda factory_callable=factory_callable: factory_callable(),
                )
            )

        return candidates


__all__ = [
    "BackendCallbacks",
    "BackendInfo",
    "BackendLoader",
    "BackendRunResult",
    "PlaceholderBackend",
    "PulsimBackend",
    "SimulationBackend",
]
