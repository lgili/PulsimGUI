"""Backend discovery and placeholder adapter for simulations."""

from __future__ import annotations

import copy
import logging
import math
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module, metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from pulsimgui.services.simulation_service import SimulationSettings

from pulsimgui.services.backend_types import (
    MIN_BACKEND_API,
    ACResult,
    ACSettings,
    BackendVersion,
    C99CodegenResult,
    C99CodegenSettings,
    ConvergenceInfo,
    DCResult,
    DCSettings,
    FmuExportResult,
    FmuExportSettings,
    FosterStage,
    FraResult,
    FraResultEntry,
    FraSettings,
    FrequencyAnalysisResult,
    HarmonicBalanceResult,
    HarmonicBalanceSettings,
    HarmonicEntry,
    IterationRecord,
    LossBreakdown,
    PeriodicSteadyStateResult,
    PeriodicSteadyStateSettings,
    PostProcessingJobResult,
    PostProcessingResult,
    ProblematicVariable,
    ScalarMetric,
    SpectralBin,
    ThermalDeviceResult,
    ThermalResult,
    ThermalSettings,
    TransientResult,
    TransientSettings,
    UndefinedMetricEntry,
)
from pulsimgui.models.component import derive_control_schedule_from_serialized_components
from pulsimgui.services.circuit_converter import CircuitConversionError, CircuitConverter

log = logging.getLogger(__name__)

_SIMULATION_OPTIONS_MIN_BACKEND = BackendVersion(0, 7, 0, api_version=1)
_CBLOCK_MODERN_TRANSIENT_MIN_BACKEND = BackendVersion(0, 7, 7, api_version=1)
_PROBE_COMPONENT_TYPES = frozenset({"voltage_probe", "current_probe", "power_probe"})


def _optional_float(value: Any) -> float | None:
    """Convert a value to float, returning None if it is None or not numeric."""
    if value is None:
        return None
    try:
        numeric = float(value)
        if not math.isfinite(numeric):
            return None
        return numeric
    except (TypeError, ValueError):
        return None


def _enum_name_or_value(value: Any) -> str:
    """Return a stable string from either plain values or Enum-like objects."""
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    if enum_value is not None and not isinstance(enum_value, type):
        return str(enum_value)
    enum_name = getattr(value, "name", None)
    if enum_name is not None:
        return str(enum_name)
    return str(value)


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
        all_features = {"dc", "ac", "thermal", "transient", "post_processing", "frequency_analysis", "averaged"}
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
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        """Run transient simulation and return the backend result payload."""
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
        """Request backend pause for the active simulation execution."""
        ...

    def request_resume(self, run_id: int | None = None) -> None:
        """Request backend resume for the active simulation execution."""
        ...

    def request_stop(self, run_id: int | None = None) -> None:
        """Request backend stop for the active simulation execution."""
        ...

    def run_post_processing(
        self,
        transient_result: TransientResult,
        jobs: list[dict],
    ) -> PostProcessingResult:
        """Run post-processing jobs on a transient result.

        Args:
            transient_result: Completed transient simulation result.
            jobs: List of job specification dicts (job_id, kind, signals, ...).

        Returns:
            PostProcessingResult with per-job results.
        """
        ...

    def run_frequency_analysis(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> FrequencyAnalysisResult:
        """Run frequency-domain (Bode sweep) analysis.

        Args:
            circuit_data: Serialised circuit definition.
            settings: AC/frequency analysis settings.

        Returns:
            FrequencyAnalysisResult with Bode data and stability margins.
        """
        ...

    def export_fmu(
        self,
        circuit_data: dict,
        settings: FmuExportSettings,
    ) -> FmuExportResult:
        """Export the current circuit as a FMI 2.0 co-simulation FMU.

        Args:
            circuit_data: Serialised circuit definition (same shape as the
                one used for ``run_transient``).
            settings: FMU export configuration.

        Returns:
            FmuExportResult describing the produced ``.fmu`` archive.

        Raises:
            NotImplementedError: backend does not support FMU export.
        """
        ...

    def export_c99(
        self,
        circuit_data: dict,
        settings: C99CodegenSettings,
    ) -> C99CodegenResult:
        """Generate deployable C99 controller code from the active circuit."""
        ...

    def run_fra(
        self,
        circuit_data: dict,
        settings: FraSettings,
    ) -> FraResult:
        """Run closed-loop Frequency Response Analysis (wave-4 sub-B 2.1)."""
        ...

    def run_periodic_steady_state(
        self,
        circuit_data: dict,
        settings: PeriodicSteadyStateSettings,
    ) -> PeriodicSteadyStateResult:
        """Solve for the periodic orbit via shooting (wave-4 sub-B 2.2)."""
        ...

    def run_harmonic_balance(
        self,
        circuit_data: dict,
        settings: HarmonicBalanceSettings,
    ) -> HarmonicBalanceResult:
        """Solve for the spectrum via harmonic balance (wave-4 sub-B 2.3)."""
        ...


class PlaceholderBackend(SimulationBackend):
    """Fallback backend that generates synthetic data for demo mode."""

    def __init__(self, info: BackendInfo | None = None) -> None:
        self.info = info or BackendInfo(
            identifier="placeholder",
            name="Demo backend",
            version="0.0",
            status="placeholder",
            capabilities={"transient", "dc", "ac", "thermal", "post_processing", "frequency_analysis", "averaged"},
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
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        """Run transient simulation and return the backend result payload."""
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
            "P(R1)": 0.025,
            "P(M1)": 3.5,
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
        for _i, t in enumerate(time):
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
        for _i, t in enumerate(time):
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

    def run_post_processing(
        self,
        transient_result: TransientResult,
        jobs: list[dict],
    ) -> PostProcessingResult:
        """Return synthetic post-processing results for demo mode."""
        import math

        job_results: list[PostProcessingJobResult] = []
        for job in jobs:
            kind = job.get("kind", "time_domain")
            job_id = job.get("job_id", "demo_job")
            signals = job.get("signals", list(transient_result.signals.keys())[:1])

            if kind == "spectral":
                fundamental = job.get("fundamental_hz", 1000.0)
                bins = [
                    SpectralBin(frequency_hz=fundamental * i, amplitude=1.0 / i, phase_deg=0.0)
                    for i in range(1, 6)
                ]
                harmonics = [
                    HarmonicEntry(
                        order=i,
                        frequency_hz=fundamental * i,
                        amplitude=1.0 / i,
                        amplitude_db=-20 * math.log10(i),
                    )
                    for i in range(1, 4)
                ]
                job_results.append(PostProcessingJobResult(
                    job_id=job_id,
                    kind=kind,
                    success=True,
                    spectrum_bins=bins,
                    harmonics=harmonics,
                    thd_pct=5.0,
                    fundamental_hz=fundamental,
                    signal_names=signals,
                ))
            elif kind == "power_efficiency":
                job_results.append(PostProcessingJobResult(
                    job_id=job_id,
                    kind=kind,
                    success=True,
                    average_input_power=10.0,
                    average_output_power=9.3,
                    efficiency=0.93,
                    power_factor=0.98,
                    signal_names=signals,
                ))
            else:
                # time_domain: synthetic scalar metrics
                metrics = {
                    "mean": ScalarMetric(name="mean", value=1.0, unit="V", signal_name=signals[0] if signals else ""),
                    "rms": ScalarMetric(name="rms", value=1.414, unit="V", signal_name=signals[0] if signals else ""),
                    "peak": ScalarMetric(name="peak", value=2.0, unit="V", signal_name=signals[0] if signals else ""),
                    "ripple": ScalarMetric(name="ripple", value=0.05, unit="V", signal_name=signals[0] if signals else ""),
                }
                job_results.append(PostProcessingJobResult(
                    job_id=job_id,
                    kind=kind,
                    success=True,
                    scalar_metrics=metrics,
                    signal_names=signals,
                ))

        return PostProcessingResult(jobs=job_results, success=True)

    def export_fmu(
        self,
        circuit_data: dict,
        settings: FmuExportSettings,
    ) -> FmuExportResult:  # pragma: no cover - placeholder path
        raise NotImplementedError(
            "FMU export is not available in demo mode — install the Pulsim "
            "runtime (pip install pulsim) to enable this feature."
        )

    def export_c99(
        self,
        circuit_data: dict,
        settings: C99CodegenSettings,
    ) -> C99CodegenResult:  # pragma: no cover - placeholder path
        raise NotImplementedError(
            "C99 codegen is not available in demo mode — install the Pulsim "
            "runtime (pip install pulsim) to enable this feature."
        )

    # ------------------------------------------------------------------
    # Wave-4 sub-B placeholder stubs.
    # ------------------------------------------------------------------
    def run_fra(
        self,
        circuit_data: dict,
        settings: FraSettings,
    ) -> FraResult:  # pragma: no cover - placeholder path
        return FraResult(
            success=False,
            failure_reason="FRA is not available in demo mode. Install Pulsim.",
        )

    def run_periodic_steady_state(
        self,
        circuit_data: dict,
        settings: PeriodicSteadyStateSettings,
    ) -> PeriodicSteadyStateResult:  # pragma: no cover - placeholder path
        return PeriodicSteadyStateResult(
            success=False,
            message="Periodic steady-state is not available in demo mode.",
        )

    def run_harmonic_balance(
        self,
        circuit_data: dict,
        settings: HarmonicBalanceSettings,
    ) -> HarmonicBalanceResult:  # pragma: no cover - placeholder path
        return HarmonicBalanceResult(
            success=False,
            message="Harmonic balance is not available in demo mode.",
        )

    def run_frequency_analysis(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> FrequencyAnalysisResult:
        """Return synthetic Bode plot data for demo mode."""
        import numpy as np

        num_decades = max(1, int(math.log10(settings.f_stop / max(settings.f_start, 1))))
        num_points = max(20, num_decades * settings.points_per_decade)
        freqs = list(np.logspace(
            math.log10(settings.f_start),
            math.log10(settings.f_stop),
            num_points,
        ))

        fc = 1000.0
        mag: list[float] = []
        phase: list[float] = []
        for f in freqs:
            ratio = f / fc
            mag.append(-10 * math.log10(1 + ratio**2))
            phase.append(-math.degrees(math.atan(ratio)))

        key = settings.output_nodes[0] if settings.output_nodes else "H(s)"
        return FrequencyAnalysisResult(
            frequencies=freqs,
            magnitude_db={key: mag},
            phase_deg={key: phase},
            gain_margin_db=12.0,
            phase_margin_deg=45.0,
            gain_crossover_hz=fc * 10,
            phase_crossover_hz=fc * 100,
            success=True,
        )


class PulsimBackend(SimulationBackend):
    """Adapter that executes simulations via the native Pulsim backend."""

    def __init__(self, module: Any, info: BackendInfo) -> None:
        self._module = module
        self.info = info
        self._converter = CircuitConverter(module)
        self._controllers: dict[int, Any] = {}
        self._lock = threading.Lock()
        self._cached_capabilities: set[str] | None = None
        self._cblock_autobuild_cache: dict[tuple[str, int, tuple[str, ...]], str] = {}

    @property
    def capabilities(self) -> set[str]:
        """Return set of supported capability names."""
        if self._cached_capabilities is not None:
            return self._cached_capabilities

        caps = {"transient"}

        # Check for DC analysis (top-level, simulator, or v1/v2 solver)
        if self._supports_dc_analysis(self._module):
            caps.add("dc")

        # Check for AC analysis
        if self._supports_ac_analysis(self._module):
            caps.add("ac")

        # Check for thermal simulation
        if self._supports_thermal_analysis(self._module):
            caps.add("thermal")

        # Check for post-processing (pulsim >= 0.7.0)
        if hasattr(self._module, "run_post_processing"):
            caps.add("post_processing")

        # Check for frequency analysis (pulsim >= 0.7.0)
        if hasattr(self._module, "run_frequency_analysis"):
            caps.add("frequency_analysis")

        # Check for averaged converter options (pulsim >= 0.7.0)
        if hasattr(self._module, "AveragedConverterOptions"):
            caps.add("averaged")

        # FMU 2.0 co-simulation export (pulsim >= 0.8.0).
        fmu_mod = getattr(self._module, "fmu", None)
        if fmu_mod is not None and hasattr(fmu_mod, "export"):
            caps.add("fmu_export")

        # C99 controller codegen (pulsim >= 0.8.0).
        codegen_mod = getattr(self._module, "codegen", None)
        if codegen_mod is not None and hasattr(codegen_mod, "generate"):
            caps.add("c99_codegen")

        # Wave-4 sub-B analysis modes (pulsim >= 0.9.0).
        sim_cls = getattr(self._module, "Simulator", None)
        if sim_cls is not None:
            if hasattr(sim_cls, "run_fra"):
                caps.add("fra")
            if hasattr(sim_cls, "run_periodic_shooting"):
                caps.add("periodic_steady_state")
            if hasattr(sim_cls, "run_harmonic_balance"):
                caps.add("harmonic_balance")

        self._cached_capabilities = caps
        return caps

    def has_capability(self, name: str) -> bool:
        """Check if a specific capability is supported."""
        return name in self.capabilities

    def run_transient(
        self,
        circuit_data: dict,
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
    ) -> BackendRunResult:
        """Run transient simulation and return the backend result payload."""
        result = BackendRunResult()

        callbacks.progress(0.0, "Starting Pulsim simulation...")
        time.sleep(0)

        try:
            base_dt = self._compute_time_step(settings)
        except Exception as exc:
            result.error_message = str(exc)
            return result

        has_cblock = self._has_component_type(circuit_data, "C_BLOCK")
        if has_cblock and not self._supports_modern_cblock_transient_path():
            min_ver = (
                f"{_CBLOCK_MODERN_TRANSIENT_MIN_BACKEND.major}."
                f"{_CBLOCK_MODERN_TRANSIENT_MIN_BACKEND.minor}."
                f"{_CBLOCK_MODERN_TRANSIENT_MIN_BACKEND.patch}"
            )
            result.error_message = (
                "C-Block control requires backend >= "
                f"{min_ver}. Detected {self.info.version}. "
                "Upgrade the backend and retry."
            )
            result.statistics["cblock_strict_mode"] = True
            result.statistics["execution_note"] = "cblock_blocked_legacy_backend"
            return result
        if has_cblock:
            prepared_data, prepare_error = self._prepare_cblock_runtime_payload(
                circuit_data,
                callbacks,
            )
            if prepare_error:
                result.error_message = prepare_error
                return result
            circuit_data = prepared_data
        prefer_nonblocking_run = self._should_prefer_nonblocking_transient(
            settings,
            base_dt,
            circuit_data=circuit_data,
        )
        if has_cblock:
            # C-Block execution remains strict (no API fallback), but we allow
            # progressive numeric retuning retries for convergence robustness.
            retry_profiles = self._build_cblock_strict_retry_profiles(settings)
        elif prefer_nonblocking_run:
            # Nonblocking transient paths already keep UI responsive and modern
            # backends have internal convergence handling. Re-running full profiles
            # here can create long visible restart cycles (95->100->restart).
            retry_profiles = [_TransientRetryProfile(name="default")]
        else:
            retry_profiles = self._build_transient_retry_profiles(settings)
        retry_errors: list[str] = []

        for retry_index, profile in enumerate(retry_profiles):
            if retry_index > 0:
                callbacks.progress(2.0, f"Retrying convergence with profile '{profile.name}'...")
            callbacks.progress(3.0, "Building circuit model...")
            time.sleep(0)

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
                    circuit_data,
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

            if has_cblock:
                retry_errors.append(error_text)
                is_last_profile = retry_index >= len(retry_profiles) - 1
                if is_last_profile or not self._is_transient_convergence_failure(error_text):
                    if retry_index > 0:
                        attempt_result.statistics["convergence_retry_profile"] = profile.name
                        attempt_result.statistics["convergence_retries"] = retry_index
                        attempt_result.statistics["convergence_retry_errors"] = retry_errors.copy()
                    return attempt_result
                continue

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

    def _resolve_signal_names(self, circuit: Any) -> list[str]:
        """Resolve labels for transient state-vector signals."""
        candidates: list[str] = []

        if hasattr(circuit, "signal_names"):
            try:
                candidates = [str(name) for name in circuit.signal_names()]
            except Exception:
                candidates = []

        if not candidates and hasattr(circuit, "node_names"):
            try:
                candidates = [str(name) for name in circuit.node_names()]
            except Exception:
                candidates = []

        if not candidates:
            return []

        normalized: list[str] = []
        seen: set[str] = set()
        for raw_name in candidates:
            name = self._normalize_signal_name(raw_name)
            if name in seen:
                continue
            seen.add(name)
            normalized.append(name)
        return normalized

    @staticmethod
    def _extract_virtual_channel_metadata(source: Any) -> dict[str, Any]:
        metadata_attr = getattr(source, "virtual_channel_metadata", None)
        if metadata_attr is None:
            return {}
        try:
            raw_metadata = metadata_attr() if callable(metadata_attr) else metadata_attr
        except Exception:
            return {}
        return raw_metadata if isinstance(raw_metadata, dict) else {}

    @staticmethod
    def _virtual_metadata_field(metadata_entry: Any, field: str) -> Any:
        if isinstance(metadata_entry, dict):
            return metadata_entry.get(field)
        return getattr(metadata_entry, field, None)

    @staticmethod
    def _virtual_component_type(metadata_entry: Any) -> str:
        return str(
            PulsimBackend._virtual_metadata_field(metadata_entry, "component_type") or ""
        ).strip().lower()

    @classmethod
    def _serialize_virtual_channel_metadata(
        cls,
        *sources: Any,
    ) -> dict[str, dict[str, str]]:
        serialized: dict[str, dict[str, str]] = {}
        for source in sources:
            raw_map = cls._extract_virtual_channel_metadata(source)
            if not raw_map:
                continue
            for raw_name, entry in raw_map.items():
                channel_name = str(raw_name or "").strip()
                if not channel_name:
                    continue
                component_type = str(
                    cls._virtual_metadata_field(entry, "component_type") or ""
                ).strip()
                source_component = str(
                    cls._virtual_metadata_field(entry, "source_component") or ""
                ).strip()
                domain = str(
                    cls._virtual_metadata_field(entry, "domain") or ""
                ).strip().lower()
                unit = str(
                    cls._virtual_metadata_field(entry, "unit") or ""
                ).strip()

                payload = {
                    "component_type": component_type,
                    "source_component": source_component,
                    "domain": domain,
                    "unit": unit,
                }
                serialized[channel_name] = payload
        return serialized

    def _probe_virtual_channels(self, *sources: Any) -> dict[str, str]:
        channels: dict[str, str] = {}
        for source in sources:
            metadata = self._extract_virtual_channel_metadata(source)
            if not metadata:
                continue
            for channel_name, metadata_entry in metadata.items():
                comp_type = self._virtual_component_type(metadata_entry)
                if comp_type in _PROBE_COMPONENT_TYPES:
                    channels[str(channel_name)] = comp_type
        return channels

    def _merge_native_virtual_probe_channels(
        self,
        circuit: Any,
        native_result: Any,
        result: BackendRunResult,
    ) -> None:
        """Use backend-native virtual channel arrays when available."""
        if not result.time:
            return

        probe_channels = self._probe_virtual_channels(native_result, circuit)
        channel_metadata = self._serialize_virtual_channel_metadata(native_result, circuit)

        virtual_channels_attr = getattr(native_result, "virtual_channels", None)
        if virtual_channels_attr is None:
            return
        try:
            raw_virtual_channels = (
                virtual_channels_attr() if callable(virtual_channels_attr) else virtual_channels_attr
            )
        except Exception:
            return
        if not isinstance(raw_virtual_channels, dict):
            return

        sample_count = len(result.time)
        merged_channels: list[str] = []
        for raw_name, series in raw_virtual_channels.items():
            channel_name = str(raw_name or "").strip()
            if not channel_name:
                continue
            if series is None:
                continue
            try:
                values = [float(value) for value in list(series)[:sample_count]]
            except (TypeError, ValueError):
                continue
            if not values:
                continue
            if len(values) < sample_count:
                values.extend([0.0] * (sample_count - len(values)))
            result.signals[channel_name] = values
            merged_channels.append(channel_name)

        if merged_channels:
            result.statistics["virtual_channel_names"] = sorted(set(merged_channels))
            if channel_metadata:
                result.statistics["virtual_channel_metadata"] = channel_metadata
            if probe_channels:
                result.statistics["virtual_probe_channels"] = sorted(
                    {name for name in merged_channels if name in probe_channels}
                )
            if channel_metadata:
                thermal_channels = [
                    name
                    for name in merged_channels
                    if (
                        str(channel_metadata.get(name, {}).get("domain", "")).strip().lower()
                        == "thermal"
                        or str(
                            channel_metadata.get(name, {}).get("component_type", "")
                        ).strip().lower()
                        == "thermal_trace"
                    )
                ]
                if thermal_channels:
                    result.statistics["virtual_thermal_channels"] = sorted(set(thermal_channels))

    def _ensure_virtual_probe_channels(
        self,
        circuit: Any,
        result: BackendRunResult,
        signal_names: list[str],
        *,
        callbacks: BackendCallbacks | None = None,
        progress_start: float = 92.0,
        progress_span: float = 7.0,
    ) -> None:
        """Fill missing virtual channels by evaluating backend virtual channels."""
        if not result.time:
            return

        sample_count = len(result.time)
        channel_metadata = self._serialize_virtual_channel_metadata(circuit)
        expected_channels = list(channel_metadata.keys())
        if not expected_channels:
            # Legacy backend: at least try known probe channels.
            expected_channels = list(self._probe_virtual_channels(circuit).keys())
        if not expected_channels:
            return

        missing_channels = [
            channel_name
            for channel_name in expected_channels
            if len(result.signals.get(channel_name, [])) < sample_count
        ]

        evaluate = getattr(circuit, "evaluate_virtual_signals", None)
        if missing_channels and not callable(evaluate):
            return

        ordered_signal_names = (
            [name for name in signal_names if name in result.signals]
            if signal_names
            else list(result.signals.keys())
        )
        if not ordered_signal_names:
            return

        if missing_channels:
            ordered_series = [result.signals.get(name, []) for name in ordered_signal_names]
            evaluated_channels: dict[str, list[float]] = {
                channel_name: [] for channel_name in missing_channels
            }
            if callbacks is not None:
                callbacks.progress(progress_start, "Deriving virtual channels...")

            for sample_index in range(sample_count):
                state = [
                    float(series[sample_index]) if sample_index < len(series) else 0.0
                    for series in ordered_series
                ]
                try:
                    virtual_values = evaluate(state)
                except Exception as exc:
                    log.debug("Virtual channel evaluation skipped: %s", exc)
                    return

                if not isinstance(virtual_values, dict):
                    return

                for channel_name in missing_channels:
                    try:
                        value = float(virtual_values.get(channel_name, 0.0))
                    except (TypeError, ValueError):
                        value = 0.0
                    evaluated_channels[channel_name].append(value)

                if sample_index and sample_index % 2048 == 0:
                    if callbacks is not None:
                        progress = progress_start + min(
                            progress_span,
                            (sample_index / sample_count) * progress_span,
                        )
                        callbacks.progress(progress, "Deriving virtual channels...")
                    time.sleep(0)

            for channel_name, values in evaluated_channels.items():
                result.signals[channel_name] = values

        existing_metadata = (
            result.statistics.get("virtual_channel_metadata")
            if isinstance(result.statistics.get("virtual_channel_metadata"), dict)
            else {}
        )
        merged_metadata = dict(existing_metadata)
        merged_metadata.update(channel_metadata)
        if merged_metadata:
            result.statistics["virtual_channel_metadata"] = merged_metadata

        virtual_names = sorted(
            {
                channel_name
                for channel_name in expected_channels
                if len(result.signals.get(channel_name, [])) >= sample_count
            }
        )
        if virtual_names:
            result.statistics["virtual_channel_names"] = virtual_names

        probe_channels = self._probe_virtual_channels(circuit)
        probe_names = [name for name in virtual_names if name in probe_channels]
        if probe_names:
            result.statistics["virtual_probe_channels"] = sorted(set(probe_names))

        control_names = [
            name
            for name in virtual_names
            if str(merged_metadata.get(name, {}).get("domain", "")).strip().lower() == "control"
        ]
        if control_names:
            result.statistics["virtual_control_channels"] = sorted(set(control_names))

        thermal_names = [
            name
            for name in virtual_names
            if (
                str(merged_metadata.get(name, {}).get("domain", "")).strip().lower() == "thermal"
                or str(
                    merged_metadata.get(name, {}).get("component_type", "")
                ).strip().lower()
                == "thermal_trace"
            )
        ]
        if thermal_names:
            result.statistics["virtual_thermal_channels"] = sorted(set(thermal_names))

        if callbacks is not None:
            callbacks.progress(progress_start + progress_span, "Virtual channels ready")

    def _repair_current_probe_channels_from_bypass(
        self,
        circuit: Any,
        result: BackendRunResult,
    ) -> None:
        """Repair flatlined current-probe channels using the stamped bypass branch.

        Some backend builds expose current-probe channels but return all-zero values
        even when branch current is flowing. Current probes are stamped with a tiny
        bypass resistor by the converter; reconstruct probe current from node voltages
        when the reported probe channel is effectively zero.
        """
        sample_count = len(result.time)
        if sample_count <= 0:
            return

        virtual_components_attr = getattr(circuit, "virtual_components", None)
        if not callable(virtual_components_attr):
            return
        node_name_attr = getattr(circuit, "node_name", None)
        if not callable(node_name_attr):
            return

        try:
            virtual_components = virtual_components_attr()
        except Exception:
            return
        try:
            components_iter = list(virtual_components)
        except Exception:
            return

        repaired_channels: list[str] = []

        for entry in components_iter:
            comp_type = str(getattr(entry, "type", "") or "").strip().lower()
            if comp_type != "current_probe":
                continue

            channel_name = str(getattr(entry, "name", "") or "").strip()
            if not channel_name:
                continue

            existing = result.signals.get(channel_name)
            if not isinstance(existing, list) or len(existing) < sample_count:
                continue

            try:
                peak_existing = max(abs(float(value)) for value in existing[:sample_count])
            except Exception:
                continue
            if peak_existing > 1e-12:
                # Backend already produced a meaningful current-probe channel.
                continue

            raw_nodes = getattr(entry, "nodes", None)
            if not isinstance(raw_nodes, list) or len(raw_nodes) < 2:
                continue
            try:
                node_in = int(raw_nodes[0])
                node_out = int(raw_nodes[1])
            except (TypeError, ValueError):
                continue
            if node_in < 0 or node_out < 0:
                continue

            node_in_name = str(node_name_attr(node_in) or "").strip()
            node_out_name = str(node_name_attr(node_out) or "").strip()
            if not node_in_name or not node_out_name:
                continue

            vin = result.signals.get(f"V({node_in_name})") or result.signals.get(node_in_name)
            vout = result.signals.get(f"V({node_out_name})") or result.signals.get(node_out_name)
            if not isinstance(vin, list) or not isinstance(vout, list):
                continue
            if len(vin) < sample_count or len(vout) < sample_count:
                continue

            numeric_params = getattr(entry, "numeric_params", None)
            series_r = 1e-4
            if isinstance(numeric_params, dict):
                try:
                    series_r = float(numeric_params.get("series_resistance", series_r))
                except (TypeError, ValueError):
                    series_r = 1e-4
            if abs(series_r) < 1e-15:
                continue

            repaired = [
                (float(vin[idx]) - float(vout[idx])) / series_r
                for idx in range(sample_count)
            ]
            result.signals[channel_name] = repaired
            repaired_channels.append(channel_name)

        if repaired_channels:
            result.statistics["virtual_probe_repaired_channels"] = sorted(set(repaired_channels))

    @staticmethod
    def _normalize_signal_name(raw_name: str) -> str:
        """Normalize backend signal names for waveform display."""
        name = str(raw_name or "").strip()
        if not name:
            return "V(?)"

        upper = name.upper()
        if upper.startswith(("V(", "I(", "P(", "T(")):
            return name
        return f"V({name})"

    @staticmethod
    def _normalize_integration_method(value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw == "rk4" or raw == "rk45":
            return "trapezoidal"
        if raw == "bdf":
            return "bdf2"
        if not raw:
            return "auto"
        return raw

    @staticmethod
    def _normalize_step_mode(value: Any) -> str:
        raw = str(value or "").strip().lower()
        return raw if raw in {"fixed", "variable"} else "fixed"

    @staticmethod
    def _normalize_formulation_mode(value: Any) -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "projected": "projected_wrapper",
            "projectedwrapper": "projected_wrapper",
            "native": "projected_wrapper",
            "directdae": "direct",
            "dae": "direct",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in {"projected_wrapper", "direct"} else "projected_wrapper"

    @staticmethod
    def _normalize_control_mode(value: Any) -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "sampled": "discrete",
            "sample": "discrete",
            "continuous_time": "continuous",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in {"auto", "continuous", "discrete"} else "auto"

    @staticmethod
    def _normalize_thermal_policy(value: Any) -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "losswithtemperaturescaling": "loss_with_temperature_scaling",
            "temperature_scaling": "loss_with_temperature_scaling",
            "lossonly": "loss_only",
        }
        normalized = aliases.get(raw, raw)
        if normalized not in {"loss_only", "loss_with_temperature_scaling"}:
            return "loss_with_temperature_scaling"
        return normalized

    @staticmethod
    def _normalize_thermal_network_kind(value: Any) -> str:
        raw = str(value or "").strip().lower()
        aliases = {
            "single": "single_rc",
            "single-rc": "single_rc",
            "singlerc": "single_rc",
            "rc": "single_rc",
        }
        normalized = aliases.get(raw, raw)
        return normalized if normalized in {"single_rc", "foster", "cauer"} else "single_rc"

    @staticmethod
    def _component_name(component: dict[str, Any]) -> str:
        return str(component.get("name") or component.get("id") or "").strip()

    @staticmethod
    def _first_numeric(params: dict[str, Any], keys: tuple[str, ...], default: float) -> float:
        for key in keys:
            if key not in params:
                continue
            try:
                return float(params.get(key))
            except (TypeError, ValueError):
                continue
        return float(default)

    @staticmethod
    def _first_text(params: dict[str, Any], keys: tuple[str, ...], default: str = "") -> str:
        for key in keys:
            if key not in params:
                continue
            value = params.get(key)
            if value is None:
                continue
            return str(value).strip()
        return default

    @staticmethod
    def _parse_numeric_sequence(raw_value: Any) -> list[float]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            text = raw_value.strip()
            if not text:
                return []
            parts = [item.strip() for item in text.replace(";", ",").split(",")]
            out: list[float] = []
            for part in parts:
                if not part:
                    continue
                try:
                    out.append(float(part))
                except (TypeError, ValueError):
                    return []
            return out
        if isinstance(raw_value, (list, tuple)):
            out: list[float] = []
            for item in raw_value:
                try:
                    out.append(float(item))
                except (TypeError, ValueError):
                    return []
            return out
        return []

    @classmethod
    def _first_numeric_sequence(cls, params: dict[str, Any], keys: tuple[str, ...]) -> list[float]:
        for key in keys:
            if key not in params:
                continue
            values = cls._parse_numeric_sequence(params.get(key))
            if values:
                return values
        return []

    @staticmethod
    def _coerce_surface_table(raw_value: Any) -> list[float]:
        if raw_value is None:
            return []
        if isinstance(raw_value, str):
            return PulsimBackend._parse_numeric_sequence(raw_value)
        if isinstance(raw_value, (list, tuple)):
            out: list[float] = []
            for item in raw_value:
                try:
                    out.append(float(item))
                except (TypeError, ValueError):
                    return []
            return out
        return []

    def _make_switching_energy_surface_config(
        self,
        *,
        current_axis: list[float],
        voltage_axis: list[float],
        temperature_axis: list[float],
        eon_table: list[float],
        eoff_table: list[float],
        err_table: list[float],
    ) -> Any:
        config_cls = getattr(self._module, "SwitchingEnergySurface3D", None)
        if config_cls is None:
            return {
                "current_axis": list(current_axis),
                "voltage_axis": list(voltage_axis),
                "temperature_axis": list(temperature_axis),
                "eon_table": list(eon_table),
                "eoff_table": list(eoff_table),
                "err_table": list(err_table),
            }
        config = config_cls()
        if hasattr(config, "current_axis"):
            config.current_axis = list(current_axis)
        if hasattr(config, "voltage_axis"):
            config.voltage_axis = list(voltage_axis)
        if hasattr(config, "temperature_axis"):
            config.temperature_axis = list(temperature_axis)
        if hasattr(config, "eon_table"):
            config.eon_table = list(eon_table)
        if hasattr(config, "eoff_table"):
            config.eoff_table = list(eoff_table)
        if hasattr(config, "err_table"):
            config.err_table = list(err_table)
        return config

    def _make_switching_energy_config(self, eon: float, eoff: float, err: float) -> Any:
        config_cls = getattr(self._module, "SwitchingEnergy", None)
        if config_cls is None:
            return {
                "eon": float(eon),
                "eoff": float(eoff),
                "err": float(err),
            }
        config = config_cls()
        if hasattr(config, "eon"):
            config.eon = float(eon)
        if hasattr(config, "eoff"):
            config.eoff = float(eoff)
        if hasattr(config, "err"):
            config.err = float(err)
        return config

    def _make_thermal_device_config(
        self,
        *,
        enabled: bool,
        network_kind: str,
        rth: float,
        cth: float,
        stage_rth: list[float],
        stage_cth: list[float],
        temp_init: float,
        temp_ref: float,
        alpha: float,
        shared_sink_id: str,
        shared_sink_rth: float,
        shared_sink_cth: float,
    ) -> Any:
        config_cls = getattr(self._module, "ThermalDeviceConfig", None)
        if config_cls is None:
            return {
                "enabled": bool(enabled),
                "network_kind": str(network_kind),
                "rth": float(rth),
                "cth": float(cth),
                "stage_rth": list(stage_rth),
                "stage_cth": list(stage_cth),
                "temp_init": float(temp_init),
                "temp_ref": float(temp_ref),
                "alpha": float(alpha),
                "shared_sink_id": str(shared_sink_id),
                "shared_sink_rth": float(shared_sink_rth),
                "shared_sink_cth": float(shared_sink_cth),
            }
        config = config_cls()
        if hasattr(config, "enabled"):
            config.enabled = bool(enabled)
        if hasattr(config, "network_kind") and hasattr(self._module, "ThermalNetworkKind"):
            enum_map = {
                "single_rc": "SingleRC",
                "foster": "Foster",
                "cauer": "Cauer",
            }
            enum_name = enum_map.get(network_kind, "SingleRC")
            if hasattr(self._module.ThermalNetworkKind, enum_name):
                config.network_kind = getattr(self._module.ThermalNetworkKind, enum_name)
        if hasattr(config, "rth"):
            config.rth = float(rth)
        if hasattr(config, "cth"):
            config.cth = float(cth)
        if hasattr(config, "stage_rth"):
            config.stage_rth = list(stage_rth)
        if hasattr(config, "stage_cth"):
            config.stage_cth = list(stage_cth)
        if hasattr(config, "temp_init"):
            config.temp_init = float(temp_init)
        if hasattr(config, "temp_ref"):
            config.temp_ref = float(temp_ref)
        if hasattr(config, "alpha"):
            config.alpha = float(alpha)
        if hasattr(config, "shared_sink_id"):
            config.shared_sink_id = str(shared_sink_id)
        if hasattr(config, "shared_sink_rth"):
            config.shared_sink_rth = float(shared_sink_rth)
        if hasattr(config, "shared_sink_cth"):
            config.shared_sink_cth = float(shared_sink_cth)
        return config

    def _build_switching_energy_map(self, circuit_data: dict[str, Any]) -> dict[str, Any]:
        components = circuit_data.get("components", []) if isinstance(circuit_data, dict) else []
        energy_map: dict[str, Any] = {}
        for component in components:
            name = self._component_name(component)
            if not name:
                continue
            params = component.get("parameters")
            if not isinstance(params, dict):
                continue
            component_loss = component.get("loss")
            if not isinstance(component_loss, dict):
                component_loss = {}
            nested_loss = params.get("loss")
            if not isinstance(nested_loss, dict):
                nested_loss = {}
            loss_payload: dict[str, Any] = {}
            loss_payload.update(component_loss)
            loss_payload.update(nested_loss)
            loss_model = str(
                loss_payload.get("model")
                or params.get("switching_loss_model")
                or ""
            ).strip().lower()
            if loss_model == "datasheet":
                # Datasheet surfaces are mapped via switching_energy_surfaces.
                continue
            energy_payload: dict[str, Any] = {}
            energy_payload.update(loss_payload)
            energy_payload.update(params)

            eon = self._first_numeric(
                energy_payload,
                ("switching_eon_j", "switching_eon", "e_on", "eon"),
                0.0,
            )
            eoff = self._first_numeric(
                energy_payload,
                ("switching_eoff_j", "switching_eoff", "e_off", "eoff"),
                0.0,
            )
            err = self._first_numeric(
                energy_payload,
                ("switching_err_j", "switching_err", "err", "e_rr"),
                0.0,
            )
            if abs(eon) + abs(eoff) + abs(err) <= 0.0:
                continue
            energy_map[name] = self._make_switching_energy_config(eon, eoff, err)
        return energy_map

    def _build_switching_energy_surface_map(self, circuit_data: dict[str, Any]) -> dict[str, Any]:
        components = circuit_data.get("components", []) if isinstance(circuit_data, dict) else []
        surfaces: dict[str, Any] = {}
        for component in components:
            name = self._component_name(component)
            if not name:
                continue
            params = component.get("parameters")
            if not isinstance(params, dict):
                continue

            component_loss = component.get("loss")
            if not isinstance(component_loss, dict):
                component_loss = {}
            nested_loss = params.get("loss")
            if not isinstance(nested_loss, dict):
                nested_loss = {}
            loss_payload: dict[str, Any] = {}
            loss_payload.update(component_loss)
            loss_payload.update(nested_loss)

            loss_model = str(
                loss_payload.get("model")
                or params.get("switching_loss_model")
                or ""
            ).strip().lower()
            if loss_model != "datasheet":
                continue

            axes = loss_payload.get("axes")
            current_axis: list[float] = []
            voltage_axis: list[float] = []
            temperature_axis: list[float] = []
            if isinstance(axes, dict):
                current_axis = self._parse_numeric_sequence(axes.get("current"))
                voltage_axis = self._parse_numeric_sequence(axes.get("voltage"))
                temperature_axis = self._parse_numeric_sequence(axes.get("temperature"))
            if not current_axis:
                current_axis = self._first_numeric_sequence(
                    params,
                    ("switching_loss_axes_current", "switching_loss_axis_current"),
                )
            if not voltage_axis:
                voltage_axis = self._first_numeric_sequence(
                    params,
                    ("switching_loss_axes_voltage", "switching_loss_axis_voltage"),
                )
            if not temperature_axis:
                temperature_axis = self._first_numeric_sequence(
                    params,
                    ("switching_loss_axes_temperature", "switching_loss_axis_temperature"),
                )
            if not current_axis or not voltage_axis or not temperature_axis:
                continue

            eon_table = self._coerce_surface_table(loss_payload.get("eon"))
            eoff_table = self._coerce_surface_table(loss_payload.get("eoff"))
            err_table = self._coerce_surface_table(loss_payload.get("err"))
            if not eon_table:
                eon_table = self._first_numeric_sequence(
                    params,
                    ("switching_loss_eon_table",),
                )
            if not eoff_table:
                eoff_table = self._first_numeric_sequence(
                    params,
                    ("switching_loss_eoff_table",),
                )
            if not err_table:
                err_table = self._first_numeric_sequence(
                    params,
                    ("switching_loss_err_table",),
                )
            if not eon_table or not eoff_table:
                continue

            surfaces[name] = self._make_switching_energy_surface_config(
                current_axis=current_axis,
                voltage_axis=voltage_axis,
                temperature_axis=temperature_axis,
                eon_table=eon_table,
                eoff_table=eoff_table,
                err_table=err_table,
            )
        return surfaces

    def _build_thermal_device_map(
        self,
        circuit_data: dict[str, Any],
        settings: SimulationSettings,
    ) -> dict[str, Any]:
        components = circuit_data.get("components", []) if isinstance(circuit_data, dict) else []
        thermal_map: dict[str, Any] = {}
        override_keys = {
            "thermal_enabled",
            "thermal_rth",
            "thermal_cth",
            "thermal_temp_init",
            "thermal_temp_ref",
            "thermal_alpha",
            "thermal_network",
            "thermal_rth_stages",
            "thermal_cth_stages",
            "thermal_shared_sink_id",
            "thermal_shared_sink_rth",
            "thermal_shared_sink_cth",
        }
        default_rth = max(0.0, float(getattr(settings, "thermal_default_rth", 1.0)))
        default_cth = max(0.0, float(getattr(settings, "thermal_default_cth", 0.1)))
        default_temp = float(getattr(settings, "thermal_ambient", 25.0))

        for component in components:
            name = self._component_name(component)
            if not name:
                continue
            params = component.get("parameters")
            if not isinstance(params, dict):
                continue
            component_thermal = component.get("thermal")
            if not isinstance(component_thermal, dict):
                component_thermal = {}
            nested_thermal = params.get("thermal")
            if not isinstance(nested_thermal, dict):
                nested_thermal = {}

            if not (override_keys & set(params.keys())) and not component_thermal and not nested_thermal:
                continue

            thermal_payload: dict[str, Any] = {}
            thermal_payload.update(component_thermal)
            thermal_payload.update(nested_thermal)
            thermal_payload.update(params)
            if "enabled" in thermal_payload and "thermal_enabled" not in thermal_payload:
                thermal_payload["thermal_enabled"] = thermal_payload.get("enabled")

            enabled = bool(thermal_payload.get("thermal_enabled", True))
            rth = max(
                0.0,
                self._first_numeric(thermal_payload, ("thermal_rth", "rth", "rth_ja"), default_rth),
            )
            cth = max(
                0.0,
                self._first_numeric(thermal_payload, ("thermal_cth", "cth"), default_cth),
            )
            temp_init = self._first_numeric(
                thermal_payload,
                ("thermal_temp_init", "temp_init", "temperature_init"),
                default_temp,
            )
            temp_ref = self._first_numeric(
                thermal_payload,
                ("thermal_temp_ref", "temp_ref", "temperature_ref"),
                default_temp,
            )
            alpha = max(
                0.0,
                self._first_numeric(thermal_payload, ("thermal_alpha", "alpha_temp", "alpha"), 0.004),
            )
            stage_rth = self._first_numeric_sequence(
                thermal_payload,
                ("thermal_rth_stages", "rth_stages", "stage_rth"),
            )
            stage_cth = self._first_numeric_sequence(
                thermal_payload,
                ("thermal_cth_stages", "cth_stages", "stage_cth"),
            )
            network_kind = self._normalize_thermal_network_kind(
                self._first_text(thermal_payload, ("thermal_network", "network"), "single_rc")
            )
            if (stage_rth or stage_cth) and "thermal_network" not in thermal_payload and "network" not in thermal_payload:
                network_kind = "foster"
            shared_sink_id = self._first_text(
                thermal_payload,
                ("thermal_shared_sink_id", "shared_sink_id"),
                "",
            )
            shared_sink_rth = self._first_numeric(
                thermal_payload,
                ("thermal_shared_sink_rth", "shared_sink_rth"),
                0.0,
            )
            shared_sink_cth = self._first_numeric(
                thermal_payload,
                ("thermal_shared_sink_cth", "shared_sink_cth"),
                0.0,
            )
            thermal_map[name] = self._make_thermal_device_config(
                enabled=enabled,
                network_kind=network_kind,
                rth=rth,
                cth=cth,
                stage_rth=stage_rth,
                stage_cth=stage_cth,
                temp_init=temp_init,
                temp_ref=temp_ref,
                alpha=alpha,
                shared_sink_id=shared_sink_id,
                shared_sink_rth=shared_sink_rth,
                shared_sink_cth=shared_sink_cth,
            )
        return thermal_map

    def _integrator_enum_name(self, method: str) -> str:
        mapping = {
            # "auto" maps to BDF1: first-order implicit method is the most stable
            # default for switching power converters (proven by benchmark tests).
            "auto": "BDF1",
            "trapezoidal": "Trapezoidal",
            "bdf1": "BDF1",
            "bdf2": "BDF2",
            "bdf3": "BDF3",
            "bdf4": "BDF4",
            "bdf5": "BDF5",
            "gear": "Gear",
            "trbdf2": "TRBDF2",
            "rosenbrockw": "RosenbrockW",
            "sdirk2": "SDIRK2",
        }
        return mapping.get(method, "BDF1")

    def _should_use_simulation_options(self, settings: SimulationSettings) -> bool:
        # Use SimulationOptions only when the backend API is new enough.
        # Legacy/early backends can expose SimulationOptions/Simulator but still
        # run as a fully blocking path with poor runtime for closed-loop
        # electrothermal cases.
        if not (hasattr(self._module, "SimulationOptions") and hasattr(self._module, "Simulator")):
            return False

        parsed_version = self.info.parsed_version
        if parsed_version is None:
            try:
                parsed_version = BackendVersion.from_string(str(self.info.version))
                self.info.parsed_version = parsed_version
            except ValueError:
                log.warning(
                    "Could not parse backend version '%s'; using compatibility transient path.",
                    self.info.version,
                )
                return False

        return parsed_version.is_compatible_with(_SIMULATION_OPTIONS_MIN_BACKEND)

    def _build_dc_convergence_config(self, settings: SimulationSettings) -> Any | None:
        config_cls = getattr(self._module, "DCConvergenceConfig", None)
        if config_cls is None:
            return None
        config = config_cls()
        strategy = str(getattr(settings, "dc_strategy", "auto")).lower()
        strategy_enum = getattr(self._module, "DCStrategy", None)
        if strategy_enum is not None:
            if strategy == "gmin" and hasattr(strategy_enum, "GminStepping"):
                config.strategy = strategy_enum.GminStepping
            elif strategy == "source" and hasattr(strategy_enum, "SourceStepping"):
                config.strategy = strategy_enum.SourceStepping
            elif strategy == "pseudo" and hasattr(strategy_enum, "PseudoTransient"):
                config.strategy = strategy_enum.PseudoTransient
            elif strategy == "direct" and hasattr(strategy_enum, "Direct"):
                config.strategy = strategy_enum.Direct
            elif hasattr(strategy_enum, "Auto"):
                config.strategy = strategy_enum.Auto

        if strategy == "gmin" and hasattr(config, "gmin_config"):
            config.gmin_config.initial_gmin = float(getattr(settings, "gmin_initial", 1e-3))
            config.gmin_config.final_gmin = float(getattr(settings, "gmin_final", 1e-12))
        if strategy == "source" and hasattr(config, "source_config"):
            source_steps = max(1, int(getattr(settings, "dc_source_steps", 10)))
            if hasattr(config.source_config, "max_steps"):
                config.source_config.max_steps = source_steps
        return config

    def _resolve_control_schedule(
        self,
        *,
        settings: SimulationSettings,
        circuit_data: dict[str, Any] | None,
    ) -> tuple[str, float | None]:
        components: list[dict[str, Any]] = []
        if isinstance(circuit_data, dict):
            raw_components = circuit_data.get("components")
            if isinstance(raw_components, list):
                components = [item for item in raw_components if isinstance(item, dict)]
        return derive_control_schedule_from_serialized_components(
            components,
            fallback_mode=getattr(settings, "control_mode", "auto"),
            fallback_sample_time=getattr(settings, "control_sample_time", 0.0),
        )

    def _build_simulation_options_from_yaml_parser(
        self,
        settings: SimulationSettings,
        *,
        circuit_data: dict[str, Any] | None = None,
    ) -> Any | None:
        """Build SimulationOptions via backend YamlParser defaults.

        This avoids drift from backend-internal defaults that are not exposed
        as writable Python attributes on SimulationOptions.
        """
        parser_cls = getattr(self._module, "YamlParser", None)
        if parser_cls is None:
            return None

        parser_options_cls = getattr(self._module, "YamlParserOptions", None)
        try:
            parser = (
                parser_cls(parser_options_cls())
                if parser_options_cls is not None
                else parser_cls()
            )
        except Exception as exc:
            log.debug("Could not instantiate backend YamlParser: %s", exc)
            return None

        method = self._normalize_integration_method(getattr(settings, "solver", "auto"))
        step_mode = self._normalize_step_mode(getattr(settings, "step_mode", "fixed"))
        control_mode, control_sample_time = self._resolve_control_schedule(
            settings=settings,
            circuit_data=circuit_data,
        )
        thermal_policy = self._normalize_thermal_policy(
            getattr(settings, "thermal_policy", "loss_with_temperature_scaling")
        )

        dt = max(float(getattr(settings, "t_step", 1e-6)), 1e-15)
        dt_max = float(getattr(settings, "max_step", dt))
        if dt_max <= 0.0:
            dt_max = dt

        integrator_tokens = {
            "trapezoidal": "trapezoidal",
            "bdf1": "bdf1",
            "bdf2": "bdf2",
            "bdf3": "bdf3",
            "bdf4": "bdf4",
            "bdf5": "bdf5",
            "gear": "gear",
            "trbdf2": "trbdf2",
            "rosenbrockw": "rosenbrockw",
            "sdirk2": "sdirk2",
        }

        simulation_section: dict[str, Any] = {
            "tstart": float(settings.t_start),
            "tstop": float(settings.t_stop),
            "dt": float(dt),
            "step_mode": step_mode,
            "enable_events": bool(getattr(settings, "enable_events", True)),
            "enable_losses": bool(getattr(settings, "enable_losses", True)),
            "max_step_retries": max(0, int(getattr(settings, "max_step_retries", 8))),
            "formulation": self._normalize_formulation_mode(
                getattr(settings, "formulation_mode", "projected_wrapper")
            ),
            "direct_formulation_fallback": bool(
                getattr(settings, "direct_formulation_fallback", True)
            ),
            "newton": {
                "max_iterations": max(1, int(getattr(settings, "max_newton_iterations", 100))),
                "enable_limiting": bool(getattr(settings, "enable_voltage_limiting", False)),
                "max_voltage_step": max(0.0, float(getattr(settings, "max_voltage_step", 5.0))),
            },
            "control": {
                "mode": control_mode,
            },
            "thermal": {
                "enabled": bool(getattr(settings, "enable_losses", True)),
                "ambient": float(getattr(settings, "thermal_ambient", 25.0)),
                "policy": thermal_policy,
                "default_rth": max(0.0, float(getattr(settings, "thermal_default_rth", 1.0))),
                "default_cth": max(0.0, float(getattr(settings, "thermal_default_cth", 0.1))),
            },
        }
        if step_mode == "variable":
            simulation_section["dt_max"] = float(dt_max)

        if method != "auto":
            token = integrator_tokens.get(method)
            if token:
                simulation_section["integrator"] = token

        if control_sample_time is not None:
            simulation_section["control"]["sample_time"] = float(max(control_sample_time, 1e-12))

        def _fmt_real(value: Any) -> str:
            return f"{float(value):.16g}"

        def _fmt_bool(value: Any) -> str:
            return "true" if bool(value) else "false"

        lines: list[str] = [
            "schema: pulsim-v1",
            "version: 1",
            "simulation:",
            f"  tstart: {_fmt_real(simulation_section['tstart'])}",
            f"  tstop: {_fmt_real(simulation_section['tstop'])}",
            f"  dt: {_fmt_real(simulation_section['dt'])}",
            f"  step_mode: {simulation_section['step_mode']}",
        ]
        if "dt_max" in simulation_section:
            lines.append(f"  dt_max: {_fmt_real(simulation_section['dt_max'])}")
        if "integrator" in simulation_section:
            lines.append(f"  integrator: {simulation_section['integrator']}")
        lines.extend(
            [
                f"  enable_events: {_fmt_bool(simulation_section['enable_events'])}",
                f"  enable_losses: {_fmt_bool(simulation_section['enable_losses'])}",
                f"  max_step_retries: {int(simulation_section['max_step_retries'])}",
                f"  formulation: {simulation_section['formulation']}",
                "  direct_formulation_fallback: "
                f"{_fmt_bool(simulation_section['direct_formulation_fallback'])}",
                "  newton:",
                f"    max_iterations: {int(simulation_section['newton']['max_iterations'])}",
                "    enable_limiting: "
                f"{_fmt_bool(simulation_section['newton']['enable_limiting'])}",
                "    max_voltage_step: "
                f"{_fmt_real(simulation_section['newton']['max_voltage_step'])}",
                "  control:",
                f"    mode: {simulation_section['control']['mode']}",
            ]
        )
        if "sample_time" in simulation_section["control"]:
            lines.append(
                "    sample_time: "
                f"{_fmt_real(simulation_section['control']['sample_time'])}"
            )
        lines.extend(
            [
                "  thermal:",
                f"    enabled: {_fmt_bool(simulation_section['thermal']['enabled'])}",
                f"    ambient: {_fmt_real(simulation_section['thermal']['ambient'])}",
                f"    policy: {simulation_section['thermal']['policy']}",
                f"    default_rth: {_fmt_real(simulation_section['thermal']['default_rth'])}",
                f"    default_cth: {_fmt_real(simulation_section['thermal']['default_cth'])}",
                "components:",
                "  - type: resistor",
                "    name: __opts_stub__",
                "    nodes: [__opts_n1, 0]",
                "    value: 1.0",
            ]
        )
        payload_text = "\n".join(lines) + "\n"

        try:
            _, options = parser.load_string(payload_text)
        except Exception as exc:
            log.debug("YamlParser options synthesis failed: %s", exc)
            return None

        parser_errors = getattr(parser, "errors", [])
        try:
            parser_errors = parser_errors() if callable(parser_errors) else parser_errors
        except Exception:
            parser_errors = []
        if parser_errors:
            log.debug("YamlParser reported options synthesis errors: %s", parser_errors)
            return None

        return options

    def _build_simulation_options(
        self,
        settings: SimulationSettings,
        dt: float,
        newton_opts: Any,
        linear_solver: Any | None,
        circuit_data: dict[str, Any] | None = None,
    ) -> Any:
        opts = self._build_simulation_options_from_yaml_parser(
            settings,
            circuit_data=circuit_data,
        )
        using_parser_defaults = opts is not None
        if opts is None:
            opts = self._module.SimulationOptions()

        method = self._normalize_integration_method(getattr(settings, "solver", "auto"))
        step_mode = self._normalize_step_mode(getattr(settings, "step_mode", "fixed"))
        dt_max = float(getattr(settings, "max_step", dt))
        if dt_max <= 0.0:
            dt_max = dt
        if step_mode == "variable":
            dt_min = max(min(dt, dt_max) * 1e-3, 1e-15)
        else:
            dt_min = max(min(dt, dt_max), 1e-15)

        for attr, value in (
            ("tstart", float(settings.t_start)),
            ("t_stop", float(settings.t_stop)),
            ("tstop", float(settings.t_stop)),
            ("dt", float(dt)),
            ("dt_min", float(dt_min)),
            ("dtmax", float(dt_max)),
            ("dt_max", float(dt_max)),
        ):
            if hasattr(opts, attr):
                try:
                    setattr(opts, attr, value)
                except Exception:
                    pass

        if not using_parser_defaults:
            if hasattr(opts, "newton_options"):
                opts.newton_options = newton_opts
            elif hasattr(opts, "newton_opts"):
                opts.newton_opts = newton_opts

            if linear_solver is not None:
                if hasattr(opts, "linear_solver"):
                    opts.linear_solver = linear_solver
                elif hasattr(opts, "linear_solver_config"):
                    opts.linear_solver_config = linear_solver

            dc_config = self._build_dc_convergence_config(settings)
            if dc_config is not None:
                if hasattr(opts, "dc_config"):
                    opts.dc_config = dc_config
                elif hasattr(opts, "dc_options"):
                    opts.dc_options = dc_config

            if hasattr(opts, "adaptive_timestep"):
                opts.adaptive_timestep = step_mode == "variable"
            if hasattr(opts, "step_mode") and hasattr(self._module, "StepMode"):
                enum_name = "Variable" if step_mode == "variable" else "Fixed"
                if hasattr(self._module.StepMode, enum_name):
                    opts.step_mode = getattr(self._module.StepMode, enum_name)

            if hasattr(opts, "integrator") and hasattr(self._module, "Integrator"):
                enum_name = self._integrator_enum_name(method)
                if hasattr(self._module.Integrator, enum_name):
                    opts.integrator = getattr(self._module.Integrator, enum_name)

        formulation_mode = self._normalize_formulation_mode(
            getattr(settings, "formulation_mode", "projected_wrapper")
        )
        if hasattr(opts, "formulation_mode") and hasattr(self._module, "FormulationMode"):
            enum_name = "Direct" if formulation_mode == "direct" else "ProjectedWrapper"
            if hasattr(self._module.FormulationMode, enum_name):
                opts.formulation_mode = getattr(self._module.FormulationMode, enum_name)
        if hasattr(opts, "direct_formulation_fallback"):
            opts.direct_formulation_fallback = bool(
                getattr(settings, "direct_formulation_fallback", True)
            )
        control_mode, control_sample_time = self._resolve_control_schedule(
            settings=settings,
            circuit_data=circuit_data,
        )
        if hasattr(opts, "control_mode") and hasattr(self._module, "ControlUpdateMode"):
            enum_map = {
                "auto": "Auto",
                "continuous": "Continuous",
                "discrete": "Discrete",
            }
            enum_name = enum_map.get(control_mode, "Auto")
            if hasattr(self._module.ControlUpdateMode, enum_name):
                opts.control_mode = getattr(self._module.ControlUpdateMode, enum_name)
        if hasattr(opts, "control_sample_time"):
            opts.control_sample_time = (
                float(control_sample_time) if control_sample_time is not None else 0.0
            )

        if hasattr(opts, "enable_events"):
            opts.enable_events = bool(getattr(settings, "enable_events", True))
        if hasattr(opts, "max_step_retries"):
            opts.max_step_retries = max(0, int(getattr(settings, "max_step_retries", 8)))
        if hasattr(opts, "enable_losses"):
            opts.enable_losses = bool(getattr(settings, "enable_losses", True))

        thermal_cfg = getattr(opts, "thermal", None)
        if thermal_cfg is not None:
            if hasattr(thermal_cfg, "ambient"):
                thermal_cfg.ambient = float(getattr(settings, "thermal_ambient", 25.0))
            if hasattr(thermal_cfg, "enable"):
                thermal_cfg.enable = bool(getattr(settings, "enable_losses", True))
            if hasattr(thermal_cfg, "default_rth"):
                thermal_cfg.default_rth = max(
                    0.0,
                    float(getattr(settings, "thermal_default_rth", 1.0)),
                )
            if hasattr(thermal_cfg, "default_cth"):
                thermal_cfg.default_cth = max(
                    0.0,
                    float(getattr(settings, "thermal_default_cth", 0.1)),
                )
            if hasattr(thermal_cfg, "policy") and hasattr(self._module, "ThermalCouplingPolicy"):
                policy = self._normalize_thermal_policy(
                    getattr(settings, "thermal_policy", "loss_with_temperature_scaling")
                )
                enum_name = "LossOnly" if policy == "loss_only" else "LossWithTemperatureScaling"
                if hasattr(self._module.ThermalCouplingPolicy, enum_name):
                    thermal_cfg.policy = getattr(self._module.ThermalCouplingPolicy, enum_name)

        if hasattr(opts, "switching_energy") and circuit_data is not None:
            opts.switching_energy = self._build_switching_energy_map(circuit_data)
        if hasattr(opts, "switching_energy_surfaces") and circuit_data is not None:
            opts.switching_energy_surfaces = self._build_switching_energy_surface_map(circuit_data)

        if hasattr(opts, "thermal_devices") and circuit_data is not None:
            opts.thermal_devices = self._build_thermal_device_map(circuit_data, settings)

        # Averaged converter mode (pulsim >= 0.7.0)
        averaged_options_dict = getattr(settings, "averaged_options", None)
        if averaged_options_dict and hasattr(self._module, "AveragedConverterOptions"):
            try:
                AvgOpts = self._module.AveragedConverterOptions
                AvgTopology = getattr(self._module, "AveragedConverterTopology", None)
                AvgMode = getattr(self._module, "AveragedOperatingMode", None)
                AvgEnvelope = getattr(self._module, "AveragedEnvelopePolicy", None)

                avg_kwargs: dict[str, Any] = {}
                if AvgTopology and "topology" in averaged_options_dict:
                    try:
                        avg_kwargs["topology"] = AvgTopology[averaged_options_dict["topology"].lower()]
                    except (KeyError, AttributeError):
                        pass
                if AvgMode and "mode" in averaged_options_dict:
                    try:
                        avg_kwargs["mode"] = AvgMode[averaged_options_dict["mode"].lower()]
                    except (KeyError, AttributeError):
                        pass
                if AvgEnvelope and "envelope" in averaged_options_dict:
                    try:
                        avg_kwargs["envelope"] = AvgEnvelope[averaged_options_dict["envelope"].lower()]
                    except (KeyError, AttributeError):
                        pass

                avg_opts_obj = AvgOpts(**avg_kwargs)
                if hasattr(opts, "averaged_converter"):
                    opts.averaged_converter = avg_opts_obj
            except Exception:
                log.debug("Failed to apply averaged_options; skipping", exc_info=True)

        if not using_parser_defaults:
            # Fallback policy: enable transient gmin stepping for switching circuit convergence.
            if hasattr(opts, "fallback_policy"):
                fp = opts.fallback_policy
                if hasattr(fp, "enable_transient_gmin"):
                    fp.enable_transient_gmin = True
                if hasattr(fp, "gmin_retry_threshold"):
                    fp.gmin_retry_threshold = 1
                if hasattr(fp, "gmin_initial"):
                    fp.gmin_initial = 1e-8
                if hasattr(fp, "gmin_max"):
                    fp.gmin_max = 1e-4
                if hasattr(fp, "gmin_growth"):
                    fp.gmin_growth = 10
                if hasattr(fp, "trace_retries"):
                    fp.trace_retries = True

        return opts

    def _run_transient_via_simulator(
        self,
        circuit: Any,
        circuit_data: dict[str, Any],
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        signal_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        result = BackendRunResult()
        for name in signal_names:
            result.signals[name] = []

        callbacks.progress(8.0, "Running transient with SimulationOptions...")
        options = self._build_simulation_options(
            settings,
            dt,
            newton_opts,
            linear_solver,
            circuit_data,
        )
        simulator = self._module.Simulator(circuit, options)
        native_result: Any | None = None
        run_error: Exception | None = None

        def _run_native() -> None:
            nonlocal native_result, run_error
            try:
                native_result = (
                    simulator.run_transient(x0) if x0 is not None else simulator.run_transient()
                )
            except Exception as exc:  # pragma: no cover - delegated backend call
                run_error = exc

        worker = threading.Thread(
            target=_run_native,
            name="pulsim-simulator-transient",
            daemon=True,
        )
        worker.start()

        # The SimulationOptions path is blocking in the backend and does not
        # stream progress. Emit a keepalive progress ramp so GUI users don't
        # see a frozen 5% status on long runs.
        start_time = time.monotonic()
        # Keep progress responsive for long-running simulations:
        # - 0..20s: ramp from 8% to ~82%
        # - >20s: slow tail from ~82% to 89%, leaving visible room for finalize
        primary_span_seconds = 20.0
        tail_span_seconds = 120.0
        while worker.is_alive():
            worker.join(timeout=1.0)
            if worker.is_alive():
                elapsed = time.monotonic() - start_time
                if elapsed <= primary_span_seconds:
                    progress = 8.0 + (elapsed / primary_span_seconds) * 74.0
                else:
                    tail_progress = min(
                        7.0,
                        ((elapsed - primary_span_seconds) / tail_span_seconds) * 7.0,
                    )
                    progress = 82.0 + tail_progress
                progress = min(89.0, progress)
                callbacks.progress(
                    progress,
                    f"Running transient with SimulationOptions... ({elapsed:.0f}s elapsed)",
                )
        worker.join()

        if run_error is not None:
            raise run_error
        if native_result is None:
            result.error_message = "Transient failed: backend returned no result."
            return result

        success = getattr(native_result, "success", True)
        if callable(success):
            success = success()
        message = str(getattr(native_result, "message", "") or "")

        # Respect explicit solver status when available.
        status_value = getattr(native_result, "final_status", None)
        if status_value is not None and hasattr(self._module, "SolverStatus"):
            try:
                status = self._module.SolverStatus(status_value)
                if status != self._module.SolverStatus.Success:
                    success = False
                    if not message:
                        message = getattr(native_result, "status_message", status.name)
            except Exception:
                pass

        if not success:
            result.error_message = message or "Transient failed"
            return result

        times = list(getattr(native_result, "time", []))
        states = list(getattr(native_result, "states", []))
        if not signal_names:
            native_signal_names = list(getattr(native_result, "signal_names", []))
            if native_signal_names:
                signal_names = [self._normalize_signal_name(name) for name in native_signal_names]
                for name in signal_names:
                    result.signals.setdefault(name, [])

        callbacks.progress(84.0, "Finalizing results...")
        self._fill_result_from_samples(
            result,
            times,
            states,
            signal_names,
            callbacks=callbacks,
            progress_start=84.0,
            progress_span=8.0,
            progress_message="Finalizing results...",
        )

        self._merge_native_virtual_probe_channels(circuit, native_result, result)

        if result.time:
            final_sample = {
                name: values[-1]
                for name, values in result.signals.items()
                if values
            }
            callbacks.data_point(result.time[-1], final_sample)

        result.statistics["execution_path"] = "simulator_options"
        for field_name in (
            "total_steps",
            "newton_iterations_total",
            "timestep_rejections",
            "total_time_seconds",
        ):
            value = self._coerce_telemetry_scalar(getattr(native_result, field_name, None))
            if value is not None:
                result.statistics[field_name] = value

        message_value = str(getattr(native_result, "message", "") or "").strip()
        if message_value:
            result.statistics["message"] = message_value

        status_value = getattr(native_result, "final_status", None)
        if status_value is not None:
            status_name = self._coerce_telemetry_scalar(status_value)
            if status_name is None and hasattr(self._module, "SolverStatus"):
                try:
                    status_name = str(self._module.SolverStatus(status_value).name)
                except Exception:
                    status_name = str(status_value)
            if status_name is not None:
                result.statistics["status"] = status_name

        diagnostic_value = getattr(native_result, "diagnostic", None)
        if diagnostic_value is not None:
            diagnostic_name = self._coerce_telemetry_scalar(diagnostic_value)
            if diagnostic_name is None and hasattr(self._module, "SimulationDiagnosticCode"):
                try:
                    diagnostic_name = str(
                        self._module.SimulationDiagnosticCode(diagnostic_value).name
                    )
                except Exception:
                    diagnostic_name = str(diagnostic_value)
            if diagnostic_name is not None:
                result.statistics["diagnostic"] = diagnostic_name

        self._append_electrothermal_statistics(result.statistics, native_result)
        return result

    def _fill_result_from_samples(
        self,
        result: BackendRunResult,
        times: Any,
        states: Any,
        signal_names: list[str],
        *,
        callbacks: BackendCallbacks | None = None,
        progress_start: float = 84.0,
        progress_span: float = 8.0,
        progress_message: str = "Finalizing results...",
    ) -> None:
        """Populate backend result vectors with fast-path NumPy conversion.

        Falls back to a cooperative Python loop when input buffers are ragged.
        """
        time_values: np.ndarray | None = None
        try:
            time_values = np.asarray(times, dtype=np.float64).reshape(-1)
        except Exception:
            time_values = None

        if time_values is not None:
            result.time = time_values.tolist()
        else:
            result.time = [float(value) for value in list(times)]

        sample_count = len(result.time)
        if sample_count == 0:
            return

        try:
            state_matrix = np.asarray(states, dtype=np.float64)
        except Exception:
            state_matrix = None

        if state_matrix is not None:
            if state_matrix.ndim == 1:
                if sample_count == 1:
                    state_matrix = state_matrix.reshape(1, -1)
                elif len(signal_names) == 1 and state_matrix.size >= sample_count:
                    state_matrix = state_matrix.reshape(-1, 1)
            if state_matrix.ndim == 2 and state_matrix.shape[0] >= sample_count:
                usable_cols = min(len(signal_names), int(state_matrix.shape[1]))
                if usable_cols > 0:
                    for idx, name in enumerate(signal_names[:usable_cols]):
                        result.signals[name] = state_matrix[:sample_count, idx].astype(
                            np.float64,
                            copy=False,
                        ).tolist()
                        if callbacks is not None and idx and idx % 8 == 0:
                            progress = progress_start + min(
                                progress_span,
                                (idx / max(usable_cols, 1)) * progress_span,
                            )
                            callbacks.progress(progress, progress_message)
                    if callbacks is not None:
                        callbacks.progress(progress_start + progress_span, progress_message)
                return

        # Ragged fallback with cooperative yields to keep UI responsive.
        for name in signal_names:
            result.signals.setdefault(name, [])
        for sample_index, (t, state) in enumerate(zip(times, states, strict=False)):
            if sample_index >= sample_count:
                break
            result.time[sample_index] = float(t)
            for idx, name in enumerate(signal_names):
                if idx < len(state):
                    result.signals[name].append(float(state[idx]))
            if sample_index and sample_index % 2048 == 0:
                if callbacks is not None:
                    progress = progress_start + min(
                        progress_span,
                        (sample_index / sample_count) * progress_span,
                    )
                    callbacks.progress(progress, progress_message)
                time.sleep(0)
        if callbacks is not None:
            callbacks.progress(progress_start + progress_span, progress_message)

    def _run_transient_once(
        self,
        circuit: Any,
        circuit_data: dict[str, Any],
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run one transient attempt with precomputed solver state."""
        result = BackendRunResult()
        signal_names = self._resolve_signal_names(circuit)
        result.time = []
        for name in signal_names:
            result.signals[name] = []
        attempt_diagnostics: dict[str, Any] = {}

        def _finalize_attempt(run_result: BackendRunResult) -> BackendRunResult:
            if attempt_diagnostics:
                run_result.statistics.update(
                    {
                        key: value
                        for key, value in attempt_diagnostics.items()
                        if key not in run_result.statistics
                    }
                )
            if run_result.error_message:
                return run_result
            self._ensure_virtual_probe_channels(
                circuit,
                run_result,
                signal_names,
                callbacks=callbacks,
                progress_start=92.0,
                progress_span=7.0,
            )
            self._repair_current_probe_channels_from_bypass(circuit, run_result)
            callbacks.progress(100.0, "Simulation complete")
            return run_result

        attempted_streaming = False
        attempted_shared = False
        has_cblock = self._has_component_type(circuit_data, "C_BLOCK")
        if has_cblock:
            strict_result = self._run_cblock_transient_strict(
                circuit,
                circuit_data,
                settings,
                callbacks,
                result,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            return _finalize_attempt(strict_result)

        force_compatibility_path = has_cblock and not self._supports_modern_cblock_transient_path()

        prefer_nonblocking = (
            not force_compatibility_path
            and self._should_prefer_nonblocking_transient(
                settings,
                dt,
                circuit_data=circuit_data,
            )
        )
        if force_compatibility_path:
            callbacks.progress(
                4.0,
                "C-Block detected: using compatibility transient path...",
            )
            attempt_diagnostics["execution_note"] = "cblock_forced_compatibility_path"

        if prefer_nonblocking:
            if hasattr(self._module, "run_transient_streaming"):
                attempted_streaming = True
                streaming_result = self._run_transient_streaming(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                if not streaming_result.error_message:
                    streaming_result.statistics["execution_preference"] = "nonblocking_streaming"
                    return _finalize_attempt(streaming_result)
                if "cancel" in streaming_result.error_message.lower():
                    return streaming_result

            if hasattr(self._module, "run_transient_shared"):
                attempted_shared = True
                shared_result = self._run_transient_shared(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                if not shared_result.error_message:
                    shared_result.statistics["execution_preference"] = "nonblocking_shared"
                    return _finalize_attempt(shared_result)
                if "cancel" in shared_result.error_message.lower():
                    return shared_result

        if not force_compatibility_path and self._should_use_simulation_options(settings):
            try:
                simulator_result = self._run_transient_via_simulator(
                    circuit,
                    circuit_data,
                    settings,
                    callbacks,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                if not simulator_result.error_message:
                    return _finalize_attempt(simulator_result)
                attempt_diagnostics["simulator_options_error"] = simulator_result.error_message
                if "cancel" in simulator_result.error_message.lower():
                    return _finalize_attempt(simulator_result)
                if has_cblock:
                    # Modern C-Block control depends on native transient APIs.
                    # Compatibility run_transient fallback can silently drop
                    # virtual control behavior and yield misleading waveforms.
                    simulator_result.error_message = (
                        "C-Block transient failed on native backend path; "
                        "compatibility fallback disabled for control safety. "
                        f"Backend error: {simulator_result.error_message}"
                    )
                    simulator_result.statistics["cblock_native_path_required"] = True
                    return _finalize_attempt(simulator_result)
                callbacks.progress(
                    5.0,
                    "SimulationOptions path failed; retrying compatibility transient...",
                )
            except Exception as exc:
                attempt_diagnostics["simulator_options_exception"] = str(exc)
                if has_cblock:
                    error_result = BackendRunResult(
                        error_message=(
                            "C-Block transient requires native backend execution path; "
                            f"SimulationOptions raised: {exc}"
                        ),
                    )
                    error_result.statistics["cblock_native_path_required"] = True
                    return _finalize_attempt(error_result)
                callbacks.progress(
                    5.0,
                    "SimulationOptions unavailable; retrying compatibility transient...",
                )

        # Prefer robust run_transient path first to match notebook behavior.
        if hasattr(self._module, "run_transient"):
            chunked_result = self._run_transient_chunked(
                circuit,
                settings,
                callbacks,
                result,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            if not chunked_result.error_message:
                return _finalize_attempt(chunked_result)
            if "cancel" in chunked_result.error_message.lower():
                return chunked_result
            if hasattr(self._module, "run_transient_streaming") and not attempted_streaming:
                callbacks.progress(
                    5.0,
                    "Compatibility transient failed; retrying in streaming mode...",
                )
                attempted_streaming = True
                streaming_result = self._run_transient_streaming(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                if not streaming_result.error_message:
                    streaming_result.statistics["fallback_mode"] = "streaming"
                    streaming_result.statistics["compatibility_error"] = (
                        chunked_result.error_message
                    )
                    return _finalize_attempt(streaming_result)
                streaming_result.error_message = (
                    f"{chunked_result.error_message} | Fallback error: "
                    f"{streaming_result.error_message}"
                )
                return streaming_result
            return chunked_result

        if hasattr(self._module, "run_transient_shared") and not attempted_shared:
            attempted_shared = True
            return _finalize_attempt(self._run_transient_shared(
                circuit, settings, callbacks, result,
                signal_names, dt, x0, newton_opts, linear_solver,
            ))

        if hasattr(self._module, "run_transient_streaming") and not attempted_streaming:
            attempted_streaming = True
            streaming_result = self._run_transient_streaming(
                circuit, settings, callbacks, result,
                signal_names, dt, x0, newton_opts, linear_solver,
            )
            if not streaming_result.error_message:
                return _finalize_attempt(streaming_result)
            if "cancel" in streaming_result.error_message.lower():
                return streaming_result
            return streaming_result

        return _finalize_attempt(self._run_transient_chunked(
            circuit, settings, callbacks, result,
            signal_names, dt, x0, newton_opts, linear_solver,
        ))

    def _run_cblock_transient_strict(
        self,
        circuit: Any,
        circuit_data: dict[str, Any],
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        signal_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run C-Block transient in strict mode without GUI fallback reruns."""
        modern_backend = self._supports_modern_cblock_transient_path()
        has_streaming = hasattr(self._module, "run_transient_streaming")
        has_shared = hasattr(self._module, "run_transient_shared")
        has_chunked = hasattr(self._module, "run_transient")
        can_use_simulator = (
            self._should_use_simulation_options(settings)
            and hasattr(self._module, "SimulationOptions")
            and hasattr(self._module, "Simulator")
        )

        def _tag_error(run_result: BackendRunResult, execution_note: str) -> BackendRunResult:
            run_result.statistics.setdefault("execution_note", execution_note)
            run_result.statistics["cblock_strict_mode"] = True
            if run_result.error_message and "cancel" not in run_result.error_message.lower():
                run_result.error_message = (
                    "C-Block transient failed (strict mode, fallback disabled): "
                    f"{run_result.error_message}"
                )
            return run_result

        if modern_backend:
            if can_use_simulator:
                callbacks.progress(4.0, "C-Block strict mode: running SimulationOptions path...")
                sim_result = self._run_transient_via_simulator(
                    circuit,
                    circuit_data,
                    settings,
                    callbacks,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                return _tag_error(sim_result, "cblock_strict_simulator_options")

            if has_streaming:
                callbacks.progress(4.0, "C-Block strict mode: running native streaming path...")
                streaming_result = self._run_transient_streaming(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                return _tag_error(streaming_result, "cblock_strict_streaming")

            if has_shared:
                callbacks.progress(4.0, "C-Block strict mode: running native shared path...")
                shared_result = self._run_transient_shared(
                    circuit,
                    settings,
                    callbacks,
                    result,
                    signal_names,
                    dt,
                    x0,
                    newton_opts,
                    linear_solver,
                )
                return _tag_error(shared_result, "cblock_strict_shared")

            unavailable = BackendRunResult(
                error_message=(
                    "C-Block strict mode requires native transient API "
                    "(streaming/shared/SimulationOptions) on this backend."
                ),
            )
            return _tag_error(unavailable, "cblock_strict_no_native_path")

        callbacks.progress(4.0, "C-Block strict mode: running compatibility path...")
        if has_chunked:
            chunked_result = self._run_transient_chunked(
                circuit,
                settings,
                callbacks,
                result,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            return _tag_error(chunked_result, "cblock_strict_chunked_legacy")

        if has_streaming:
            streaming_result = self._run_transient_streaming(
                circuit,
                settings,
                callbacks,
                result,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            return _tag_error(streaming_result, "cblock_strict_streaming_legacy")

        if has_shared:
            shared_result = self._run_transient_shared(
                circuit,
                settings,
                callbacks,
                result,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            return _tag_error(shared_result, "cblock_strict_shared_legacy")

        if can_use_simulator:
            sim_result = self._run_transient_via_simulator(
                circuit,
                circuit_data,
                settings,
                callbacks,
                signal_names,
                dt,
                x0,
                newton_opts,
                linear_solver,
            )
            return _tag_error(sim_result, "cblock_strict_simulator_options_legacy")

        unavailable = BackendRunResult(
            error_message=(
                "No transient API available for C-Block execution on this backend."
            ),
        )
        return _tag_error(unavailable, "cblock_strict_no_path_legacy")

    @staticmethod
    def _has_component_type(circuit_data: dict[str, Any] | None, comp_type: str) -> bool:
        if not isinstance(circuit_data, dict):
            return False
        components = circuit_data.get("components", [])
        if not isinstance(components, list):
            return False
        target = str(comp_type or "").strip().upper()
        for component in components:
            if not isinstance(component, dict):
                continue
            current = str(component.get("type", "")).strip().upper()
            if current == target:
                return True
        return False

    def _supports_modern_cblock_transient_path(self) -> bool:
        """Return whether this backend version can safely run C-Block on modern paths."""
        parsed_version = self.info.parsed_version
        if parsed_version is None:
            try:
                parsed_version = BackendVersion.from_string(str(self.info.version))
                self.info.parsed_version = parsed_version
            except ValueError:
                return False
        return parsed_version.is_compatible_with(_CBLOCK_MODERN_TRANSIENT_MIN_BACKEND)

    @staticmethod
    def _safe_cblock_build_name(raw_name: str) -> str:
        name = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in raw_name.strip())
        name = name.strip("_")
        return name or "cblock"

    def _prepare_cblock_runtime_payload(
        self,
        circuit_data: dict[str, Any],
        callbacks: BackendCallbacks,
    ) -> tuple[dict[str, Any], str | None]:
        """Auto-compile C-Block ``source`` into ``lib_path`` when compile API exists."""
        compile_fn = getattr(self._module, "compile_cblock", None)
        if compile_fn is None:
            return circuit_data, None
        if not isinstance(circuit_data, dict):
            return circuit_data, None
        components = circuit_data.get("components")
        if not isinstance(components, list):
            return circuit_data, None

        prepared = copy.deepcopy(circuit_data)
        prepared_components = prepared.get("components")
        if not isinstance(prepared_components, list):
            return circuit_data, None

        compiled_any = False
        cache_root = Path(tempfile.gettempdir()).resolve() / "pulsimgui-cblock-build-cache"

        for comp in prepared_components:
            if not isinstance(comp, dict):
                continue
            if str(comp.get("type", "")).strip().upper() != "C_BLOCK":
                continue

            params = comp.get("parameters")
            if not isinstance(params, dict):
                continue
            source = str(params.get("source", "") or "").strip()
            lib_path = str(params.get("lib_path", "") or "").strip()
            if not source or lib_path:
                continue

            source_path = Path(source).expanduser()
            if not source_path.exists():
                # Contract validator already raises a clear file-not-found error.
                continue
            try:
                resolved_source = source_path.resolve()
                source_mtime = resolved_source.stat().st_mtime_ns
            except OSError:
                continue

            flags_raw = params.get("extra_cflags", [])
            flags: list[str] = []
            if isinstance(flags_raw, list):
                flags = [str(item).strip() for item in flags_raw if str(item).strip()]
            elif isinstance(flags_raw, str):
                flags = [token for token in flags_raw.split() if token]
            cache_key = (
                resolved_source.as_posix(),
                int(source_mtime),
                tuple(flags),
            )

            cached_lib = self._cblock_autobuild_cache.get(cache_key, "")
            built_lib_path: Path
            if cached_lib and Path(cached_lib).exists():
                built_lib_path = Path(cached_lib)
            else:
                try:
                    cache_root.mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
                try:
                    built_lib = compile_fn(
                        resolved_source,
                        output_dir=cache_root,
                        name=self._safe_cblock_build_name(str(comp.get("name") or "cblock")),
                        extra_cflags=flags or None,
                    )
                    built_lib_path = Path(built_lib).expanduser().resolve()
                except Exception as exc:
                    details: list[str] = [str(exc)]
                    compiler_path = str(getattr(exc, "compiler_path", "") or "").strip()
                    stderr_output = str(getattr(exc, "stderr_output", "") or "").strip()
                    if compiler_path:
                        details.append(f"Compiler: {compiler_path}")
                    if stderr_output:
                        details.append(stderr_output)
                    return prepared, (
                        "C-Block auto-compilation failed; install a supported C compiler "
                        "or provide 'lib_path'.\n"
                        + "\n".join(details)
                    )

                self._cblock_autobuild_cache[cache_key] = built_lib_path.as_posix()

            params["lib_path"] = built_lib_path.as_posix()
            params["source"] = ""
            params["implementation"] = "library"
            compiled_any = True

        if compiled_any:
            callbacks.progress(
                2.5,
                "C-Block source detected: auto-compiling with host toolchain...",
            )
        return prepared, None

    def _should_prefer_nonblocking_transient(
        self,
        settings: SimulationSettings,
        dt: float,
        *,
        circuit_data: dict[str, Any] | None = None,
    ) -> bool:
        """Prefer shared/streaming APIs for runs that can stall UI responsiveness."""
        duration = max(0.0, float(getattr(settings, "t_stop", 0.0)) - float(getattr(settings, "t_start", 0.0)))
        if dt <= 0.0:
            return duration >= 0.5
        estimated_steps = int(duration / dt) if duration > 0.0 else 0
        if duration >= 0.5 or estimated_steps >= 200_000:
            return True

        # Medium-size runs can still lock the UI when the backend path keeps the GIL
        # (notably control + losses/thermal validation setups).
        if estimated_steps >= 10_000:
            return True

        if circuit_data and estimated_steps >= 2_000:
            components = (
                circuit_data.get("components", [])
                if isinstance(circuit_data, dict)
                else []
            )
            has_cblock = any(
                str(comp.get("type", "")).strip().upper() == "C_BLOCK"
                for comp in components
            )
            if has_cblock:
                return True

        return False

    def _build_transient_retry_profiles(
        self,
        settings: SimulationSettings,
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

    def _build_cblock_strict_retry_profiles(
        self,
        settings: SimulationSettings,
    ) -> list[_TransientRetryProfile]:
        """Build strict-mode numeric retries for C-Block transient convergence."""
        base_iterations = max(1, int(getattr(settings, "max_newton_iterations", 50)))
        configured_step = float(getattr(settings, "max_voltage_step", 5.0))
        safe_step = configured_step if configured_step > 0 else 5.0

        return [
            _TransientRetryProfile(name="default"),
            _TransientRetryProfile(
                name="cblock-gmin-seed",
                dc_strategy="gmin",
                min_newton_iterations=max(base_iterations, 160),
                force_voltage_limiting=True,
                max_voltage_step=min(safe_step, 3.0),
            ),
            _TransientRetryProfile(
                name="cblock-source-half-step",
                dc_strategy="source",
                min_newton_iterations=max(base_iterations, 220),
                force_voltage_limiting=True,
                max_voltage_step=min(safe_step, 2.0),
                dt_scale=0.5,
            ),
            _TransientRetryProfile(
                name="cblock-pseudo-quarter-step",
                dc_strategy="pseudo",
                min_newton_iterations=max(base_iterations, 280),
                force_voltage_limiting=True,
                max_voltage_step=min(safe_step, 1.5),
                dt_scale=0.25,
            ),
        ]

    def _apply_transient_retry_profile(
        self,
        settings: SimulationSettings,
        profile: _TransientRetryProfile,
    ) -> SimulationSettings:
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
            "max iterations",
            "transient failed",
            "time step too small",
            "timestep too small",
        )
        return any(indicator in lowered for indicator in indicators)

    @staticmethod
    def _unpack_streaming_transient_result(
        raw_output: Any,
    ) -> tuple[Any, Any, bool, str, dict[str, Any] | None]:
        """Unpack streaming API output with backward/forward-compatible tuple parsing."""
        if not isinstance(raw_output, (tuple, list)):
            raise TypeError("run_transient_streaming returned a non-iterable payload")
        if len(raw_output) < 4:
            raise TypeError("run_transient_streaming returned an invalid tuple payload")

        times = raw_output[0]
        states = raw_output[1]
        success = bool(raw_output[-2])
        message = str(raw_output[-1] or "")

        virtual_channels: dict[str, Any] | None = None
        for extra in raw_output[2:-2]:
            if not isinstance(extra, dict):
                continue
            if any(isinstance(value, (list, tuple, np.ndarray)) for value in extra.values()):
                virtual_channels = dict(extra)
                break

        return times, states, success, message, virtual_channels

    @staticmethod
    def _merge_streaming_virtual_channels(
        result: BackendRunResult,
        virtual_channels: dict[str, Any],
    ) -> None:
        """Merge virtual channel series returned directly by streaming APIs."""
        if not result.time or not isinstance(virtual_channels, dict):
            return

        sample_count = len(result.time)
        merged_names: set[str] = set()
        for raw_name, raw_series in virtual_channels.items():
            channel_name = str(raw_name or "").strip()
            if not channel_name or raw_series is None:
                continue
            if not isinstance(raw_series, (list, tuple, np.ndarray)):
                continue

            values: list[float] = []
            for item in list(raw_series)[:sample_count]:
                try:
                    values.append(float(item))
                except (TypeError, ValueError):
                    values.append(0.0)
            if not values:
                continue
            if len(values) < sample_count:
                values.extend([values[-1]] * (sample_count - len(values)))
            result.signals[channel_name] = values
            merged_names.add(channel_name)

        if not merged_names:
            return
        existing_names = result.statistics.get("virtual_channel_names")
        names = set(existing_names) if isinstance(existing_names, list) else set()
        names.update(merged_names)
        result.statistics["virtual_channel_names"] = sorted(names)

    def _run_transient_streaming(
        self,
        circuit: Any,
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        signal_names: list[str],
        dt: float,
        x0: Any,
        newton_opts: Any,
        linear_solver: Any | None,
    ) -> BackendRunResult:
        """Run transient simulation using streaming API with real-time callbacks."""
        last_progress_emit_ts = 0.0
        last_progress_value = -1.0

        def data_callback(t: float, state_dict: dict) -> None:
            """Called by C++ backend for progress - we ignore the data here.

            The actual data comes from the final returned arrays which have
            full resolution. We just use this callback to trigger UI updates.
            """
            _ = (t, state_dict)

        def progress_callback(percent: float, message: str) -> None:
            """Called by C++ backend for progress updates."""
            nonlocal last_progress_emit_ts, last_progress_value
            # Map backend progress (0-100) to solver stage range (8-80)
            mapped_progress = 8.0 + (percent / 100.0) * 72.0
            now = time.monotonic()
            should_emit = (
                last_progress_emit_ts <= 0.0
                or (now - last_progress_emit_ts) >= 0.08
                or abs(mapped_progress - last_progress_value) >= 0.75
                or percent >= 99.0
            )
            if should_emit:
                callbacks.progress(mapped_progress, message)
                last_progress_emit_ts = now
                last_progress_value = mapped_progress

        def cancel_check() -> bool:
            """Called by C++ backend to check cancellation."""
            return callbacks.check_cancelled()

        callbacks.progress(8.0, "Running simulation...")

        # Use fewer callbacks (50) to reduce GIL overhead
        # The returned data will have full resolution
        total_steps = max(1, int((settings.t_stop - settings.t_start) / dt))
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
        try:
            stream_output = self._module.run_transient_streaming(*transient_args)
            times, states, success, message, virtual_channels = (
                self._unpack_streaming_transient_result(stream_output)
            )
        except TypeError as exc:
            # Some backend variants require explicit x0 in streaming API.
            # Retry once with a synthesized state vector for compatibility.
            if x0 is not None:
                raise
            retry_args = self._compose_transient_args(
                circuit=circuit,
                settings=settings,
                dt=dt,
                x0=self._ensure_state_vector(x0, len(signal_names)),
                newton_opts=newton_opts,
                linear_solver=linear_solver,
            )
            retry_args.extend([data_callback, progress_callback, cancel_check, emit_interval])
            try:
                stream_output = self._module.run_transient_streaming(*retry_args)
                times, states, success, message, virtual_channels = (
                    self._unpack_streaming_transient_result(stream_output)
                )
            except TypeError as err:
                raise exc from err

        if not success:
            result.error_message = message
            return result
        result.error_message = ""

        callbacks.progress(84.0, "Finalizing results...")
        self._fill_result_from_samples(
            result,
            times,
            states,
            signal_names,
            callbacks=callbacks,
            progress_start=84.0,
            progress_span=8.0,
            progress_message="Finalizing results...",
        )
        if virtual_channels:
            self._merge_streaming_virtual_channels(result, virtual_channels)

        # Final data point
        if result.time:
            final_sample = {name: values[-1] for name, values in result.signals.items()}
            callbacks.data_point(result.time[-1], final_sample)

        return result

    def _run_transient_shared(
        self,
        circuit: Any,
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        signal_names: list[str],
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
        callbacks.progress(8.0, "Preparing shared memory buffers...")

        # Calculate buffer size (add 20% margin for safety)
        total_steps = int((settings.t_stop - settings.t_start) / dt)
        buffer_size = int(total_steps * 1.2) + 100
        num_signals = len(signal_names)

        # Pre-allocate numpy arrays (shared memory buffers)
        time_buffer = np.zeros(buffer_size, dtype=np.float64)
        states_buffer = np.zeros((buffer_size, num_signals), dtype=np.float64)
        status_buffer = np.zeros(3, dtype=np.int64)
        # status_buffer[0] = current_index (steps completed)
        # status_buffer[1] = status (0=running, 1=completed, 2=error, 3=cancelled)
        # status_buffer[2] = error_code

        # Get initial state
        if x0 is None:
            x0 = np.zeros(num_signals)

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
        last_progress_emit_ts = 0.0
        last_progress_value = 10.0

        while status_buffer[1] == 0:  # While running
            # Check for pause
            callbacks.wait_if_paused()

            # Get current progress
            current_index = int(status_buffer[0])

            if current_index > last_index:
                # Calculate progress percentage
                progress = 12.0 + (current_index / total_steps) * 68.0
                progress = min(80.0, progress)

                # Get current time value for message
                if current_index > 0 and current_index < buffer_size:
                    current_time = time_buffer[current_index - 1]
                    now = time.monotonic()
                    should_emit = (
                        last_progress_emit_ts <= 0.0
                        or (now - last_progress_emit_ts) >= 0.08
                        or abs(progress - last_progress_value) >= 0.75
                        or current_index >= total_steps
                    )
                    if should_emit:
                        callbacks.progress(progress, f"Simulating: t={current_time*1e6:.1f}µs")
                        last_progress_emit_ts = now
                        last_progress_value = progress

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
        result.error_message = ""

        if final_index > last_index:
            last_index = final_index

        callbacks.progress(84.0, "Finalizing results...")
        self._fill_result_from_samples(
            result,
            time_buffer[:final_index],
            states_buffer[:final_index, :],
            signal_names,
            callbacks=callbacks,
            progress_start=84.0,
            progress_span=8.0,
            progress_message="Finalizing results...",
        )

        # Send final complete data
        if result.time:
            final_sample = {name: values[-1] for name, values in result.signals.items()}
            callbacks.data_point(result.time[-1], final_sample)

        return result

    def _run_transient_chunked(
        self,
        circuit: Any,
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
        result: BackendRunResult,
        signal_names: list[str],
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
        times, states, success, message = self._invoke_run_transient(transient_args, settings)

        if not success:
            result.error_message = message
            return result
        result.error_message = ""

        callbacks.progress(60.0, "Processing results...")

        # Convert to numpy arrays for efficient transfer
        total_points = len(times)
        time_array = np.array([float(t) for t in times], dtype=np.float64)

        callbacks.progress(70.0, f"Converting {total_points:,} data points...")

        signal_arrays = {}
        for i, name in enumerate(signal_names):
            signal_arrays[name] = np.array(
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
                return self._run_dc_top_level(circuit, settings, circuit_data)

            # Try simulator-based API
            if hasattr(self._module, "Simulator"):
                simulator_result = self._run_dc_via_simulator(circuit, settings, circuit_data)
                if simulator_result is not None:
                    return simulator_result

            # Try top-level solve_dc
            if hasattr(self._module, "solve_dc"):
                newton_opts = self._build_dc_options(settings)
                native_result = self._module.solve_dc(circuit, newton_opts)
                return self._convert_newton_result(native_result, circuit, circuit_data)

            # Try v1 namespace (DCConvergenceSolver)
            if hasattr(self._module, "v1") and hasattr(self._module.v1, "DCConvergenceSolver"):
                newton_opts = self._build_dc_options(settings)
                return self._run_dc_v1(circuit, settings, newton_opts, circuit_data)

            # Try v2 namespace
            if hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
                newton_opts = self._build_dc_options(settings)
                native_result = self._module.v2.solve_dc(circuit, newton_opts)
                return self._convert_newton_result(native_result, circuit, circuit_data)

            return DCResult(
                error_message="No DC solver available in backend",
                convergence_info=ConvergenceInfo(converged=False, failure_reason="No solver"),
            )

        except Exception as exc:
            return DCResult(
                error_message=str(exc),
                convergence_info=ConvergenceInfo(converged=False, failure_reason=str(exc)),
            )

    def _run_dc_via_simulator(
        self,
        circuit: Any,
        settings: DCSettings,
        circuit_data: dict | None = None,
    ) -> DCResult | None:
        """Try DC operating point through Simulator APIs.

        Returns:
            DCResult when simulator path succeeds, otherwise None.
        """
        simulator_cls = getattr(self._module, "Simulator", None)
        if simulator_cls is None:
            return None

        try:
            simulator = simulator_cls(circuit)
        except Exception:
            return None

        try:
            if hasattr(simulator, "dc_operating_point"):
                native_result = simulator.dc_operating_point()
                return self._convert_newton_result(native_result, circuit, circuit_data)
            if hasattr(simulator, "solve_dc"):
                newton_opts = self._build_dc_options(settings)
                native_result = simulator.solve_dc(newton_opts)
                return self._convert_newton_result(native_result, circuit, circuit_data)
        except Exception:
            return None

        return None

    def _run_dc_top_level(
        self,
        circuit: Any,
        settings: DCSettings,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Run DC analysis using top-level dc_operating_point function."""
        # Build DCConvergenceConfig
        config = self._module.DCConvergenceConfig()

        strategy_name = str(settings.strategy or "auto").strip().lower()
        if hasattr(self._module, "DCStrategy"):
            strategy_enum = {
                "auto": getattr(self._module.DCStrategy, "Auto", None),
                "direct": getattr(self._module.DCStrategy, "Direct", None),
                "gmin": getattr(self._module.DCStrategy, "GminStepping", None),
                "source": getattr(self._module.DCStrategy, "SourceStepping", None),
                "pseudo": getattr(self._module.DCStrategy, "PseudoTransient", None),
            }.get(strategy_name)
            if strategy_enum is not None:
                config.strategy = strategy_enum

        if strategy_name == "source" and hasattr(config, "source_config"):
            config.source_config.max_steps = settings.source_steps

        if strategy_name == "gmin" and hasattr(config, "gmin_config"):
            config.gmin_config.initial_gmin = settings.gmin_initial
            config.gmin_config.final_gmin = settings.gmin_final

        # Run DC analysis
        dc_result = self._module.dc_operating_point(circuit, config)

        # Convert to DCResult
        return self._convert_dc_analysis_result(dc_result, circuit, circuit_data)

    def _run_dc_v1(
        self,
        circuit: Any,
        settings: DCSettings,
        newton_opts: Any,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Run DC analysis using v1 DCConvergenceSolver."""
        v1 = self._module.v1

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

        return self._convert_dc_result(native_result, circuit, circuit_data)

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

    def _convert_dc_analysis_result(
        self,
        dc_result: Any,
        circuit: Any,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Convert PulsimCore DCAnalysisResult to GUI DCResult."""
        node_voltages: dict[str, float] = {}
        branch_currents: dict[str, float] = {}
        power_dissipation: dict[str, float] = {}

        # Extract solution from newton_result
        newton_result = getattr(dc_result, "newton_result", None)
        solution = getattr(newton_result, "solution", None) if newton_result else None

        if solution is not None:
            node_voltages, branch_currents = self._extract_dc_solution_maps(circuit, solution)
            node_names = [key[2:-1] for key in node_voltages if key.startswith("V(") and key.endswith(")")]
        else:
            node_names = []
        power_dissipation.update(
            self._extract_dc_power_result(dc_result)
        )
        if circuit_data is not None:
            power_dissipation.update(
                self._estimate_dc_power_dissipation(
                    circuit_data,
                    node_voltages,
                    branch_currents,
                )
            )

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

    def _convert_newton_result(
        self,
        native_result: Any,
        circuit: Any,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Convert PulsimCore NewtonResult to GUI DCResult."""
        return self._convert_dc_result(native_result, circuit, circuit_data)

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

    def _convert_dc_result(
        self,
        native_result: Any,
        circuit: Any,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Convert PulsimCore DC result to GUI DCResult."""
        node_voltages: dict[str, float] = {}
        branch_currents: dict[str, float] = {}
        power_dissipation: dict[str, float] = {}

        # Extract solution vector
        solution = getattr(native_result, "solution", None)
        if solution is not None:
            node_voltages, branch_currents = self._extract_dc_solution_maps(circuit, solution)

        # Extract branch currents if available
        if hasattr(native_result, "branch_currents"):
            for name, current in native_result.branch_currents.items():
                branch_currents[f"I({name})"] = float(current)
        power_dissipation.update(self._extract_dc_power_result(native_result))
        if circuit_data is not None:
            power_dissipation.update(
                self._estimate_dc_power_dissipation(
                    circuit_data,
                    node_voltages,
                    branch_currents,
                )
            )

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

    @staticmethod
    def _resolve_index_count(circuit: Any, attr_name: str) -> int:
        """Resolve numeric node/branch counts from runtime circuit APIs."""
        attr = getattr(circuit, attr_name, None)
        if callable(attr):
            try:
                return max(0, int(attr()))
            except Exception:
                return 0
        if attr is None:
            return 0
        try:
            return max(0, int(attr))
        except Exception:
            return 0

    @classmethod
    def _extract_dc_solution_maps(
        cls,
        circuit: Any,
        solution: Any,
    ) -> tuple[dict[str, float], dict[str, float]]:
        """Convert a DC solution vector into node voltages and branch currents."""
        values = [float(value) for value in solution]
        if not values:
            return {}, {}

        node_voltages: dict[str, float] = {}
        branch_currents: dict[str, float] = {}

        signal_names_attr = getattr(circuit, "signal_names", None)
        if signal_names_attr is not None:
            try:
                raw_signal_names = signal_names_attr() if callable(signal_names_attr) else signal_names_attr
            except Exception:
                raw_signal_names = []
            if raw_signal_names:
                limit = min(len(values), len(raw_signal_names))
                for index in range(limit):
                    name = cls._normalize_signal_name(raw_signal_names[index])
                    if name.upper().startswith("I("):
                        branch_currents[name] = values[index]
                    else:
                        node_voltages[name] = values[index]
                if node_voltages or branch_currents:
                    return node_voltages, branch_currents

        node_count = cls._resolve_index_count(circuit, "num_nodes")
        branch_count = cls._resolve_index_count(circuit, "num_branches")
        if node_count <= 0 and branch_count > 0:
            node_count = max(0, len(values) - branch_count)

        node_names = cls._resolve_node_names(circuit, node_count or len(values))
        node_count = min(len(values), node_count or len(node_names))
        for index in range(node_count):
            node_name = node_names[index] if index < len(node_names) else f"node_{index}"
            node_voltages[f"V({node_name})"] = values[index]

        remaining = max(0, len(values) - node_count)
        branch_count = min(remaining, branch_count or remaining)
        for index in range(branch_count):
            branch_currents[f"I(branch{index})"] = values[node_count + index]

        return node_voltages, branch_currents

    @staticmethod
    def _parse_channel_name(key: str, prefix: str) -> str:
        text = str(key or "").strip()
        if text.upper().startswith(f"{prefix}(") and text.endswith(")"):
            return text[2:-1].strip()
        return text

    @classmethod
    def _canonical_channel_lookup(cls, values: dict[str, float], prefix: str) -> dict[str, float]:
        lookup: dict[str, float] = {}
        for raw_key, raw_value in values.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            key = cls._parse_channel_name(raw_key, prefix)
            if not key:
                continue
            normalized = key.strip()
            lookup.setdefault(normalized, value)
            lookup.setdefault(normalized.lower(), value)
        return lookup

    @classmethod
    def _extract_dc_power_result(cls, source: Any) -> dict[str, float]:
        """Extract native DC power maps when backend exposes them."""
        result: dict[str, float] = {}
        for attr_name in ("power_dissipation", "component_power", "device_power", "power"):
            raw_map = getattr(source, attr_name, None)
            if raw_map is None:
                continue
            if callable(raw_map):
                try:
                    raw_map = raw_map()
                except Exception:
                    continue
            if not isinstance(raw_map, dict):
                continue
            for raw_key, raw_value in raw_map.items():
                try:
                    value = float(raw_value)
                except (TypeError, ValueError):
                    continue
                key = str(raw_key or "").strip()
                if not key:
                    continue
                label = key if key.upper().startswith("P(") else f"P({key})"
                result[label] = value
        return result

    @classmethod
    def _estimate_dc_power_dissipation(
        cls,
        circuit_data: dict | None,
        node_voltages: dict[str, float],
        branch_currents: dict[str, float],
    ) -> dict[str, float]:
        """Estimate component power from DC operating point when backend has no native map."""
        if not isinstance(circuit_data, dict):
            return {}

        components = circuit_data.get("components", []) or []
        if not components:
            return {}

        voltage_lookup = cls._canonical_channel_lookup(node_voltages, "V")
        current_lookup = cls._canonical_channel_lookup(branch_currents, "I")
        power_map: dict[str, float] = {}

        for component in components:
            if not isinstance(component, dict):
                continue
            comp_id = str(component.get("id") or "").strip()
            comp_name = str(component.get("name") or comp_id).strip()
            if not comp_name:
                continue

            pin_nodes = component.get("pin_nodes") or []
            if not isinstance(pin_nodes, list):
                pin_nodes = []
            v_drop: float | None = None
            if len(pin_nodes) >= 2:
                n_pos = str(pin_nodes[0] or "").strip()
                n_neg = str(pin_nodes[1] or "").strip()
                v_pos = cls._lookup_canonical_value(voltage_lookup, n_pos)
                v_neg = cls._lookup_canonical_value(voltage_lookup, n_neg)
                if v_pos is not None and v_neg is not None:
                    v_drop = float(v_pos) - float(v_neg)

            current_value: float | None = None
            for token in (
                comp_name,
                comp_name.lower(),
                comp_id,
                comp_id.lower(),
            ):
                if not token:
                    continue
                if token in current_lookup:
                    current_value = current_lookup[token]
                    break
            if current_value is None:
                for raw_key, value in current_lookup.items():
                    if raw_key.endswith(f"({comp_name.lower()})") or raw_key.startswith(f"{comp_name.lower()}_"):
                        current_value = value
                        break

            params = component.get("parameters") if isinstance(component.get("parameters"), dict) else {}
            component_type = str(component.get("type") or "").strip().lower()

            power_value: float | None = None
            if v_drop is not None and current_value is not None:
                power_value = float(v_drop) * float(current_value)
            elif component_type == "resistor":
                resistance = params.get("resistance")
                try:
                    resistance_value = float(resistance)
                except (TypeError, ValueError):
                    resistance_value = 0.0
                if resistance_value > 0.0 and v_drop is not None:
                    power_value = (float(v_drop) ** 2) / resistance_value
            elif component_type == "current_source" and v_drop is not None:
                waveform = params.get("waveform")
                if isinstance(waveform, dict) and str(waveform.get("type", "")).strip().lower() == "dc":
                    try:
                        source_current = float(waveform.get("value", 0.0))
                    except (TypeError, ValueError):
                        source_current = 0.0
                    power_value = float(v_drop) * source_current

            if power_value is None or not math.isfinite(power_value):
                continue

            power_map[f"P({comp_name})"] = float(power_value)

        return power_map

    @staticmethod
    def _lookup_canonical_value(lookup: dict[str, float], key: str) -> float | None:
        """Resolve a canonicalized lookup key while preserving zero values."""
        if key in lookup:
            return lookup[key]
        lowered = key.lower()
        if lowered in lookup:
            return lookup[lowered]
        return None

    @staticmethod
    def _resolve_node_names(circuit: Any, solution_size: int = 0) -> list[str]:
        """Resolve stable node labels from runtime circuit APIs."""
        for accessor in ("node_names", "get_node_names"):
            node_names_attr = getattr(circuit, accessor, None)
            if node_names_attr is None:
                continue
            try:
                raw_node_names = node_names_attr() if callable(node_names_attr) else node_names_attr
            except Exception:
                continue
            if raw_node_names:
                return [str(name) for name in raw_node_names]

        node_count = 0
        num_nodes_attr = getattr(circuit, "num_nodes", None)
        if callable(num_nodes_attr):
            try:
                node_count = int(num_nodes_attr())
            except Exception:
                node_count = 0
        elif num_nodes_attr is not None:
            try:
                node_count = int(num_nodes_attr)
            except Exception:
                node_count = 0

        if node_count <= 0 and solution_size > 0:
            node_count = int(solution_size)

        return [f"node_{idx}" for idx in range(max(0, node_count))]

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

            native_result = self._run_ac_native(circuit, ac_opts)
            if native_result is None:
                return ACResult(error_message="No AC analysis API available")

            return self._convert_ac_result(native_result, settings)

        except Exception as exc:
            return ACResult(error_message=str(exc))

    def _run_ac_native(self, circuit: Any, ac_opts: Any) -> Any | None:
        """Run AC analysis across backend API variants."""
        if hasattr(self._module, "run_ac"):
            return self._module.run_ac(circuit, ac_opts)

        if hasattr(self._module, "run_ac_analysis"):
            return self._module.run_ac_analysis(circuit, ac_opts)

        if hasattr(self._module, "run_small_signal"):
            return self._module.run_small_signal(circuit, ac_opts)

        if hasattr(self._module, "ACAnalysis"):
            analyzer = self._module.ACAnalysis(circuit)
            if hasattr(analyzer, "run"):
                return analyzer.run(ac_opts)
            if hasattr(analyzer, "analyze"):
                return analyzer.analyze(ac_opts)

        simulator_cls = getattr(self._module, "Simulator", None)
        if simulator_cls is not None:
            try:
                simulator = simulator_cls(circuit)
            except Exception:
                simulator = None
            if simulator is not None:
                if hasattr(simulator, "run_ac"):
                    return simulator.run_ac(ac_opts)
                if hasattr(simulator, "run_ac_analysis"):
                    return simulator.run_ac_analysis(ac_opts)
                if hasattr(simulator, "run_small_signal"):
                    return simulator.run_small_signal(ac_opts)

        return None

    def _build_ac_options(self, settings: ACSettings) -> Any:
        """Build PulsimCore AC options from ACSettings."""
        if hasattr(self._module, "ACOptions"):
            opts = self._module.ACOptions()
        else:
            opts = type("ACOptions", (), {})()

        # Calculate total points based on points_per_decade
        decades = math.log10(settings.f_stop / max(settings.f_start, 0.001))
        npoints = max(1, int(decades * settings.points_per_decade))

        # Frequency range aliases across versions
        for attr in ("fstart", "f_start", "f_min", "start_frequency", "frequency_start"):
            if hasattr(opts, attr):
                setattr(opts, attr, settings.f_start)
                break
        for attr in ("fstop", "f_stop", "f_max", "stop_frequency", "frequency_stop"):
            if hasattr(opts, attr):
                setattr(opts, attr, settings.f_stop)
                break

        # Point count aliases
        if hasattr(opts, "npoints"):
            opts.npoints = npoints
        elif hasattr(opts, "num_points"):
            opts.num_points = npoints
        elif hasattr(opts, "points"):
            opts.points = npoints
        elif hasattr(opts, "points_per_decade"):
            opts.points_per_decade = settings.points_per_decade

        # Set sweep type to Decade if available
        if hasattr(opts, "sweep_type") and hasattr(self._module, "FrequencySweepType"):
            opts.sweep_type = self._module.FrequencySweepType.Decade
        elif hasattr(opts, "sweep_mode") and hasattr(self._module, "FrequencySweepType"):
            opts.sweep_mode = self._module.FrequencySweepType.Decade

        if hasattr(opts, "input_source"):
            opts.input_source = settings.input_source
        if hasattr(opts, "output_nodes"):
            opts.output_nodes = list(settings.output_nodes)

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
        """Run thermal simulation using backend-native ThermalSimulator APIs only."""
        if not self.has_capability("thermal"):
            return ThermalResult(
                error_message="Thermal simulation not supported by this backend version",
                is_synthetic=False,
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            return ThermalResult(error_message=str(exc), is_synthetic=False)

        try:
            direct_result = self._run_thermal_native(circuit, electrical_result, settings)
            if direct_result is not None:
                return direct_result

            return ThermalResult(
                error_message=(
                    "No compatible native thermal API available for this backend version. "
                    "Upgrade backend thermal support to use thermal analysis."
                ),
                is_synthetic=False,
            )

        except Exception as exc:
            return ThermalResult(error_message=str(exc), is_synthetic=False)

    def _run_thermal_native(
        self,
        circuit: Any,
        electrical_result: TransientResult,
        settings: ThermalSettings,
    ) -> ThermalResult | None:
        """Run thermal through circuit-coupled backend APIs when available."""
        simulator_cls = getattr(self._module, "ThermalSimulator", None)
        if simulator_cls is None:
            return None

        try:
            thermal_sim = simulator_cls(circuit)
        except Exception:
            return None

        if hasattr(thermal_sim, "set_ambient_temperature"):
            thermal_sim.set_ambient_temperature(settings.ambient_temperature)
        elif hasattr(thermal_sim, "set_ambient"):
            thermal_sim.set_ambient(settings.ambient_temperature)

        if hasattr(thermal_sim, "include_switching_losses"):
            try:
                thermal_sim.include_switching_losses = settings.include_switching_losses
            except Exception:
                pass
        if hasattr(thermal_sim, "include_conduction_losses"):
            try:
                thermal_sim.include_conduction_losses = settings.include_conduction_losses
            except Exception:
                pass
        if hasattr(thermal_sim, "set_thermal_network"):
            try:
                thermal_sim.set_thermal_network(settings.thermal_network)
            except Exception:
                pass
        elif hasattr(thermal_sim, "thermal_network"):
            try:
                thermal_sim.thermal_network = settings.thermal_network
            except Exception:
                pass

        if not hasattr(thermal_sim, "run"):
            return None

        native_result = thermal_sim.run(electrical_result.time, electrical_result.signals)
        return self._convert_thermal_result(native_result, settings)

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
        """Request backend pause for the active simulation execution."""
        controller = self._controller_for(run_id)
        if controller:
            controller.request_pause()

    def request_resume(self, run_id: int | None = None) -> None:
        """Request backend resume for the active simulation execution."""
        controller = self._controller_for(run_id)
        if controller:
            controller.request_resume()

    def request_stop(self, run_id: int | None = None) -> None:
        """Request backend stop for the active simulation execution."""
        controller = self._controller_for(run_id)
        if controller:
            controller.request_stop()

    def run_post_processing(
        self,
        transient_result: TransientResult,
        jobs: list[dict],
    ) -> PostProcessingResult:
        """Run post-processing jobs via pulsim.run_post_processing."""
        if not self.has_capability("post_processing"):
            return PostProcessingResult(
                success=False,
                error_message="Post-processing not supported by this backend version",
            )

        ps = self._module
        try:
            sim_result_cls = getattr(ps, "SimulationResult", None)
            if sim_result_cls is None:
                return PostProcessingResult(
                    success=False,
                    error_message="pulsim.SimulationResult not available",
                )
            ps_result = self._build_post_processing_input(sim_result_cls, transient_result)

            parse_fn = getattr(ps, "parse_post_processing_yaml", None)
            if callable(parse_fn):
                pp_options = parse_fn({"jobs": jobs})
            else:
                opts_cls = getattr(ps, "PostProcessingOptions", None)
                job_cls = getattr(ps, "PostProcessingJob", None)
                if opts_cls is None or job_cls is None:
                    return PostProcessingResult(
                        success=False,
                        error_message="pulsim.PostProcessingOptions not available",
                    )
                pp_options = opts_cls()
                job_items: list[Any] = []
                for raw_job in jobs:
                    if not isinstance(raw_job, dict):
                        continue
                    job_items.append(self._build_post_processing_job(job_cls, raw_job))
                if hasattr(pp_options, "jobs"):
                    pp_options.jobs = job_items

            ps_pp_result = ps.run_post_processing(ps_result, pp_options)
            return self._map_pp_result(ps_pp_result)

        except Exception as exc:
            log.exception("run_post_processing failed")
            return PostProcessingResult(success=False, error_message=str(exc))

    @staticmethod
    def _build_post_processing_input(sim_result_cls: Any, transient_result: TransientResult) -> Any:
        """Create a backend-compatible SimulationResult-like object for post-processing."""
        base_time = list(transient_result.time)
        base_signals = {str(k): list(v) for k, v in transient_result.signals.items()}

        # Newer Python wrappers often accept kwargs.
        for kwargs in (
            {"time": base_time, "virtual_channels": base_signals},
            {"time": base_time, "signals": base_signals},
            {"time": base_time},
        ):
            try:
                candidate = sim_result_cls(**kwargs)
                try:
                    candidate.virtual_channels = base_signals
                except Exception:
                    pass
                try:
                    candidate.signals = base_signals
                except Exception:
                    pass
                return candidate
            except Exception:
                continue

        # Fallback for pybind classes that require empty init + attribute assignment.
        candidate = sim_result_cls()
        try:
            candidate.time = base_time
        except Exception:
            pass
        try:
            candidate.virtual_channels = base_signals
        except Exception:
            pass
        try:
            candidate.signals = base_signals
        except Exception:
            pass
        return candidate

    @staticmethod
    def _build_post_processing_job(job_cls: Any, payload: dict[str, Any]) -> Any:
        """Create a backend PostProcessingJob handling dataclass/pybind variants."""
        try:
            return job_cls(**payload)
        except Exception:
            job = job_cls()
            for key, value in payload.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            return job

    @staticmethod
    def _map_pp_result(ps_result: Any) -> PostProcessingResult:
        """Map a pulsim PostProcessingResult to the GUI wrapper type."""
        def _field(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        top_success = bool(_field(ps_result, "success", True))
        top_error = str(
            _field(ps_result, "error_message", "")
            or _field(ps_result, "message", "")
            or ""
        ).strip()

        job_results: list[PostProcessingJobResult] = []
        for jr in list(_field(ps_result, "jobs", []) or []):
            scalar_metrics: dict[str, ScalarMetric] = {}
            raw_scalar = _field(jr, "scalar_metrics", {}) or {}
            scalar_entries: list[tuple[str, Any]]
            if isinstance(raw_scalar, dict):
                scalar_entries = list(raw_scalar.items())
            else:
                scalar_entries = []
                for raw_item in list(raw_scalar):
                    metric_name = str(_field(raw_item, "name", "")).strip()
                    scalar_entries.append((metric_name, raw_item))

            for metric_key, raw_m in scalar_entries:
                metric_name = str(_field(raw_m, "name", metric_key)).strip() or str(metric_key).strip()
                metric_value = _optional_float(_field(raw_m, "value", None))
                if not metric_name or metric_value is None:
                    continue
                sm = ScalarMetric(
                    name=metric_name,
                    value=metric_value,
                    unit=str(_field(raw_m, "unit", "") or ""),
                    domain=str(_field(raw_m, "domain", "") or ""),
                    signal_name=str(_field(raw_m, "signal_name", "") or ""),
                    source_signal=str(_field(raw_m, "source_signal", "") or ""),
                )
                scalar_metrics[sm.name] = sm

            spectrum_bins = [
                SpectralBin(
                    frequency_hz=_optional_float(_field(b, "frequency_hz", 0.0)) or 0.0,
                    amplitude=(
                        _optional_float(_field(b, "amplitude", None))
                        or _optional_float(_field(b, "magnitude", None))
                        or 0.0
                    ),
                    phase_deg=_optional_float(_field(b, "phase_deg", 0.0)) or 0.0,
                )
                for b in list(_field(jr, "spectrum_bins", []) or [])
            ]
            harmonics = [
                HarmonicEntry(
                    order=int(
                        _optional_float(_field(h, "order", None))
                        or _optional_float(_field(h, "harmonic_number", None))
                        or 0.0
                    ),
                    frequency_hz=_optional_float(_field(h, "frequency_hz", 0.0)) or 0.0,
                    amplitude=(
                        _optional_float(_field(h, "amplitude", None))
                        or _optional_float(_field(h, "magnitude", None))
                        or 0.0
                    ),
                    phase_deg=_optional_float(_field(h, "phase_deg", 0.0)) or 0.0,
                    amplitude_db=_optional_float(_field(h, "amplitude_db", None)),
                    magnitude_pct_fundamental=_optional_float(
                        _field(h, "magnitude_pct_fundamental", None)
                    ),
                )
                for h in list(_field(jr, "harmonics", []) or [])
            ]
            undefined_metrics = [
                UndefinedMetricEntry(
                    name=str(_field(entry, "name", "") or ""),
                    reason=_enum_name_or_value(_field(entry, "reason", "")),
                    reason_message=str(_field(entry, "reason_message", "") or ""),
                )
                for entry in list(_field(jr, "undefined_metrics", []) or [])
            ]
            job_results.append(PostProcessingJobResult(
                job_id=str(_field(jr, "job_id", "") or ""),
                kind=_enum_name_or_value(_field(jr, "kind", "")),
                success=bool(_field(jr, "success", True)),
                diagnostic=_enum_name_or_value(_field(jr, "diagnostic", "")),
                diagnostic_message=str(_field(jr, "diagnostic_message", "") or ""),
                scalar_metrics=scalar_metrics,
                spectrum_bins=spectrum_bins,
                harmonics=harmonics,
                thd_pct=_optional_float(_field(jr, "thd_pct", None)),
                fundamental_hz=_optional_float(_field(jr, "fundamental_hz", None)),
                average_input_power=_optional_float(_field(jr, "average_input_power", None)),
                average_output_power=_optional_float(_field(jr, "average_output_power", None)),
                efficiency=_optional_float(_field(jr, "efficiency", None)),
                power_factor=_optional_float(_field(jr, "power_factor", None)),
                undefined_metrics=[entry for entry in undefined_metrics if entry.name],
                signal_names=[str(name) for name in list(_field(jr, "signal_names", []) or [])],
                sample_count=int(_optional_float(_field(jr, "sample_count", 0)) or 0),
                runtime_seconds=_optional_float(_field(jr, "runtime_seconds", 0.0)) or 0.0,
            ))

        success = top_success and all(job.success for job in job_results)
        return PostProcessingResult(
            jobs=job_results,
            success=success,
            error_message=top_error,
        )

    def run_frequency_analysis(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> FrequencyAnalysisResult:
        """Run frequency-domain analysis via pulsim.run_frequency_analysis."""
        if not self.has_capability("frequency_analysis"):
            return FrequencyAnalysisResult(
                success=False,
                diagnostic_code="unsupported",
                diagnostic_message="Frequency analysis not supported by this backend version",
            )

        ps = self._module
        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            return FrequencyAnalysisResult(
                success=False,
                diagnostic_code="circuit_error",
                diagnostic_message=str(exc),
            )

        try:
            fa_opts_cls = getattr(ps, "FrequencyAnalysisOptions", None)
            if fa_opts_cls is None:
                return FrequencyAnalysisResult(
                    success=False,
                    diagnostic_code="unsupported",
                    diagnostic_message="pulsim.FrequencyAnalysisOptions not available",
                )

            fa_opts = fa_opts_cls()
            if hasattr(fa_opts, "enabled"):
                fa_opts.enabled = True
            if hasattr(fa_opts, "f_start_hz"):
                fa_opts.f_start_hz = max(float(settings.f_start), 1e-12)
            if hasattr(fa_opts, "f_stop_hz"):
                f_start = max(float(settings.f_start), 1e-12)
                fa_opts.f_stop_hz = max(float(settings.f_stop), f_start * (1.0 + 1e-12))
            if hasattr(fa_opts, "points"):
                f_start = max(float(settings.f_start), 1e-12)
                f_stop = max(float(settings.f_stop), f_start * (1.0 + 1e-12))
                ppd = max(1, int(settings.points_per_decade))
                decades = max(1.0, math.log10(f_stop / f_start))
                fa_opts.points = max(2, int(math.ceil(decades * ppd)) + 1)
            if hasattr(fa_opts, "injection_current_amplitude"):
                amplitude = _optional_float(getattr(settings, "injection_current_amplitude", 1.0))
                fa_opts.injection_current_amplitude = amplitude if amplitude is not None else 1.0

            mode_raw = str(getattr(settings, "mode", "open_loop_transfer") or "open_loop_transfer").strip().lower()
            mode_map = {
                "open_loop_transfer": "OpenLoopTransfer",
                "closed_loop_transfer": "ClosedLoopTransfer",
                "input_impedance": "InputImpedance",
                "output_impedance": "OutputImpedance",
            }
            mode_enum = getattr(ps, "FrequencyAnalysisMode", None)
            mode_name = mode_map.get(mode_raw, "OpenLoopTransfer")
            if mode_enum is not None and hasattr(mode_enum, mode_name) and hasattr(fa_opts, "mode"):
                fa_opts.mode = getattr(mode_enum, mode_name)

            anchor_raw = str(getattr(settings, "anchor_mode", "auto") or "auto").strip().lower()
            anchor_map = {
                "auto": "Auto",
                "dc": "DC",
                "periodic": "Periodic",
                "averaged": "Averaged",
            }
            anchor_enum = getattr(ps, "FrequencyAnchorMode", None)
            anchor_name = anchor_map.get(anchor_raw, "Auto")
            if anchor_enum is not None and hasattr(anchor_enum, anchor_name) and hasattr(fa_opts, "anchor_mode"):
                fa_opts.anchor_mode = getattr(anchor_enum, anchor_name)

            scale_raw = str(getattr(settings, "sweep_scale", "decade") or "decade").strip().lower()
            if scale_raw in {"decade", "log", "logarithmic"}:
                scale_name = "Logarithmic"
            else:
                scale_name = "Linear"
            scale_enum = getattr(ps, "FrequencySweepScale", None)
            if scale_enum is not None and hasattr(scale_enum, scale_name) and hasattr(fa_opts, "sweep_scale"):
                fa_opts.sweep_scale = getattr(scale_enum, scale_name)

            input_hint = str(getattr(settings, "input_source", "") or "").strip()
            output_hint = (
                str(settings.output_nodes[0]).strip()
                if getattr(settings, "output_nodes", None)
                else ""
            )
            inj_positive, inj_negative = self._parse_port_nodes(
                str(getattr(settings, "injection_node", "") or "").strip(),
                default_positive=input_hint or "in",
            )
            out_positive, out_negative = self._parse_port_nodes(
                str(getattr(settings, "measurement_node", "") or "").strip(),
                default_positive=output_hint or "out",
            )

            if hasattr(fa_opts, "perturbation_port"):
                fa_opts.perturbation_port = self._make_frequency_port(inj_positive, inj_negative)
            if hasattr(fa_opts, "output_port"):
                fa_opts.output_port = self._make_frequency_port(out_positive, out_negative)

            run_frequency = ps.run_frequency_analysis
            try:
                ps_fa_result = run_frequency(circuit, fa_opts, raise_on_failure=False)
            except TypeError:
                ps_fa_result = run_frequency(circuit, fa_opts)
            return self._map_fa_result(ps_fa_result)

        except Exception as exc:
            log.exception("run_frequency_analysis failed")
            return FrequencyAnalysisResult(
                success=False,
                diagnostic_code="internal_error",
                diagnostic_message=str(exc),
            )

    def export_fmu(
        self,
        circuit_data: dict,
        settings: FmuExportSettings,
    ) -> FmuExportResult:
        """Export the current circuit as a FMI 2.0 co-simulation FMU.

        Wraps :func:`pulsim.fmu.export`. Re-raises backend exceptions as
        :class:`RuntimeError` so callers get a single failure type to
        surface in the UI.
        """
        if not self.has_capability("fmu_export"):
            raise NotImplementedError(
                "This backend version does not expose FMU export. Upgrade "
                "to pulsim>=0.8.0."
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            raise RuntimeError(f"Circuit conversion failed: {exc}") from exc

        export_fn = self._module.fmu.export

        kwargs: dict[str, Any] = {
            "dt": float(settings.dt),
            "out_path": str(settings.out_path),
        }
        if settings.model_name:
            kwargs["model_name"] = settings.model_name
        if settings.inputs:
            kwargs["inputs"] = tuple(settings.inputs)
        if settings.outputs:
            kwargs["outputs"] = tuple(settings.outputs)
        if settings.cc:
            kwargs["cc"] = settings.cc

        try:
            summary = export_fn(circuit, **kwargs)
        except Exception as exc:  # pragma: no cover - backend-side failure
            raise RuntimeError(f"FMU export failed: {exc}") from exc

        return FmuExportResult(
            path=str(getattr(summary, "path", settings.out_path)),
            model_name=str(getattr(summary, "model_name", "")),
            model_identifier=str(getattr(summary, "model_identifier", "")),
            guid=str(getattr(summary, "guid", "")),
            fmi_version=str(getattr(summary, "fmi_version", "")),
            state_size=int(getattr(summary, "state_size", 0) or 0),
            input_size=int(getattr(summary, "input_size", 0) or 0),
            output_size=int(getattr(summary, "output_size", 0) or 0),
            inputs=tuple(getattr(summary, "inputs", ()) or ()),
            outputs=tuple(getattr(summary, "outputs", ()) or ()),
            files_in_archive=tuple(getattr(summary, "files_in_archive", ()) or ()),
        )

    def export_c99(
        self,
        circuit_data: dict,
        settings: C99CodegenSettings,
    ) -> C99CodegenResult:
        """Generate deployable C99 controller code via ``pulsim.codegen.generate``.

        The Pulsim runtime today only ships the ``c99`` target; the dialog
        is structured to accept others in the future so the GUI's
        ``settings.target`` value is forwarded verbatim.
        """
        if not self.has_capability("c99_codegen"):
            raise NotImplementedError(
                "This backend version does not expose C99 codegen. Upgrade "
                "to pulsim>=0.8.0."
            )

        try:
            circuit = self._converter.build(circuit_data)
        except CircuitConversionError as exc:
            raise RuntimeError(f"Circuit conversion failed: {exc}") from exc

        generate_fn = self._module.codegen.generate

        kwargs: dict[str, Any] = {
            "dt": float(settings.dt),
            "out_dir": str(settings.out_dir),
            "target": str(settings.target or "c99"),
            "t_op": float(settings.t_op),
        }

        try:
            summary = generate_fn(circuit, **kwargs)
        except Exception as exc:  # pragma: no cover - backend-side failure
            raise RuntimeError(f"C99 codegen failed: {exc}") from exc

        return C99CodegenResult(
            out_dir=str(getattr(summary, "out_dir", settings.out_dir)),
            target=str(getattr(summary, "target", settings.target)),
            state_size=int(getattr(summary, "state_size", 0) or 0),
            input_size=int(getattr(summary, "input_size", 0) or 0),
            output_size=int(getattr(summary, "output_size", 0) or 0),
            stability_radius=float(getattr(summary, "stability_radius", 0.0) or 0.0),
            rom_estimate_bytes=int(getattr(summary, "rom_estimate_bytes", 0) or 0),
            ram_estimate_bytes=int(getattr(summary, "ram_estimate_bytes", 0) or 0),
            files_written=tuple(getattr(summary, "files_written", ()) or ()),
        )

    # ------------------------------------------------------------------
    # Wave-4 sub-B analysis modes
    # ------------------------------------------------------------------
    def _build_simulator(self, circuit_data: dict) -> Any:
        """Construct ``self._module.Simulator(circuit, default options)``.

        Used by the wave-4 sub-B run helpers. The standard
        ``run_transient`` path goes through a richer setup; this is a
        slim variant that's sufficient for the new analysis modes which
        only need a viable Simulator handle.
        """
        circuit = self._converter.build(circuit_data)
        sim_options_cls = getattr(self._module, "SimulationOptions", None)
        if sim_options_cls is None:
            return self._module.Simulator(circuit)
        return self._module.Simulator(circuit, sim_options_cls())

    def run_fra(
        self,
        circuit_data: dict,
        settings: FraSettings,
    ) -> FraResult:
        """Run pulsim's empirical FRA (Simulator.run_fra)."""
        if not self.has_capability("fra"):
            return FraResult(
                success=False,
                failure_reason="Backend version does not expose Simulator.run_fra.",
            )

        try:
            simulator = self._build_simulator(circuit_data)
        except CircuitConversionError as exc:
            return FraResult(success=False, failure_reason=f"Circuit conversion: {exc}")

        opts_cls = getattr(self._module, "FraOptions", None)
        if opts_cls is None:
            return FraResult(
                success=False, failure_reason="pulsim.FraOptions not available."
            )
        opts = opts_cls()
        if hasattr(opts, "f_start"):
            opts.f_start = float(settings.f_start)
        if hasattr(opts, "f_stop"):
            opts.f_stop = float(settings.f_stop)
        if hasattr(opts, "points_per_decade"):
            opts.points_per_decade = int(settings.points_per_decade)
        if hasattr(opts, "scale"):
            opts.scale = str(settings.scale)
        if hasattr(opts, "perturbation_amplitude"):
            opts.perturbation_amplitude = float(settings.perturbation_amplitude)
        if hasattr(opts, "perturbation_phase"):
            opts.perturbation_phase = float(settings.perturbation_phase)
        if hasattr(opts, "perturbation_source") and settings.perturbation_source:
            opts.perturbation_source = settings.perturbation_source
        if hasattr(opts, "measurement_nodes") and settings.measurement_nodes:
            opts.measurement_nodes = list(settings.measurement_nodes)
        if hasattr(opts, "samples_per_cycle"):
            opts.samples_per_cycle = int(settings.samples_per_cycle)
        if hasattr(opts, "n_cycles"):
            opts.n_cycles = int(settings.n_cycles)
        if hasattr(opts, "discard_cycles"):
            opts.discard_cycles = int(settings.discard_cycles)

        try:
            native = simulator.run_fra(opts)
        except Exception as exc:  # pragma: no cover - backend-side failure
            return FraResult(success=False, failure_reason=str(exc))

        frequencies = tuple(float(f) for f in getattr(native, "frequencies", ()) or ())
        measurements = getattr(native, "measurements", []) or []
        entries: list[FraResultEntry] = []
        for f, meas in zip(frequencies, measurements):
            entries.append(
                FraResultEntry(
                    frequency=float(f),
                    magnitude_db=float(getattr(meas, "magnitude_db", 0.0) or 0.0),
                    phase_deg=float(getattr(meas, "phase_deg", 0.0) or 0.0),
                )
            )

        return FraResult(
            success=bool(getattr(native, "success", False)),
            failure_reason=str(getattr(native, "failure_reason", "") or ""),
            wall_seconds=float(getattr(native, "wall_seconds", 0.0) or 0.0),
            total_transient_steps=int(getattr(native, "total_transient_steps", 0) or 0),
            frequencies=frequencies,
            entries=tuple(entries),
        )

    def run_periodic_steady_state(
        self,
        circuit_data: dict,
        settings: PeriodicSteadyStateSettings,
    ) -> PeriodicSteadyStateResult:
        """Shooting-based periodic steady-state solve."""
        if not self.has_capability("periodic_steady_state"):
            return PeriodicSteadyStateResult(
                success=False,
                message="Backend version does not expose Simulator.run_periodic_shooting.",
            )

        try:
            simulator = self._build_simulator(circuit_data)
        except CircuitConversionError as exc:
            return PeriodicSteadyStateResult(success=False, message=f"Circuit conversion: {exc}")

        opts_cls = getattr(self._module, "PeriodicSteadyStateOptions", None)
        if opts_cls is None:
            return PeriodicSteadyStateResult(
                success=False,
                message="pulsim.PeriodicSteadyStateOptions not available.",
            )
        opts = opts_cls()
        if hasattr(opts, "period"):
            opts.period = float(settings.period)
        if hasattr(opts, "max_iterations"):
            opts.max_iterations = int(settings.max_iterations)
        if hasattr(opts, "tolerance"):
            opts.tolerance = float(settings.tolerance)
        if hasattr(opts, "relaxation"):
            opts.relaxation = float(settings.relaxation)
        if hasattr(opts, "store_last_transient"):
            opts.store_last_transient = bool(settings.store_last_transient)

        try:
            native = simulator.run_periodic_shooting(opts)
        except Exception as exc:  # pragma: no cover - backend-side failure
            return PeriodicSteadyStateResult(success=False, message=str(exc))

        return PeriodicSteadyStateResult(
            success=bool(getattr(native, "success", False)),
            message=str(getattr(native, "message", "") or ""),
            iterations=int(getattr(native, "iterations", 0) or 0),
            residual_norm=float(getattr(native, "residual_norm", 0.0) or 0.0),
            diagnostic=str(getattr(native, "diagnostic", "") or ""),
        )

    def run_harmonic_balance(
        self,
        circuit_data: dict,
        settings: HarmonicBalanceSettings,
    ) -> HarmonicBalanceResult:
        """Solve the spectrum via harmonic balance."""
        if not self.has_capability("harmonic_balance"):
            return HarmonicBalanceResult(
                success=False,
                message="Backend version does not expose Simulator.run_harmonic_balance.",
            )

        try:
            simulator = self._build_simulator(circuit_data)
        except CircuitConversionError as exc:
            return HarmonicBalanceResult(success=False, message=f"Circuit conversion: {exc}")

        opts_cls = getattr(self._module, "HarmonicBalanceOptions", None)
        if opts_cls is None:
            return HarmonicBalanceResult(
                success=False,
                message="pulsim.HarmonicBalanceOptions not available.",
            )
        opts = opts_cls()
        if hasattr(opts, "period"):
            opts.period = float(settings.period)
        if hasattr(opts, "num_samples"):
            opts.num_samples = int(settings.num_samples)
        if hasattr(opts, "max_iterations"):
            opts.max_iterations = int(settings.max_iterations)
        if hasattr(opts, "tolerance"):
            opts.tolerance = float(settings.tolerance)
        if hasattr(opts, "relaxation"):
            opts.relaxation = float(settings.relaxation)
        if hasattr(opts, "initialize_from_transient"):
            opts.initialize_from_transient = bool(settings.initialize_from_transient)

        try:
            native = simulator.run_harmonic_balance(opts)
        except Exception as exc:  # pragma: no cover - backend-side failure
            return HarmonicBalanceResult(success=False, message=str(exc))

        sample_times = getattr(native, "sample_times", []) or []
        return HarmonicBalanceResult(
            success=bool(getattr(native, "success", False)),
            message=str(getattr(native, "message", "") or ""),
            iterations=int(getattr(native, "iterations", 0) or 0),
            residual_norm=float(getattr(native, "residual_norm", 0.0) or 0.0),
            diagnostic=str(getattr(native, "diagnostic", "") or ""),
            sample_count=len(sample_times),
        )

    def _make_frequency_port(self, positive_node: str, negative_node: str) -> Any:
        """Create FrequencyAnalysisPort for pybind/dataclass backends."""
        port_cls = getattr(self._module, "FrequencyAnalysisPort", None)
        if port_cls is None:
            return {"positive_node": positive_node, "negative_node": negative_node}
        try:
            port = port_cls()
        except Exception:
            port = port_cls
        if hasattr(port, "positive_node"):
            port.positive_node = positive_node
        if hasattr(port, "negative_node"):
            port.negative_node = negative_node
        return port

    @staticmethod
    def _parse_port_nodes(raw: str, *, default_positive: str) -> tuple[str, str]:
        """Parse a node specification into (positive, negative)."""
        text = str(raw or "").strip()
        if not text:
            return default_positive, "0"
        for sep in (",", ";", ":", "/", "->"):
            if sep in text:
                left, right = text.split(sep, 1)
                positive = left.strip() or default_positive
                negative = right.strip() or "0"
                return positive, negative
        return text, "0"

    @staticmethod
    def _map_fa_result(ps_result: Any) -> FrequencyAnalysisResult:
        """Map a pulsim FrequencyAnalysisResult to the GUI wrapper type."""
        def _field(obj: Any, key: str, default: Any = None) -> Any:
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        def _coerce_series(raw: Any) -> list[float]:
            if raw is None:
                return []
            values = raw.tolist() if isinstance(raw, np.ndarray) else list(raw)
            out: list[float] = []
            for value in values:
                numeric = _optional_float(value)
                if numeric is None:
                    continue
                out.append(numeric)
            return out

        freqs = _coerce_series(_field(ps_result, "frequency_hz", None) or _field(ps_result, "frequencies", []))

        raw_mag = _field(ps_result, "magnitude_db", None) or _field(ps_result, "magnitude", None)
        raw_phase = _field(ps_result, "phase_deg", None) or _field(ps_result, "phase", None)
        if isinstance(raw_mag, dict):
            magnitude_db = {str(key): _coerce_series(values) for key, values in raw_mag.items()}
        else:
            magnitude_db = {"H(s)": _coerce_series(raw_mag)} if raw_mag is not None else {}
        if isinstance(raw_phase, dict):
            phase_deg = {str(key): _coerce_series(values) for key, values in raw_phase.items()}
        else:
            phase_deg = {"H(s)": _coerce_series(raw_phase)} if raw_phase is not None else {}

        diagnostic = _field(ps_result, "diagnostic", None)
        diagnostic_code = _enum_name_or_value(diagnostic)
        diagnostic_message = str(
            _field(ps_result, "message", "")
            or _field(diagnostic, "message", "")
            or _field(ps_result, "diagnostic_message", "")
            or ""
        ).strip()

        return FrequencyAnalysisResult(
            frequencies=freqs,
            magnitude_db=magnitude_db,
            phase_deg=phase_deg,
            gain_margin_db=_optional_float(_field(ps_result, "gain_margin_db", None)),
            phase_margin_deg=_optional_float(_field(ps_result, "phase_margin_deg", None)),
            gain_crossover_hz=_optional_float(_field(ps_result, "gain_crossover_hz", None)),
            phase_crossover_hz=_optional_float(_field(ps_result, "phase_crossover_hz", None)),
            success=bool(_field(ps_result, "success", True)),
            diagnostic_code=diagnostic_code,
            diagnostic_message=diagnostic_message,
            mode=_enum_name_or_value(_field(ps_result, "mode", "")),
            anchor_mode_selected=_enum_name_or_value(_field(ps_result, "anchor_mode_selected", "")),
            failed_point_index=int(_optional_float(_field(ps_result, "failed_point_index", -1)) or -1),
            failed_frequency_hz=_optional_float(_field(ps_result, "failed_frequency_hz", None)),
            gain_crossover_reason=_enum_name_or_value(_field(ps_result, "gain_crossover_reason", "")),
            phase_crossover_reason=_enum_name_or_value(_field(ps_result, "phase_crossover_reason", "")),
            phase_margin_reason=_enum_name_or_value(_field(ps_result, "phase_margin_reason", "")),
            gain_margin_reason=_enum_name_or_value(_field(ps_result, "gain_margin_reason", "")),
        )

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

    @staticmethod
    def _extract_telemetry_field(payload: Any, field: str) -> Any | None:
        if isinstance(payload, dict):
            return payload.get(field)
        return getattr(payload, field, None)

    @staticmethod
    def _serialize_telemetry_items(payload: Any, fields: tuple[str, ...]) -> list[dict[str, Any]]:
        if payload is None:
            return []
        if isinstance(payload, dict):
            item = PulsimBackend._serialize_telemetry_item(payload, fields)
            return [item] if item else []
        if isinstance(payload, (list, tuple)):
            return [
                item
                for item in (
                    PulsimBackend._serialize_telemetry_item(entry, fields) for entry in payload
                )
                if item
            ]
        try:
            iterable = list(payload)
        except TypeError:
            item = PulsimBackend._serialize_telemetry_item(payload, fields)
            return [item] if item else []
        return [
            item
            for item in (
                PulsimBackend._serialize_telemetry_item(entry, fields) for entry in iterable
            )
            if item
        ]

    @staticmethod
    def _serialize_telemetry_item(payload: Any, fields: tuple[str, ...]) -> dict[str, Any]:
        if payload is None:
            return {}
        out: dict[str, Any] = {}
        for field_name in fields:
            value = PulsimBackend._extract_telemetry_field(payload, field_name)
            coerced = PulsimBackend._coerce_telemetry_scalar(value)
            if coerced is not None:
                out[field_name] = coerced
        return out

    @staticmethod
    def _coerce_telemetry_scalar(value: Any) -> bool | float | str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value
        if isinstance(value, (int, float)):
            return float(value)
        enum_name = getattr(value, "name", None)
        if isinstance(enum_name, str):
            return enum_name
        return None

    @staticmethod
    def _serialize_loss_breakdown(payload: Any) -> dict[str, Any]:
        breakdown = PulsimBackend._serialize_telemetry_item(
            payload,
            ("conduction", "turn_on", "turn_off", "reverse_recovery"),
        )
        if not breakdown:
            return {}

        conduction = float(breakdown.get("conduction", 0.0) or 0.0)
        turn_on = float(breakdown.get("turn_on", 0.0) or 0.0)
        turn_off = float(breakdown.get("turn_off", 0.0) or 0.0)
        reverse_recovery = float(breakdown.get("reverse_recovery", 0.0) or 0.0)
        breakdown["switching"] = turn_on + turn_off + reverse_recovery
        breakdown["total"] = conduction + float(breakdown["switching"])
        return breakdown

    @staticmethod
    def _serialize_loss_result(payload: Any) -> dict[str, Any]:
        if payload is None:
            return {}

        out = PulsimBackend._serialize_telemetry_item(
            payload,
            (
                "device_name",
                "total_energy",
                "average_power",
                "peak_power",
                "rms_current",
                "avg_current",
                "efficiency_contribution",
            ),
        )
        breakdown = PulsimBackend._serialize_loss_breakdown(
            PulsimBackend._extract_telemetry_field(payload, "breakdown")
        )
        if breakdown:
            out["breakdown"] = breakdown
        return out

    @staticmethod
    def _serialize_device_losses(payload: Any) -> dict[str, dict[str, Any]]:
        if payload is None:
            return {}

        if isinstance(payload, dict):
            iterable = payload.items()
        else:
            try:
                iterable = ((None, item) for item in list(payload))
            except TypeError:
                iterable = ()

        device_losses: dict[str, dict[str, Any]] = {}
        for key, raw_entry in iterable:
            entry = PulsimBackend._serialize_loss_result(raw_entry)
            entry_name = str(entry.get("device_name") or key or "").strip()
            if not entry_name:
                continue
            if not entry:
                continue
            entry["device_name"] = entry_name
            device_losses[entry_name] = entry
        return device_losses

    def _append_electrothermal_statistics(
        self,
        statistics: dict[str, Any],
        native_result: Any,
        payload: dict[str, Any] | None = None,
    ) -> None:
        linear_solver_telemetry = self._extract_telemetry_field(payload, "linear_solver_telemetry")
        if linear_solver_telemetry is None:
            linear_solver_telemetry = getattr(native_result, "linear_solver_telemetry", None)
        linear_data = self._serialize_telemetry_item(
            linear_solver_telemetry,
            (
                "total_solve_calls",
                "total_analyze_calls",
                "total_factorize_calls",
                "total_iterations",
                "total_fallbacks",
                "last_iterations",
                "last_error",
                "total_analyze_time_seconds",
                "total_factorize_time_seconds",
                "total_solve_time_seconds",
                "last_analyze_time_seconds",
                "last_factorize_time_seconds",
                "last_solve_time_seconds",
                "last_solver",
                "last_preconditioner",
            ),
        )
        if linear_data:
            statistics["linear_solver_telemetry"] = linear_data

        backend_telemetry = self._extract_telemetry_field(payload, "backend_telemetry")
        if backend_telemetry is None:
            backend_telemetry = getattr(native_result, "backend_telemetry", None)
        backend_data = self._serialize_telemetry_item(
            backend_telemetry,
            (
                "requested_backend",
                "selected_backend",
                "solver_family",
                "formulation_mode",
                "function_evaluations",
                "jacobian_evaluations",
                "nonlinear_iterations",
                "nonlinear_convergence_failures",
                "error_test_failures",
                "escalation_count",
                "reinitialization_count",
                "backend_recovery_count",
                "state_space_primary_steps",
                "dae_fallback_steps",
                "segment_non_admissible_steps",
                "segment_model_cache_hits",
                "segment_model_cache_misses",
                "linear_factor_cache_hits",
                "linear_factor_cache_misses",
                "linear_factor_cache_invalidations",
                "linear_factor_cache_last_invalidation_reason",
                "reserved_output_samples",
                "time_series_reallocations",
                "state_series_reallocations",
                "virtual_channel_reallocations",
                "equation_assemble_system_calls",
                "equation_assemble_residual_calls",
                "equation_assemble_system_time_seconds",
                "equation_assemble_residual_time_seconds",
                "model_regularization_events",
                "model_regularization_last_changed",
                "model_regularization_last_intensity",
                "failure_reason",
            ),
        )
        if backend_data:
            statistics["backend_telemetry"] = backend_data

        fallback_trace = self._extract_telemetry_field(payload, "fallback_trace")
        if fallback_trace is None:
            fallback_trace = getattr(native_result, "fallback_trace", None)
        fallback_data = self._serialize_telemetry_items(
            fallback_trace,
            ("step_index", "retry_index", "time", "dt", "reason", "solver_status", "action"),
        )
        if fallback_data:
            statistics["fallback_trace"] = fallback_data
            statistics["fallback_trace_count"] = len(fallback_data)

        loss_summary = self._extract_telemetry_field(payload, "loss_summary")
        if loss_summary is None:
            loss_summary = getattr(native_result, "loss_summary", None)
        summary_data = self._serialize_telemetry_item(
            loss_summary,
            (
                "total_loss",
                "total_conduction",
                "total_switching",
                "input_power",
                "output_power",
                "efficiency",
            ),
        )
        device_losses = self._serialize_device_losses(
            self._extract_telemetry_field(loss_summary, "device_losses")
        )
        if device_losses:
            summary_data["device_losses"] = device_losses
        if summary_data:
            statistics["loss_summary"] = summary_data
            if isinstance(summary_data.get("total_loss"), (int, float)):
                statistics["system_total_loss"] = float(summary_data["total_loss"])
            if device_losses:
                statistics["loss_device_count"] = len(device_losses)

        thermal_summary = self._extract_telemetry_field(payload, "thermal_summary")
        if thermal_summary is None:
            thermal_summary = getattr(native_result, "thermal_summary", None)

        summary_data = self._serialize_telemetry_item(
            thermal_summary,
            ("enabled", "ambient", "max_temperature"),
        )
        device_data = self._serialize_telemetry_items(
            self._extract_telemetry_field(thermal_summary, "device_temperatures"),
            (
                "device_name",
                "enabled",
                "final_temperature",
                "peak_temperature",
                "average_temperature",
            ),
        )
        if device_data:
            summary_data["device_temperatures"] = device_data
        if summary_data:
            statistics["thermal_summary"] = summary_data
            if isinstance(summary_data.get("max_temperature"), (int, float)):
                statistics["thermal_max_temperature"] = float(summary_data["max_temperature"])

        component_electrothermal = self._extract_telemetry_field(payload, "component_electrothermal")
        if component_electrothermal is None:
            component_electrothermal = getattr(native_result, "component_electrothermal", None)
        component_data = self._serialize_telemetry_items(
            component_electrothermal,
            (
                "component_name",
                "thermal_enabled",
                "conduction",
                "turn_on",
                "turn_off",
                "reverse_recovery",
                "total_loss",
                "total_energy",
                "average_power",
                "peak_power",
                "final_temperature",
                "peak_temperature",
                "average_temperature",
            ),
        )
        if component_data:
            statistics["component_electrothermal"] = component_data
            statistics["electrothermal_component_count"] = len(component_data)
            peak_temperatures = [
                float(item["peak_temperature"])
                for item in component_data
                if isinstance(item.get("peak_temperature"), (int, float))
            ]
            if peak_temperatures:
                statistics["electrothermal_peak_temperature"] = max(peak_temperatures)

    def _populate_backend_result(self, backend_result: BackendRunResult, sim_result: Any) -> None:
        payload: dict[str, Any] | None = None
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
        self._append_electrothermal_statistics(backend_result.statistics, sim_result, payload)

    def _compute_time_step(self, settings: SimulationSettings) -> float:
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
        settings: SimulationSettings,
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

    def _invoke_run_transient(self, args: list[Any], settings: SimulationSettings) -> tuple[Any, Any, bool, str]:
        """Invoke run_transient with optional robust kwargs when supported."""
        robust = bool(getattr(settings, "transient_robust_mode", True))
        auto_regularize = bool(getattr(settings, "transient_auto_regularize", True))
        try:
            return self._module.run_transient(
                *args,
                robust=robust,
                auto_regularize=auto_regularize,
            )
        except TypeError as exc:
            text = str(exc)
            if "robust" not in text and "auto_regularize" not in text:
                raise
        return self._module.run_transient(*args)

    def _build_newton_options(self, settings: SimulationSettings, circuit: Any) -> Any:
        """Build NewtonOptions for the new kernel API."""
        if hasattr(self._module, "NewtonOptions"):
            opts = self._module.NewtonOptions()
        else:  # pragma: no cover - defensive fallback for older adapters
            opts = type("NewtonOptions", (), {})()

        base_max_iter = int(getattr(settings, "max_newton_iterations", 100))
        opts.max_iterations = base_max_iter
        opts.enable_limiting = settings.enable_voltage_limiting
        opts.max_voltage_step = settings.max_voltage_step

        if hasattr(self._module, "Tolerances"):
            tolerances = self._module.Tolerances.defaults()
            tolerances.voltage_abstol = settings.abs_tol
            tolerances.voltage_reltol = settings.rel_tol
            tolerances.current_abstol = settings.abs_tol
            tolerances.current_reltol = settings.rel_tol
            if hasattr(tolerances, "residual_tol"):
                tolerances.residual_tol = max(settings.abs_tol, 1e-12)
            opts.tolerances = tolerances

        # Newton damping: critical for MOSFET/diode switching circuit convergence.
        # These match the values from the validated buck converter benchmark.
        if hasattr(opts, "initial_damping"):
            opts.initial_damping = 0.5
        if hasattr(opts, "min_damping"):
            opts.min_damping = 1e-4
        if hasattr(opts, "auto_damping"):
            opts.auto_damping = True

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

    def _build_initial_state(self, circuit: Any, settings: SimulationSettings) -> Any:
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
                    if hasattr(config, "source_config"):
                        source_steps = int(getattr(settings, "dc_source_steps", 10))
                        config.source_config.max_steps = max(1, source_steps)
                elif settings.dc_strategy == "pseudo" and hasattr(self._module, "DCStrategy"):
                    config.strategy = self._module.DCStrategy.PseudoTransient
                dc_result = self._module.dc_operating_point(circuit, config)
                success = getattr(dc_result, "success", False)
                if callable(success):
                    success = success()
                if success:
                    newton_result = getattr(dc_result, "newton_result", None)
                    if newton_result is not None:
                        return newton_result.solution
            except Exception:
                pass

        if hasattr(circuit, "initial_state"):
            return circuit.initial_state()
        return None

    @staticmethod
    def _ensure_state_vector(x0: Any, size: int) -> Any:
        if x0 is not None:
            return x0
        return np.zeros(max(1, int(size)), dtype=np.float64)

    @staticmethod
    def _supports_dc_analysis(module: Any) -> bool:
        if any(hasattr(module, name) for name in ("dc_operating_point", "solve_dc", "run_dc", "run_dc_analysis")):
            return True

        for ns_name in ("v1", "v2"):
            namespace = getattr(module, ns_name, None)
            if namespace is None:
                continue
            if any(
                hasattr(namespace, name)
                for name in ("dc_operating_point", "solve_dc", "run_dc", "run_dc_analysis", "DCConvergenceSolver")
            ):
                return True

        simulator_cls = getattr(module, "Simulator", None)
        if simulator_cls is not None and any(
            hasattr(simulator_cls, name) for name in ("dc_operating_point", "solve_dc", "run_dc", "run_dc_analysis")
        ):
            return True

        cap_fn = getattr(module, "backend_capabilities", None)
        if callable(cap_fn):
            try:
                raw_caps = cap_fn()
            except Exception:
                return False
            if isinstance(raw_caps, dict):
                for key in ("dc", "dc_analysis", "operating_point"):
                    dc_value = raw_caps.get(key)
                    if isinstance(dc_value, bool):
                        return dc_value
            if isinstance(raw_caps, (set, tuple, list)):
                return any(cap in raw_caps for cap in ("dc", "dc_analysis", "operating_point"))
        return False

    @staticmethod
    def _supports_ac_analysis(module: Any) -> bool:
        if any(hasattr(module, name) for name in ("run_ac", "run_ac_analysis", "run_small_signal", "ACAnalysis")):
            return True

        simulator_cls = getattr(module, "Simulator", None)
        if simulator_cls is not None and any(
            hasattr(simulator_cls, name) for name in ("run_ac", "run_ac_analysis", "run_small_signal")
        ):
            return True

        cap_fn = getattr(module, "backend_capabilities", None)
        if callable(cap_fn):
            try:
                raw_caps = cap_fn()
            except Exception:
                return False
            if isinstance(raw_caps, dict):
                for key in ("ac", "ac_analysis", "small_signal"):
                    ac_value = raw_caps.get(key)
                    if isinstance(ac_value, bool):
                        return ac_value
            if isinstance(raw_caps, (set, tuple, list)):
                return any(cap in raw_caps for cap in ("ac", "ac_analysis", "small_signal"))
        return False

    @staticmethod
    def _supports_thermal_analysis(module: Any) -> bool:
        if any(hasattr(module, name) for name in ("run_thermal", "run_thermal_analysis")):
            return True

        thermal_simulator = getattr(module, "ThermalSimulator", None)
        if thermal_simulator is not None:
            if hasattr(thermal_simulator, "run"):
                return True
            if hasattr(thermal_simulator, "simulate") and callable(
                getattr(module, "create_simple_thermal_model", None)
            ):
                return True
            # Keep legacy detection behavior: older compatibility tests and
            # adapters treat ThermalSimulator presence as thermal capability.
            return True

        simulator_cls = getattr(module, "Simulator", None)
        if simulator_cls is not None and any(
            hasattr(simulator_cls, name) for name in ("run_thermal", "run_thermal_analysis")
        ):
            return True

        cap_fn = getattr(module, "backend_capabilities", None)
        if callable(cap_fn):
            try:
                raw_caps = cap_fn()
            except Exception:
                return False
            if isinstance(raw_caps, dict):
                for key in ("thermal", "thermal_analysis"):
                    thermal_value = raw_caps.get(key)
                    if isinstance(thermal_value, bool):
                        return thermal_value
            if isinstance(raw_caps, (set, tuple, list)):
                return any(cap in raw_caps for cap in ("thermal", "thermal_analysis"))
        return False


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
                message="Running in demo mode; install pulsim backend to enable real simulations.",
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
        """Return the identifier of the currently active backend."""
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

    def _discover_candidates(self) -> dict[str, BackendLoader._BackendCandidate]:
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
    ) -> BackendLoader._BackendCandidate:
        info = BackendInfo(
            identifier="placeholder",
            name="Demo backend",
            version="0.0",
            status=status,
            capabilities={
                "transient",
                "dc",
                "ac",
                "thermal",
                "post_processing",
                "frequency_analysis",
                "averaged",
            },
            message=message,
        )
        return BackendLoader._BackendCandidate(info=info, factory=lambda: PlaceholderBackend(info))

    def _create_pulsim_candidate(self) -> tuple[BackendLoader._BackendCandidate | None, str | None]:
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

        if PulsimBackend._supports_dc_analysis(module):
            capabilities.add("dc")

        if PulsimBackend._supports_ac_analysis(module):
            capabilities.add("ac")

        if PulsimBackend._supports_thermal_analysis(module):
            capabilities.add("thermal")

        if hasattr(module, "run_post_processing"):
            capabilities.add("post_processing")

        if hasattr(module, "run_frequency_analysis"):
            capabilities.add("frequency_analysis")

        if hasattr(module, "AveragedConverterOptions"):
            capabilities.add("averaged")

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

    def _load_entry_point_candidates(self) -> list[BackendLoader._BackendCandidate]:
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
