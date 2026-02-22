"""Backend discovery and placeholder adapter for simulations."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from importlib import import_module, metadata
from pathlib import Path
import math
import threading
import time
from typing import Any, Callable, Protocol, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from pulsimgui.services.simulation_service import SimulationSettings

from pulsimgui.services.circuit_converter import CircuitConversionError, CircuitConverter
from pulsimgui.services.backend_types import (
    ACResult,
    ACSettings,
    BackendVersion,
    ConvergenceInfo,
    DCResult,
    DCSettings,
    IterationRecord,
    MIN_BACKEND_API,
    ProblematicVariable,
    ThermalDeviceResult,
    ThermalResult,
    ThermalSettings,
    TransientResult,
    TransientSettings,
    FosterStage,
    LossBreakdown,
)


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
    parsed_version: BackendVersion | None = None
    is_compatible: bool = True
    compatibility_warning: str = ""
    unavailable_features: list[str] = field(default_factory=list)

    def label(self) -> str:
        """Return a human-readable label for UI badges."""
        parts = [self.name, self.version]
        if self.status not in {"available", "detected"}:
            parts.append(f"[{self.status}]")
        return " ".join(filter(None, parts))

    def check_compatibility(self) -> None:
        """Check version compatibility and update status fields."""
        if self.parsed_version is None:
            try:
                self.parsed_version = BackendVersion.from_string(self.version)
            except ValueError:
                self.is_compatible = False
                self.compatibility_warning = f"Unable to parse version: {self.version}"
                return

        if not self.parsed_version.is_compatible_with(MIN_BACKEND_API):
            self.is_compatible = False
            self.compatibility_warning = (
                f"Backend version {self.version} is older than minimum required "
                f"({MIN_BACKEND_API.major}.{MIN_BACKEND_API.minor}.{MIN_BACKEND_API.patch}). "
                "Some features may not work correctly."
            )

        # Determine unavailable features based on capabilities
        all_features = {"dc", "ac", "thermal", "transient"}
        self.unavailable_features = sorted(all_features - self.capabilities)


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


@dataclass(frozen=True)
class _TransientRetryProfile:
    """Retry profile used to recover from transient convergence failures."""

    name: str
    dc_strategy: str | None = None
    min_newton_iterations: int | None = None
    force_voltage_limiting: bool | None = None
    max_voltage_step: float | None = None
    dt_scale: float = 1.0


class SimulationBackend(Protocol):
    """Protocol describing the full backend interface used by the GUI.

    All simulation backends must implement this protocol. The protocol supports
    feature detection via `has_capability()` for graceful degradation.
    """

    info: BackendInfo

    @property
    def capabilities(self) -> set[str]:
        """Return set of supported capability names."""
        ...

    def has_capability(self, name: str) -> bool:
        """Check if a specific capability is supported."""
        ...

    def run_transient(
        self,
        circuit_data: dict,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        ...

    def run_dc(
        self,
        circuit_data: dict,
        settings: DCSettings,
    ) -> DCResult:
        """Run DC operating point analysis."""
        ...

    def run_ac(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> ACResult:
        """Run AC frequency-domain analysis."""
        ...

    def run_thermal(
        self,
        circuit_data: dict,
        electrical_result: TransientResult,
        settings: ThermalSettings,
    ) -> ThermalResult:
        """Run thermal simulation."""
        ...

    def request_pause(self, run_id: int | None = None) -> None:
        ...

    def request_resume(self, run_id: int | None = None) -> None:
        ...

    def request_stop(self, run_id: int | None = None) -> None:
        ...


class PlaceholderBackend(SimulationBackend):
    """Fallback backend that generates synthetic data for demo mode."""

    def __init__(self, info: BackendInfo | None = None) -> None:
        self.info = info or BackendInfo(
            identifier="placeholder",
            name="Demo backend",
            version="0.0",
            status="placeholder",
            capabilities={"transient", "dc", "ac", "thermal"},
            message="Running in demo mode; install pulsim backend to enable real simulations.",
        )

    @property
    def capabilities(self) -> set[str]:
        """Return supported capabilities (all for demo)."""
        return self.info.capabilities

    def has_capability(self, name: str) -> bool:
        """Check if capability is supported."""
        return name in self.capabilities

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

    def run_dc(
        self,
        circuit_data: dict,
        settings: DCSettings,
    ) -> DCResult:
        """Generate synthetic DC operating point results."""
        # Generate deterministic synthetic data based on circuit
        node_voltages = {
            "V(in)": 12.0,
            "V(out)": 5.0,
            "V(gate)": 10.0,
        }
        branch_currents = {
            "I(Vin)": -0.5,
            "I(R1)": 0.005,
            "I(M1)": 0.5,
        }
        power_dissipation = {
            "R1": 0.025,
            "M1": 3.5,
        }
        convergence_info = ConvergenceInfo(
            converged=True,
            iterations=5,
            final_residual=1e-12,
            strategy_used="placeholder",
        )
        return DCResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            power_dissipation=power_dissipation,
            convergence_info=convergence_info,
        )

    def run_ac(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> ACResult:
        """Generate synthetic AC analysis results."""
        import numpy as np

        # Generate frequency points
        num_decades = max(1, int(math.log10(settings.f_stop / max(settings.f_start, 1))))
        num_points = num_decades * settings.points_per_decade
        frequencies = list(np.logspace(
            math.log10(settings.f_start),
            math.log10(settings.f_stop),
            num_points,
        ))

        # Generate synthetic Bode plot (simple low-pass filter response)
        fc = 1000.0  # Corner frequency
        magnitude: dict[str, list[float]] = {}
        phase: dict[str, list[float]] = {}

        for node in settings.output_nodes or ["V(out)"]:
            mag_values = []
            phase_values = []
            for f in frequencies:
                # Simple first-order low-pass response
                ratio = f / fc
                mag_db = -10 * math.log10(1 + ratio**2)
                phase_deg = -math.degrees(math.atan(ratio))
                mag_values.append(mag_db)
                phase_values.append(phase_deg)
            magnitude[node] = mag_values
            phase[node] = phase_values

        return ACResult(
            frequencies=frequencies,
            magnitude=magnitude,
            phase=phase,
        )

    def run_thermal(
        self,
        circuit_data: dict,
        electrical_result: TransientResult,
        settings: ThermalSettings,
    ) -> ThermalResult:
        """Generate synthetic thermal simulation results."""
        # Use electrical result time base or generate one
        if electrical_result.time:
            time = electrical_result.time
        else:
            time = [i * 1e-6 for i in range(1001)]

        # Generate synthetic device thermal data
        devices = []

        # MOSFET M1
        m1_temps = []
        for i, t in enumerate(time):
            # Exponential rise to steady state
            tau = 0.1e-3  # Thermal time constant
            steady_state = settings.ambient_temperature + 50.0
            temp = settings.ambient_temperature + (steady_state - settings.ambient_temperature) * (
                1 - math.exp(-t / tau)
            )
            m1_temps.append(temp)

        devices.append(ThermalDeviceResult(
            name="M1",
            junction_temperature=m1_temps,
            peak_temperature=max(m1_temps),
            steady_state_temperature=m1_temps[-1] if m1_temps else settings.ambient_temperature,
            losses=LossBreakdown(
                conduction=2.5,
                switching_on=0.3,
                switching_off=0.4,
                reverse_recovery=0.0,
            ),
            foster_stages=[
                FosterStage(resistance=0.5, capacitance=0.001),
                FosterStage(resistance=1.0, capacitance=0.01),
                FosterStage(resistance=2.0, capacitance=0.1),
            ],
            thermal_limit=150.0,
        ))

        # Diode D1
        d1_temps = []
        for i, t in enumerate(time):
            tau = 0.05e-3
            steady_state = settings.ambient_temperature + 30.0
            temp = settings.ambient_temperature + (steady_state - settings.ambient_temperature) * (
                1 - math.exp(-t / tau)
            )
            d1_temps.append(temp)

        devices.append(ThermalDeviceResult(
            name="D1",
            junction_temperature=d1_temps,
            peak_temperature=max(d1_temps),
            steady_state_temperature=d1_temps[-1] if d1_temps else settings.ambient_temperature,
            losses=LossBreakdown(
                conduction=0.8,
                switching_on=0.0,
                switching_off=0.0,
                reverse_recovery=0.15,
            ),
            foster_stages=[
                FosterStage(resistance=1.0, capacitance=0.002),
                FosterStage(resistance=2.0, capacitance=0.02),
            ],
            thermal_limit=175.0,
        ))

        return ThermalResult(
            time=time,
            devices=devices,
            ambient_temperature=settings.ambient_temperature,
            is_synthetic=True,
        )

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
        self._cached_capabilities: set[str] | None = None

    @property
    def capabilities(self) -> set[str]:
        """Return set of supported capability names."""
        if self._cached_capabilities is not None:
            return self._cached_capabilities

        caps = {"transient"}

        # Check for DC analysis (top-level or v1/v2 solver)
        if hasattr(self._module, "dc_operating_point") or hasattr(self._module, "solve_dc"):
            caps.add("dc")
        elif hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
            caps.add("dc")
        elif hasattr(self._module, "v1") and hasattr(self._module.v1, "DCConvergenceSolver"):
            caps.add("dc")

        # Check for AC analysis
        if hasattr(self._module, "run_ac") or hasattr(self._module, "ACAnalysis"):
            caps.add("ac")

        # Check for thermal simulation
        if hasattr(self._module, "ThermalSimulator"):
            caps.add("thermal")

        self._cached_capabilities = caps
        return caps

    def has_capability(self, name: str) -> bool:
        """Check if a specific capability is supported."""
        return name in self.capabilities

    def run_transient(
        self,
        circuit_data: dict,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        result = BackendRunResult()

        callbacks.progress(0.0, "Starting Pulsim simulation...")

        try:
            base_dt = self._compute_time_step(settings)
        except Exception as exc:
            result.error_message = str(exc)
            return result

        retry_profiles = self._build_transient_retry_profiles(settings)
        retry_errors: list[str] = []

        for retry_index, profile in enumerate(retry_profiles):
            if retry_index > 0:
                callbacks.progress(2.0, f"Retrying convergence with profile '{profile.name}'...")

            try:
                circuit = self._converter.build(circuit_data)
            except CircuitConversionError as exc:
                result.error_message = str(exc)
                return result

            attempt_settings = self._apply_transient_retry_profile(settings, profile)
            dt = base_dt * profile.dt_scale

            if hasattr(circuit, "set_timestep"):
                try:
                    circuit.set_timestep(dt)
                except Exception:
                    pass

            try:
                newton_opts = self._build_newton_options(attempt_settings, circuit)
                linear_solver = self._build_linear_solver_config()
                x0 = self._build_initial_state(circuit, attempt_settings)
                attempt_result = self._run_transient_once(
                    circuit,
                    attempt_settings,
                    callbacks,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
            except Exception as exc:
                attempt_result = BackendRunResult(error_message=str(exc))

            if not attempt_result.error_message:
                if retry_index > 0:
                    attempt_result.statistics["convergence_retry_profile"] = profile.name
                    attempt_result.statistics["convergence_retries"] = retry_index
                    attempt_result.statistics["convergence_retry_errors"] = retry_errors.copy()
                return attempt_result

            error_text = attempt_result.error_message
            if "cancel" in error_text.lower():
                return attempt_result

            retry_errors.append(error_text)
            is_last_profile = retry_index >= len(retry_profiles) - 1
            if is_last_profile or not self._is_transient_convergence_failure(error_text):
                if retry_index > 0:
                    attempt_result.statistics["convergence_retry_profile"] = profile.name
                    attempt_result.statistics["convergence_retries"] = retry_index
                return attempt_result

        if retry_errors:
            result.error_message = retry_errors[-1]
        return result

    def _run_transient_once(
        self,
        circuit: Any,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run one transient attempt with precomputed solver state."""
        result = BackendRunResult()
        node_names = list(circuit.node_names())
        result.time = []
        for name in node_names:
            result.signals[f"V({name})"] = []

        if hasattr(self._module, "run_transient_shared"):
            return self._run_transient_shared(
                circuit, settings, callbacks, result,
                node_names, dt, x0, newton_opts, linear_solver,
            )

        if hasattr(self._module, "run_transient_streaming"):
            streaming_result = self._run_transient_streaming(
                circuit, settings, callbacks, result,
                node_names, dt, x0, newton_opts, linear_solver,
            )
            if not streaming_result.error_message:
                return streaming_result
            if "cancel" in streaming_result.error_message.lower():
                return streaming_result
            if hasattr(self._module, "run_transient"):
                callbacks.progress(
                    5.0,
                    "Streaming transient failed; retrying in compatibility mode...",
                )
                fallback_result = self._run_transient_chunked(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    node_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                if not fallback_result.error_message:
                    fallback_result.statistics["fallback_mode"] = "chunked"
                    fallback_result.statistics["streaming_error"] = (
                        streaming_result.error_message
                    )
                    return fallback_result
                fallback_result.error_message = (
                    f"{streaming_result.error_message} | Fallback error: "
                    f"{fallback_result.error_message}"
                )
                return fallback_result
            return streaming_result

        return self._run_transient_chunked(
            circuit, settings, callbacks, result,
            node_names, dt, x0, newton_opts, linear_solver,
        )

    def _build_transient_retry_profiles(
        self,
        settings: "SimulationSettings",
    ) -> list[_TransientRetryProfile]:
        """Build progressive retry profiles for Newton convergence failures."""
        base_iterations = max(1, int(getattr(settings, "max_newton_iterations", 50)))
        configured_step = float(getattr(settings, "max_voltage_step", 5.0))
        safe_step = configured_step if configured_step > 0 else 5.0

        return [
            _TransientRetryProfile(name="default"),
            _TransientRetryProfile(
                name="gmin-seed",
                dc_strategy="gmin",
                min_newton_iterations=max(base_iterations, 100),
            ),
            _TransientRetryProfile(
                name="source-limited-half-step",
                dc_strategy="source",
                min_newton_iterations=max(base_iterations, 160),
                force_voltage_limiting=True,
                max_voltage_step=min(safe_step, 3.0),
                dt_scale=0.5,
            ),
            _TransientRetryProfile(
                name="pseudo-limited-quarter-step",
                dc_strategy="pseudo",
                min_newton_iterations=max(base_iterations, 220),
                force_voltage_limiting=True,
                max_voltage_step=min(safe_step, 2.0),
                dt_scale=0.25,
            ),
        ]

    def _apply_transient_retry_profile(
        self,
        settings: "SimulationSettings",
        profile: _TransientRetryProfile,
    ) -> "SimulationSettings":
        """Clone runtime settings and apply retry profile overrides."""
        try:
            attempt_settings = copy.deepcopy(settings)
        except Exception:
            attempt_settings = copy.copy(settings)

        if profile.dc_strategy is not None:
            attempt_settings.dc_strategy = profile.dc_strategy
        if profile.min_newton_iterations is not None:
            attempt_settings.max_newton_iterations = max(
                int(getattr(attempt_settings, "max_newton_iterations", 50)),
                profile.min_newton_iterations,
            )
        if profile.force_voltage_limiting is not None:
            attempt_settings.enable_voltage_limiting = profile.force_voltage_limiting
        if profile.max_voltage_step is not None:
            attempt_settings.max_voltage_step = profile.max_voltage_step

        return attempt_settings

    def _is_transient_convergence_failure(self, error_message: str) -> bool:
        """Return True if an error should trigger a convergence retry profile."""
        lowered = (error_message or "").lower()
        if "cancel" in lowered:
            return False

        indicators = (
            "newton",
            "diverg",
            "converg",
            "singular",
            "transient failed",
            "time step too small",
            "timestep too small",
        )
        return any(indicator in lowered for indicator in indicators)

    def _run_transient_streaming(
        self,
        circuit: Any,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        node_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run transient simulation using streaming API with real-time callbacks."""
        # Track last sent index for incremental updates
        last_sent_index = 0

        def data_callback(t: float, state_dict: dict) -> None:
            """Called by C++ backend for progress - we ignore the data here.

            The actual data comes from the final returned arrays which have
            full resolution. We just use this callback to trigger UI updates.
            """
            nonlocal last_sent_index
            # Just trigger a progress update - actual data comes at the end
            # Send a dummy point to trigger waveform update
            callbacks.data_point(t, state_dict)

        def progress_callback(percent: float, message: str) -> None:
            """Called by C++ backend for progress updates."""
            # Map backend progress (0-100) to our range (5-95)
            mapped_progress = 5.0 + (percent / 100.0) * 90.0
            callbacks.progress(mapped_progress, message)

        def cancel_check() -> bool:
            """Called by C++ backend to check cancellation."""
            return callbacks.check_cancelled()

        callbacks.progress(5.0, "Running simulation...")

        # Use fewer callbacks (50) to reduce GIL overhead
        # The returned data will have full resolution
        total_steps = int((settings.t_stop - settings.t_start) / dt)
        emit_interval = max(1, total_steps // 50)

        transient_args = self._compose_transient_args(
            circuit=circuit,
            settings=settings,
            dt=dt,
            x0=x0,
            newton_opts=newton_opts,
            linear_solver=linear_solver,
        )
        transient_args.extend([data_callback, progress_callback, cancel_check, emit_interval])
        times, states, success, message = self._module.run_transient_streaming(*transient_args)

        if not success:
            result.error_message = message
            return result

        # Build final result from complete simulation data
        for t, state in zip(times, states):
            result.time.append(float(t))
            for i, name in enumerate(node_names):
                result.signals[f"V({name})"].append(float(state[i]))

        callbacks.progress(95.0, "Finalizing results...")

        # Final data point
        if result.time:
            final_sample = {name: values[-1] for name, values in result.signals.items()}
            callbacks.data_point(result.time[-1], final_sample)

        callbacks.progress(100.0, "Simulation complete")
        return result

    def _run_transient_shared(
        self,
        circuit: Any,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        node_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run transient simulation using shared memory for zero-copy real-time display.

        This is the fastest method for real-time waveform display:
        - C++ writes directly to pre-allocated numpy arrays
        - Python polls the status buffer at 60 FPS
        - No GIL contention during simulation
        """
        callbacks.progress(5.0, "Preparing shared memory buffers...")

        # Calculate buffer size (add 20% margin for safety)
        total_steps = int((settings.t_stop - settings.t_start) / dt)
        buffer_size = int(total_steps * 1.2) + 100
        num_nodes = len(node_names)

        # Pre-allocate numpy arrays (shared memory buffers)
        time_buffer = np.zeros(buffer_size, dtype=np.float64)
        states_buffer = np.zeros((buffer_size, num_nodes), dtype=np.float64)
        status_buffer = np.zeros(3, dtype=np.int64)
        # status_buffer[0] = current_index (steps completed)
        # status_buffer[1] = status (0=running, 1=completed, 2=error, 3=cancelled)
        # status_buffer[2] = error_code

        # Get initial state
        if x0 is None:
            x0 = np.zeros(num_nodes)

        # Variables for the simulation thread
        sim_success = [True]
        sim_message = [""]

        def run_simulation() -> None:
            """Run simulation in background thread."""
            try:
                transient_args = self._compose_transient_args(
                    circuit=circuit,
                    settings=settings,
                    dt=dt,
                    x0=x0,
                    newton_opts=newton_opts,
                    linear_solver=linear_solver,
                )
                transient_args.extend(
                    [
                        time_buffer,
                        states_buffer,
                        status_buffer,
                        callbacks.check_cancelled,
                        1000,  # Check cancellation every 1000 steps
                    ]
                )
                success, message = self._module.run_transient_shared(*transient_args)
                sim_success[0] = success
                sim_message[0] = message
            except Exception as exc:
                sim_success[0] = False
                sim_message[0] = str(exc)
                status_buffer[1] = 2  # error

        # Start simulation in background thread
        callbacks.progress(10.0, "Starting simulation...")
        sim_thread = threading.Thread(target=run_simulation, daemon=True)
        sim_thread.start()

        # Poll status buffer at 60 FPS and update UI
        poll_interval = 1.0 / 60.0  # 16.67ms
        last_index = 0

        while status_buffer[1] == 0:  # While running
            # Check for pause
            callbacks.wait_if_paused()

            # Get current progress
            current_index = int(status_buffer[0])

            if current_index > last_index:
                # Calculate progress percentage
                progress = 10.0 + (current_index / total_steps) * 85.0
                progress = min(95.0, progress)

                # Get current time value for message
                if current_index > 0 and current_index < buffer_size:
                    current_time = time_buffer[current_index - 1]
                    callbacks.progress(progress, f"Simulating: t={current_time*1e6:.1f}µs")

                # Send numpy array views directly to UI (zero-copy!)
                # Using _np suffix to indicate numpy arrays
                streaming_data = {
                    "_time_np": time_buffer[:current_index],
                    "_signals_np": {
                        f"V({name})": states_buffer[:current_index, i]
                        for i, name in enumerate(node_names)
                    },
                    "_current_index": current_index,
                }
                last_sample = {
                    f"V({name})": float(states_buffer[current_index - 1, i])
                    for i, name in enumerate(node_names)
                }
                last_sample["_full_data"] = streaming_data
                callbacks.data_point(float(time_buffer[current_index - 1]), last_sample)

                last_index = current_index

            time.sleep(poll_interval)

        # Wait for simulation thread to finish
        sim_thread.join(timeout=5.0)

        # Check final status
        final_status = int(status_buffer[1])
        final_index = int(status_buffer[0])

        if final_status == 3:  # Cancelled
            result.error_message = "Simulation cancelled"
            return result

        if final_status == 2 or not sim_success[0]:  # Error
            result.error_message = sim_message[0] or "Simulation failed"
            return result

        callbacks.progress(95.0, "Finalizing results...")

        # Copy final data to result (full resolution)
        result.time = time_buffer[:final_index].tolist()
        for i, name in enumerate(node_names):
            result.signals[f"V({name})"] = states_buffer[:final_index, i].tolist()

        # Send final complete data
        if result.time:
            final_sample = {name: values[-1] for name, values in result.signals.items()}
            callbacks.data_point(result.time[-1], final_sample)

        callbacks.progress(100.0, "Simulation complete")
        return result

    def _run_transient_chunked(
        self,
        circuit: Any,
        settings: "SimulationSettings",
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        node_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Optimized chunked simulation - run full sim then send data for animation."""
        # Signal that we're starting (progress=-1 means indeterminate mode)
        callbacks.progress(-1.0, "Simulating circuit...")

        transient_args = self._compose_transient_args(
            circuit=circuit,
            settings=settings,
            dt=dt,
            x0=x0,
            newton_opts=newton_opts,
            linear_solver=linear_solver,
        )
        times, states, success, message = self._module.run_transient(*transient_args)

        if not success:
            result.error_message = message
            return result

        callbacks.progress(60.0, "Processing results...")

        # Convert to numpy arrays for efficient transfer
        total_points = len(times)
        time_array = np.array([float(t) for t in times], dtype=np.float64)

        callbacks.progress(70.0, f"Converting {total_points:,} data points...")

        signal_arrays = {}
        for i, name in enumerate(node_names):
            signal_arrays[f"V({name})"] = np.array(
                [float(state[i]) for state in states if i < len(state)],
                dtype=np.float64
            )

        callbacks.progress(80.0, "Preparing waveform display...")

        # Store in result for final return
        result.time = time_array.tolist()
        result.signals = {name: arr.tolist() for name, arr in signal_arrays.items()}

        callbacks.progress(90.0, "Starting animation...")

        # Send complete data with animation flag - viewer will animate it
        callbacks.data_point(float(time_array[-1]) if len(time_array) > 0 else 0, {
            "_animate": True,  # Tell viewer to animate the display
            "_time_array": time_array,
            "_signal_arrays": signal_arrays,
            "_total_points": total_points,
        })

        callbacks.progress(100.0, "Complete")
        return result

    def run_dc(
        self,
        circuit_data: dict,
        settings: DCSettings,
    ) -> DCResult:
        """Run DC operating point analysis using PulsimCore solver."""
        if not self.has_capability("dc"):
            return DCResult(
                error_message="DC analysis not supported by this backend version",
                convergence_info=ConvergenceInfo(converged=False, failure_reason="Not supported"),
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            return DCResult(
                error_message=str(exc),
                convergence_info=ConvergenceInfo(converged=False, failure_reason=str(exc)),
            )

        try:
            # Try top-level dc_operating_point first (preferred)
            if hasattr(self._module, "dc_operating_point"):
                return self._run_dc_top_level(circuit, settings)

            # Try top-level solve_dc
            if hasattr(self._module, "solve_dc"):
                newton_opts = self._build_dc_options(settings)
                native_result = self._module.solve_dc(circuit, newton_opts)
                return self._convert_newton_result(native_result, circuit)

            # Try v1 namespace (DCConvergenceSolver)
            if hasattr(self._module, "v1") and hasattr(self._module.v1, "DCConvergenceSolver"):
                newton_opts = self._build_dc_options(settings)
                return self._run_dc_v1(circuit, settings, newton_opts)

            # Try v2 namespace
            if hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
                newton_opts = self._build_dc_options(settings)
                native_result = self._module.v2.solve_dc(circuit, newton_opts)
                return self._convert_newton_result(native_result, circuit)

            return DCResult(
                error_message="No DC solver available in backend",
                convergence_info=ConvergenceInfo(converged=False, failure_reason="No solver"),
            )

        except Exception as exc:
            return DCResult(
                error_message=str(exc),
                convergence_info=ConvergenceInfo(converged=False, failure_reason=str(exc)),
            )

    def _run_dc_top_level(self, circuit: Any, settings: DCSettings) -> DCResult:
        """Run DC analysis using top-level dc_operating_point function."""
        # Build DCConvergenceConfig
        config = self._module.DCConvergenceConfig()

        # Map strategy
        if settings.strategy == "gmin":
            if hasattr(self._module, "DCStrategy"):
                config.strategy = self._module.DCStrategy.GminStepping
        elif settings.strategy == "source":
            if hasattr(self._module, "DCStrategy"):
                config.strategy = self._module.DCStrategy.SourceStepping
                if hasattr(config, "source_config"):
                    config.source_config.max_steps = settings.source_steps
        elif settings.strategy == "pseudo":
            if hasattr(self._module, "DCStrategy"):
                config.strategy = self._module.DCStrategy.PseudoTransient
        if settings.strategy == "gmin" and hasattr(config, "gmin_config"):
            config.gmin_config.initial_gmin = settings.gmin_initial
            config.gmin_config.final_gmin = settings.gmin_final

        # Run DC analysis
        dc_result = self._module.dc_operating_point(circuit, config)

        # Convert to DCResult
        return self._convert_dc_analysis_result(dc_result, circuit)

    def _run_dc_v1(self, circuit: Any, settings: DCSettings, newton_opts: Any) -> DCResult:
        """Run DC analysis using v1 DCConvergenceSolver."""
        v1 = self._module.v1

        # Map strategy string to enum if available
        strategy = self._map_dc_strategy(settings.strategy)

        # Create DC convergence solver
        solver = v1.DCConvergenceSolver(circuit, newton_opts)

        # Run analysis with appropriate strategy
        if settings.strategy == "gmin" and hasattr(solver, "solve_with_gmin"):
            native_result = solver.solve_with_gmin(settings.gmin_initial, settings.gmin_final)
        elif settings.strategy == "source" and hasattr(solver, "solve_with_source_stepping"):
            native_result = solver.solve_with_source_stepping(settings.source_steps)
        elif settings.strategy == "pseudo" and hasattr(solver, "solve_with_pseudo_transient"):
            native_result = solver.solve_with_pseudo_transient()
        else:
            # Auto or direct strategy
            native_result = solver.solve()

        return self._convert_dc_result(native_result, circuit)

    def _build_dc_options(self, settings: DCSettings) -> Any:
        """Build PulsimCore Newton options from DCSettings."""
        # Try top-level NewtonOptions first
        if hasattr(self._module, "NewtonOptions"):
            opts = self._module.NewtonOptions()
        elif hasattr(self._module, "v1") and hasattr(self._module.v1, "NewtonOptions"):
            opts = self._module.v1.NewtonOptions()
        elif hasattr(self._module, "v2") and hasattr(self._module.v2, "NewtonOptions"):
            opts = self._module.v2.NewtonOptions()
        else:
            # Fallback to generic options
            opts = type("NewtonOptions", (), {})()

        if hasattr(opts, "max_iterations"):
            opts.max_iterations = settings.max_iterations
        if hasattr(opts, "tolerance"):
            opts.tolerance = settings.tolerance
        if hasattr(opts, "enable_limiting"):
            opts.enable_limiting = settings.enable_limiting
        if hasattr(opts, "max_voltage_step"):
            opts.max_voltage_step = settings.max_voltage_step

        return opts

    def _convert_dc_analysis_result(self, dc_result: Any, circuit: Any) -> DCResult:
        """Convert PulsimCore DCAnalysisResult to GUI DCResult."""
        node_voltages: dict[str, float] = {}
        branch_currents: dict[str, float] = {}
        power_dissipation: dict[str, float] = {}

        # Extract solution from newton_result
        newton_result = getattr(dc_result, "newton_result", None)
        solution = getattr(newton_result, "solution", None) if newton_result else None

        if solution is not None:
            node_names = list(circuit.node_names()) if hasattr(circuit, "node_names") else []
            for i, name in enumerate(node_names):
                if i < len(solution):
                    node_voltages[f"V({name})"] = float(solution[i])

        # Build convergence info from DCAnalysisResult
        converged = getattr(dc_result, "success", False)
        iterations = 0
        final_residual = 0.0
        strategy_used = "auto"

        if newton_result:
            iterations = getattr(newton_result, "iterations", 0)
            final_residual = getattr(newton_result, "final_residual", 0.0)

        # Extract history if available (handles pulsim.v2.ConvergenceHistory)
        history: list[IterationRecord] = []
        if newton_result and hasattr(newton_result, "history"):
            for i, record in enumerate(newton_result.history):
                history.append(IterationRecord(
                    iteration=getattr(record, "iteration", i),
                    residual_norm=getattr(record, "residual_norm", 0.0),
                    voltage_error=getattr(record, "max_voltage_error", getattr(record, "voltage_error", 0.0)),
                    current_error=getattr(record, "max_current_error", getattr(record, "current_error", 0.0)),
                    damping_factor=getattr(record, "damping", getattr(record, "damping_factor", 1.0)),
                    step_norm=getattr(record, "step_norm", 0.0),
                ))

        # Extract problematic variables (handles pulsim.v2.PerVariableConvergence)
        problematic_variables: list[ProblematicVariable] = []
        problematic_nodes = getattr(newton_result, "problematic_nodes", None) if newton_result else None
        if problematic_nodes is None:
            problematic_nodes = getattr(dc_result, "problematic_variables", [])
        for node in problematic_nodes:
            # Map index to node name if name not provided
            index = getattr(node, "index", 0)
            name = getattr(node, "name", None)
            if name is None and node_names and index < len(node_names):
                name = f"V({node_names[index]})"
            elif name is None:
                name = f"node_{index}"
            problematic_variables.append(ProblematicVariable(
                index=index,
                name=name,
                value=getattr(node, "value", 0.0),
                change=getattr(node, "change", 0.0),
                tolerance=getattr(node, "tolerance", 1e-9),
                normalized_error=getattr(node, "normalized_error", 0.0),
                is_voltage=getattr(node, "is_voltage", True),
            ))

        failure_reason = ""
        error_message = ""
        if not converged:
            failure_reason = getattr(dc_result, "message", "DC analysis failed")
            error_message = failure_reason

        convergence_info = ConvergenceInfo(
            converged=converged,
            iterations=iterations,
            final_residual=final_residual,
            strategy_used=strategy_used,
            history=history,
            problematic_variables=problematic_variables,
            failure_reason=failure_reason,
        )

        return DCResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            power_dissipation=power_dissipation,
            convergence_info=convergence_info,
            error_message=error_message,
        )

    def _convert_newton_result(self, native_result: Any, circuit: Any) -> DCResult:
        """Convert PulsimCore NewtonResult to GUI DCResult."""
        return self._convert_dc_result(native_result, circuit)

    def _map_dc_strategy(self, strategy: str) -> Any:
        """Map strategy string to PulsimCore enum."""
        if hasattr(self._module, "v1") and hasattr(self._module.v1, "DCStrategy"):
            strategy_map = {
                "auto": self._module.v1.DCStrategy.Auto,
                "direct": self._module.v1.DCStrategy.Direct,
                "gmin": self._module.v1.DCStrategy.GminStepping,
                "source": self._module.v1.DCStrategy.SourceStepping,
                "pseudo": self._module.v1.DCStrategy.PseudoTransient,
            }
            return strategy_map.get(strategy.lower(), self._module.v1.DCStrategy.Auto)
        return strategy

    def _convert_dc_result(self, native_result: Any, circuit: Any) -> DCResult:
        """Convert PulsimCore DC result to GUI DCResult."""
        node_voltages: dict[str, float] = {}
        branch_currents: dict[str, float] = {}
        power_dissipation: dict[str, float] = {}

        # Extract solution vector
        solution = getattr(native_result, "solution", None)
        if solution is not None:
            # Map node indices to names
            node_names = []
            if hasattr(circuit, "node_names"):
                node_names = list(circuit.node_names())
            elif hasattr(circuit, "get_node_names"):
                node_names = list(circuit.get_node_names())

            for i, name in enumerate(node_names):
                if i < len(solution):
                    node_voltages[f"V({name})"] = float(solution[i])

        # Extract branch currents if available
        if hasattr(native_result, "branch_currents"):
            for name, current in native_result.branch_currents.items():
                branch_currents[f"I({name})"] = float(current)

        # Build convergence info with circuit for node name mapping
        convergence_info = self._build_convergence_info(native_result, circuit)

        # Determine error message
        error_message = ""
        if not convergence_info.converged:
            error_message = getattr(
                native_result,
                "error_message",
                convergence_info.failure_reason or "DC analysis failed to converge",
            )

        return DCResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            power_dissipation=power_dissipation,
            convergence_info=convergence_info,
            error_message=error_message,
        )

    def _build_convergence_info(self, native_result: Any, circuit: Any = None) -> ConvergenceInfo:
        """Build ConvergenceInfo from native result.

        Args:
            native_result: Native backend result object with convergence data.
            circuit: Optional circuit for mapping node indices to names.

        Returns:
            ConvergenceInfo with extracted diagnostics.
        """
        converged = getattr(native_result, "converged", False)
        if not converged and hasattr(native_result, "success"):
            converged = native_result.success()

        iterations = getattr(native_result, "iterations", 0)
        final_residual = getattr(native_result, "final_residual", 0.0)
        strategy_used = getattr(native_result, "strategy_used", "newton")

        # Extract iteration history if available (handles pulsim.v2.ConvergenceHistory)
        history: list[IterationRecord] = []
        if hasattr(native_result, "history"):
            for i, record in enumerate(native_result.history):
                history.append(IterationRecord(
                    iteration=getattr(record, "iteration", i),
                    residual_norm=getattr(record, "residual_norm", 0.0),
                    voltage_error=getattr(record, "voltage_error", getattr(record, "max_voltage_error", 0.0)),
                    current_error=getattr(record, "current_error", getattr(record, "max_current_error", 0.0)),
                    damping_factor=getattr(record, "damping_factor", getattr(record, "damping", 1.0)),
                    step_norm=getattr(record, "step_norm", 0.0),
                ))

        # Get node names for index mapping
        node_names: list[str] = []
        if circuit is not None:
            if hasattr(circuit, "node_names"):
                node_names = list(circuit.node_names())
            elif hasattr(circuit, "get_node_names"):
                node_names = list(circuit.get_node_names())

        # Extract problematic variables (handles pulsim.v2.PerVariableConvergence)
        problematic_variables: list[ProblematicVariable] = []
        # Try different attribute names for compatibility
        problematic_nodes = getattr(native_result, "problematic_nodes", None)
        if problematic_nodes is None:
            problematic_nodes = getattr(native_result, "problematic_variables", [])
        for node in problematic_nodes:
            # Map index to node name if name not provided
            index = getattr(node, "index", 0)
            name = getattr(node, "name", None)
            if name is None and node_names and index < len(node_names):
                name = f"V({node_names[index]})"
            elif name is None:
                name = f"node_{index}"
            problematic_variables.append(ProblematicVariable(
                index=index,
                name=name,
                value=getattr(node, "value", 0.0),
                change=getattr(node, "change", 0.0),
                tolerance=getattr(node, "tolerance", 1e-9),
                normalized_error=getattr(node, "normalized_error", 0.0),
                is_voltage=getattr(node, "is_voltage", True),
            ))

        # Sort problematic variables by worst convergence
        problematic_variables.sort(key=lambda v: v.normalized_error, reverse=True)

        failure_reason = ""
        if not converged:
            failure_reason = getattr(native_result, "failure_reason", "")
            if not failure_reason:
                failure_reason = getattr(native_result, "error_message", "Convergence failed")

        return ConvergenceInfo(
            converged=converged,
            iterations=iterations,
            final_residual=final_residual,
            strategy_used=str(strategy_used),
            history=history,
            problematic_variables=problematic_variables,
            failure_reason=failure_reason,
        )

    def run_ac(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> ACResult:
        """Run AC frequency-domain analysis using PulsimCore."""
        if not self.has_capability("ac"):
            return ACResult(
                error_message="AC analysis not supported by this backend version",
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            return ACResult(error_message=str(exc))

        try:
            # Build AC options
            ac_opts = self._build_ac_options(settings)

            # Try different AC analysis APIs
            if hasattr(self._module, "run_ac"):
                native_result = self._module.run_ac(circuit, ac_opts)
            elif hasattr(self._module, "ACAnalysis"):
                analyzer = self._module.ACAnalysis(circuit)
                native_result = analyzer.run(ac_opts)
            else:
                return ACResult(error_message="No AC analysis API available")

            return self._convert_ac_result(native_result, settings)

        except Exception as exc:
            return ACResult(error_message=str(exc))

    def _build_ac_options(self, settings: ACSettings) -> Any:
        """Build PulsimCore AC options from ACSettings."""
        if hasattr(self._module, "ACOptions"):
            opts = self._module.ACOptions()
        else:
            opts = type("ACOptions", (), {})()

        # New bindings use fstart, fstop, npoints (not f_start, f_stop, points_per_decade)
        if hasattr(opts, "fstart"):
            opts.fstart = settings.f_start
        elif hasattr(opts, "f_start"):
            opts.f_start = settings.f_start

        if hasattr(opts, "fstop"):
            opts.fstop = settings.f_stop
        elif hasattr(opts, "f_stop"):
            opts.f_stop = settings.f_stop

        if hasattr(opts, "npoints"):
            # Calculate total points based on points_per_decade
            decades = math.log10(settings.f_stop / max(settings.f_start, 0.001))
            opts.npoints = max(1, int(decades * settings.points_per_decade))
        elif hasattr(opts, "points_per_decade"):
            opts.points_per_decade = settings.points_per_decade

        # Set sweep type to Decade if available
        if hasattr(opts, "sweep_type") and hasattr(self._module, "FrequencySweepType"):
            opts.sweep_type = self._module.FrequencySweepType.Decade

        if hasattr(opts, "input_source"):
            opts.input_source = settings.input_source

        return opts

    def _convert_ac_result(self, native_result: Any, settings: ACSettings) -> ACResult:
        """Convert PulsimCore AC result to GUI ACResult."""
        frequencies = list(getattr(native_result, "frequencies", []))
        magnitude: dict[str, list[float]] = {}
        phase: dict[str, list[float]] = {}

        # New bindings have signal_names and use accessor methods
        signal_names = list(getattr(native_result, "signal_names", []))

        if signal_names and hasattr(native_result, "magnitude_db"):
            # New-style ACResult with accessor methods
            num_freqs = native_result.num_frequencies()
            for j, name in enumerate(signal_names):
                mag_values = []
                phase_values = []
                for i in range(num_freqs):
                    mag_values.append(native_result.magnitude_db(i, j))
                    phase_values.append(native_result.phase_deg(i, j))
                magnitude[name] = mag_values
                phase[name] = phase_values
        else:
            # Old-style with dict attributes (not methods)
            mag_attr = getattr(native_result, "magnitude", None)
            if mag_attr is not None and not callable(mag_attr):
                for name, values in mag_attr.items():
                    magnitude[name] = list(values)
            phase_attr = getattr(native_result, "phase", None)
            if phase_attr is not None and not callable(phase_attr):
                for name, values in phase_attr.items():
                    phase[name] = list(values)

        # Check error status
        error_message = ""
        if hasattr(native_result, "status"):
            status = native_result.status
            status_name = str(status).split(".")[-1] if hasattr(status, "name") else str(status)
            if "Success" not in status_name:
                error_message = getattr(native_result, "error_message", f"AC analysis failed: {status_name}")

        return ACResult(
            frequencies=frequencies,
            magnitude=magnitude,
            phase=phase,
            error_message=error_message,
        )

    def run_thermal(
        self,
        circuit_data: dict,
        electrical_result: TransientResult,
        settings: ThermalSettings,
    ) -> ThermalResult:
        """Run thermal simulation using PulsimCore ThermalSimulator."""
        if not self.has_capability("thermal"):
            return ThermalResult(
                error_message="Thermal simulation not supported by this backend version",
                is_synthetic=True,
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            return ThermalResult(error_message=str(exc), is_synthetic=True)

        try:
            # Create thermal simulator
            thermal_sim = self._module.ThermalSimulator(circuit)

            # Configure settings
            if hasattr(thermal_sim, "set_ambient_temperature"):
                thermal_sim.set_ambient_temperature(settings.ambient_temperature)
            if hasattr(thermal_sim, "include_switching_losses"):
                thermal_sim.include_switching_losses = settings.include_switching_losses
            if hasattr(thermal_sim, "include_conduction_losses"):
                thermal_sim.include_conduction_losses = settings.include_conduction_losses

            # Run thermal analysis with electrical results
            native_result = thermal_sim.run(electrical_result.time, electrical_result.signals)

            return self._convert_thermal_result(native_result, settings)

        except Exception as exc:
            return ThermalResult(error_message=str(exc), is_synthetic=True)

    def _convert_thermal_result(self, native_result: Any, settings: ThermalSettings) -> ThermalResult:
        """Convert PulsimCore thermal result to GUI ThermalResult."""
        time = list(getattr(native_result, "time", []))
        devices: list[ThermalDeviceResult] = []

        if hasattr(native_result, "devices"):
            for dev in native_result.devices:
                # Extract Foster stages
                foster_stages: list[FosterStage] = []
                if hasattr(dev, "foster_network"):
                    for stage in dev.foster_network:
                        foster_stages.append(FosterStage(
                            resistance=getattr(stage, "r", 0.0),
                            capacitance=getattr(stage, "c", 0.0),
                        ))

                # Extract losses
                losses = LossBreakdown()
                if hasattr(dev, "losses"):
                    loss_data = dev.losses
                    losses = LossBreakdown(
                        conduction=getattr(loss_data, "conduction", 0.0),
                        switching_on=getattr(loss_data, "switching_on", 0.0),
                        switching_off=getattr(loss_data, "switching_off", 0.0),
                        reverse_recovery=getattr(loss_data, "reverse_recovery", 0.0),
                    )

                junction_temp = list(getattr(dev, "junction_temperature", []))
                devices.append(ThermalDeviceResult(
                    name=getattr(dev, "name", "unknown"),
                    junction_temperature=junction_temp,
                    peak_temperature=max(junction_temp) if junction_temp else settings.ambient_temperature,
                    steady_state_temperature=junction_temp[-1] if junction_temp else settings.ambient_temperature,
                    losses=losses,
                    foster_stages=foster_stages,
                    thermal_limit=getattr(dev, "thermal_limit", None),
                ))

        return ThermalResult(
            time=time,
            devices=devices,
            ambient_temperature=settings.ambient_temperature,
            is_synthetic=False,
        )

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

    def _compute_time_step(self, settings: "SimulationSettings") -> float:
        duration = settings.t_stop - settings.t_start
        if duration <= 0:
            raise ValueError("Simulation stop time must be greater than start time.")

        if settings.t_step > 0:
            dt = settings.t_step
        else:
            points = max(settings.output_points, 1)
            dt = duration / points

        if settings.max_step > 0:
            dt = min(dt, settings.max_step)

        if dt <= 0:
            raise ValueError("Simulation timestep must be greater than zero.")
        return dt

    def _compose_transient_args(
        self,
        *,
        circuit: Any,
        settings: "SimulationSettings",
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> list[Any]:
        """Compose positional args for transient API across Pulsim versions."""
        args: list[Any] = [circuit, settings.t_start, settings.t_stop, dt]
        if x0 is not None:
            args.append(x0)
        args.append(newton_opts)
        if linear_solver is not None:
            args.append(linear_solver)
        return args

    def _build_newton_options(self, settings: "SimulationSettings", circuit: Any) -> Any:
        """Build NewtonOptions for the new kernel API."""
        if hasattr(self._module, "NewtonOptions"):
            opts = self._module.NewtonOptions()
        else:  # pragma: no cover - defensive fallback for older adapters
            opts = type("NewtonOptions", (), {})()
        opts.max_iterations = settings.max_newton_iterations
        opts.enable_limiting = settings.enable_voltage_limiting
        opts.max_voltage_step = settings.max_voltage_step

        if hasattr(self._module, "Tolerances"):
            tolerances = self._module.Tolerances.defaults()
            tolerances.voltage_abstol = settings.abs_tol
            tolerances.voltage_reltol = settings.rel_tol
            tolerances.current_abstol = settings.abs_tol
            tolerances.current_reltol = settings.rel_tol
            opts.tolerances = tolerances

        if hasattr(circuit, "num_nodes"):
            opts.num_nodes = circuit.num_nodes()
        if hasattr(circuit, "num_branches"):
            opts.num_branches = circuit.num_branches()

        return opts

    def _build_linear_solver_config(self) -> Any | None:
        """Build optional linear-solver configuration when API supports it."""
        stack_cls = getattr(self._module, "LinearSolverStackConfig", None)
        if stack_cls is None:
            return None

        config = stack_cls.defaults() if hasattr(stack_cls, "defaults") else stack_cls()

        linear_solver_kind = getattr(self._module, "LinearSolverKind", None)
        if linear_solver_kind is not None and hasattr(config, "order"):
            preferred_order: list[Any] = []
            for name in ("KLU", "GMRES"):
                if hasattr(linear_solver_kind, name):
                    preferred_order.append(getattr(linear_solver_kind, name))
            if preferred_order:
                config.order = preferred_order

        if hasattr(config, "allow_fallback"):
            config.allow_fallback = True
        if hasattr(config, "auto_select"):
            config.auto_select = True
        return config

    def _build_initial_state(self, circuit: Any, settings: "SimulationSettings") -> Any:
        """Compute initial state, preferring DC operating point when available."""
        if hasattr(self._module, "dc_operating_point"):
            try:
                config = self._module.DCConvergenceConfig()
                if settings.dc_strategy == "gmin" and hasattr(self._module, "DCStrategy"):
                    config.strategy = self._module.DCStrategy.GminStepping
                    config.gmin_config.initial_gmin = settings.gmin_initial
                    config.gmin_config.final_gmin = settings.gmin_final
                elif settings.dc_strategy == "source" and hasattr(self._module, "DCStrategy"):
                    config.strategy = self._module.DCStrategy.SourceStepping
                    config.source_config.max_steps = 10
                elif settings.dc_strategy == "pseudo" and hasattr(self._module, "DCStrategy"):
                    config.strategy = self._module.DCStrategy.PseudoTransient
                dc_result = self._module.dc_operating_point(circuit, config)
                if getattr(dc_result, "success", False):
                    newton_result = getattr(dc_result, "newton_result", None)
                    if newton_result is not None:
                        return newton_result.solution
            except Exception:
                pass

        if hasattr(circuit, "initial_state"):
            return circuit.initial_state()
        return None


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
            capabilities={"transient", "dc", "ac", "thermal"},
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

        # Check for DC analysis capability (multiple possible APIs)
        if hasattr(module, "dc_operating_point") or hasattr(module, "solve_dc"):
            capabilities.add("dc")
        elif hasattr(module, "v2") and hasattr(module.v2, "solve_dc"):
            capabilities.add("dc")
        elif hasattr(module, "v1") and hasattr(module.v1, "DCConvergenceSolver"):
            capabilities.add("dc")

        # Check for AC analysis capability
        if hasattr(module, "run_ac") or hasattr(module, "ACAnalysis"):
            capabilities.add("ac")

        # Check for thermal simulation capability
        if hasattr(module, "ThermalSimulator"):
            capabilities.add("thermal")

        # Parse version for compatibility checking
        parsed_version = None
        try:
            parsed_version = BackendVersion.from_string(version)
        except ValueError:
            pass  # Will be handled in check_compatibility

        info = BackendInfo(
            identifier="pulsim",
            name="Pulsim",
            version=version,
            status="available",
            location=location,
            capabilities=capabilities,
            message="Using native Pulsim backend",
            parsed_version=parsed_version,
        )

        # Check version compatibility
        info.check_compatibility()

        # Update message if there's a compatibility warning
        if info.compatibility_warning:
            info.message = info.compatibility_warning

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
        elif hasattr(entry_points, "get"):  # pragma: no cover - legacy importlib.metadata API
            entries = entry_points.get("pulsimgui.backends", [])  # type: ignore[attr-defined]
        else:  # pragma: no cover - mock or unexpected return type
            return []

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
    # Re-export types from backend_types for convenience
    "ACResult",
    "ACSettings",
    "DCResult",
    "DCSettings",
    "ThermalResult",
    "ThermalSettings",
    "TransientResult",
    "TransientSettings",
    "ConvergenceInfo",
    "BackendVersion",
]
