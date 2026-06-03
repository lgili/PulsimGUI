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
    # Optional kernel-side ring buffer for zero-copy streaming. When
    # set, the adapter forwards it as ``simulate(live_stream=…)`` so
    # the kernel pushes (t, x) samples directly into the shared
    # buffer at a decimated rate (no Python callback per step). The
    # GUI thread polls it via QTimer for the live-scope view. ``None``
    # means: stay on the legacy per-step ``data_point`` callback.
    live_stream: object | None = None


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


class _SimulateCancelled(Exception):
    """Internal sentinel used inside the v1.3 ``step_observer`` to bail
    out of ``pulsim.simulate(...)`` when the GUI's ``check_cancelled``
    callback returns True. Caught at the seam in ``_invoke_simulate_v13``
    and translated into the standard "cancelled" return tuple."""


class PulsimBackend(SimulationBackend):
    """Adapter that executes simulations via the native Pulsim backend."""

    def __init__(self, module: Any, info: BackendInfo) -> None:
        self._module = module
        self.info = info
        # ``circuit_converter`` was written for pulsim's pre-1.0 surface
        # (``Circuit`` / ``MOSFETParams`` / int node indices). When the
        # host pulsim is 1.0+, ``make_compat_module`` wraps it in a shim
        # that re-exposes the v0 names on top of ``CircuitBuilder``.
        # When the host is legacy, the shim is a no-op.
        from pulsimgui.services.pulsim_v0_compat import make_compat_module
        self._converter = CircuitConverter(make_compat_module(module))
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

        # Check for frequency analysis. Old v0 builds shipped
        # ``run_frequency_analysis``; pulsim 1.3+ replaces it with the
        # swept-sine ``run_ac_sweep`` and the impulse-response
        # ``run_mna_sweep`` pair.
        if any(
            hasattr(self._module, name)
            for name in ("run_ac_sweep", "run_mna_sweep", "run_frequency_analysis")
        ):
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

    def _merge_motor_observer_signals(self, circuit: Any, result: BackendRunResult) -> None:
        """Publish dynamic-machine observer traces as named result signals.

        A PMSM tracked by ``circuit.nonlinear_observer_specs`` carries a live
        observer bundle with rotor speed + d/q + per-phase current traces.
        These are NOT in the electrical state vector, so they never reach
        ``result.signals`` on their own. Resample each onto the output time
        base and expose them as ``<motor>.speed_rpm`` / ``.i_a`` / ``.i_d`` /
        ``.torque`` … so a scope channel can plot the motor's mechanical +
        control state (speed ramp, sinusoidal phase currents, decoupled d-q)
        directly — the FOC story the electrical node voltages can't tell.
        """
        if not result.time:
            return
        specs = getattr(circuit, "nonlinear_observer_specs", []) or []
        if not specs:
            return
        try:
            t_out = np.asarray(result.time, dtype=np.float64)
        except (TypeError, ValueError):
            return
        if t_out.size == 0:
            return

        published: list[str] = []
        for spec in specs:
            if str(spec.get("kind") or "") != "pmsm":
                continue
            bundle = spec.get("bundle")
            if bundle is None:
                continue
            name = (str(spec.get("name") or "").strip() or "M1")
            try:
                t_b = np.asarray(list(getattr(bundle, "times", []) or []), dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if t_b.size < 2:
                continue
            # bundle attr -> (signal-name suffix, scale)
            traces = (
                ("omega_rad_s", "speed_rpm", 60.0 / (2.0 * math.pi)),
                ("i_a", "i_a", 1.0),
                ("i_b", "i_b", 1.0),
                ("i_c", "i_c", 1.0),
                ("i_d", "i_d", 1.0),
                ("i_q", "i_q", 1.0),
                ("T_em", "torque", 1.0),
            )
            for attr, suffix, scale in traces:
                raw = getattr(bundle, attr, None)
                if raw is None:
                    continue
                try:
                    arr = np.asarray(list(raw), dtype=np.float64)
                except (TypeError, ValueError):
                    continue
                n = min(arr.size, t_b.size)
                if n < 2:
                    continue
                values = np.interp(t_out, t_b[:n], arr[:n] * scale)
                key = f"{name}.{suffix}"
                result.signals[key] = values.tolist()
                published.append(key)

        if published:
            result.statistics["motor_observer_signals"] = sorted(set(published))

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
        """Populate ``result.signals[<probe_name>]`` for every current_probe.

        The CURRENT_PROBE component is stamped by
        :meth:`CircuitConverter.build` as a 0 V voltage source whose
        name matches the probe (modern path, pulsim ≥ 1.6.5) or as a
        tiny bypass resistor named ``__IP_BYPASS_<probe>`` (legacy
        path, pre-1.6.5 backends without ``add_voltage_source``).
        Either way pulsim publishes a branch the GUI can scope; this
        helper just normalises the lookup to a single
        ``result.signals[<probe_name>]`` entry the rest of the GUI
        already keys on.

        Lookup order per probe (first hit wins):

          1. ``result.signals[<probe_name>]`` is already populated
             with a non-trivial series — leave it alone.
          2. ``result.i(<probe_name>)`` — the modern direct branch
             current. Exact, no reconstruction. Returns the current
             through the 0 V sense source we stamped at convert time.
          3. ``result.i("__IP_BYPASS_<probe_name>")`` — legacy
             stamping path (the converter used a bypass resistor
             instead of a voltage source). Same exactness, different
             branch name.
          4. Last-resort ``(V(N_in) − V(N_out)) / R_bypass``
             reconstruction — only reached if the kernel has no
             ``result.i`` accessor at all (pre-PR #82 builds).
        """
        sample_count = len(result.time)
        if sample_count <= 0:
            return

        virtual_components_attr = getattr(circuit, "virtual_components", None)
        if not callable(virtual_components_attr):
            return
        node_name_attr = getattr(circuit, "node_name", None)

        try:
            virtual_components = virtual_components_attr()
        except Exception:
            return
        try:
            components_iter = list(virtual_components)
        except Exception:
            return

        # Resolve the pulsim Result's ``i(name)`` accessor once. ``None``
        # means we're on a pre-PR-#82 build and must use the V/R fallback.
        kernel_result = getattr(result, "raw_result", None) or getattr(
            result, "_raw_result", None
        ) or getattr(result, "result", None) or result
        i_accessor = getattr(kernel_result, "i", None)
        if not callable(i_accessor):
            i_accessor = None

        repaired_channels: list[str] = []

        def _series_from_i(branch_name: str) -> list[float] | None:
            """Call ``result.i(branch_name)`` and coerce to a list of the
            right length. Returns None on any kind of miss."""
            if i_accessor is None:
                return None
            try:
                series = i_accessor(branch_name)
            except Exception:
                return None
            if series is None:
                return None
            try:
                series_list = [float(v) for v in series]
            except Exception:
                return None
            if len(series_list) < sample_count:
                return None
            return series_list[:sample_count]

        for entry in components_iter:
            comp_type = str(getattr(entry, "type", "") or "").strip().lower()
            if comp_type != "current_probe":
                continue

            channel_name = str(getattr(entry, "name", "") or "").strip()
            if not channel_name:
                continue

            # Already populated with meaningful data — done.
            existing = result.signals.get(channel_name)
            needs_synthesis = (
                not isinstance(existing, list)
                or len(existing) < sample_count
            )
            if not needs_synthesis:
                try:
                    peak_existing = max(
                        abs(float(value)) for value in existing[:sample_count]
                    )
                except Exception:
                    peak_existing = 0.0
                if peak_existing > 1e-12:
                    continue

            # 2. ``result.i(<probe_name>)`` — modern stamping (0 V source).
            series_list = _series_from_i(channel_name)
            if series_list is not None:
                result.signals[channel_name] = series_list
                repaired_channels.append(f"{channel_name}:result.i")
                continue

            # 3. ``result.i("__IP_BYPASS_<probe>")`` — legacy stamping
            # (bypass resistor branch). Still a state-variable branch
            # in newer pulsim because we put a tiny resistor there; on
            # newer pulsim the resistor isn't a state branch so this
            # call raises NotImplementedError and we drop through.
            series_list = _series_from_i(f"__IP_BYPASS_{channel_name}")
            if series_list is not None:
                result.signals[channel_name] = series_list
                repaired_channels.append(f"{channel_name}:result.i_bypass")
                continue

            # 4. Last-resort V/R reconstruction. Requires the helper
            # node-name accessor to translate node indices, plus a
            # bypass-resistor parameter to divide by.
            if not callable(node_name_attr):
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
            repaired_channels.append(f"{channel_name}:vr_fallback")

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
        self._merge_motor_observer_signals(circuit, result)

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

        # Pulsim 1.3+ short-circuit: route every transient attempt
        # through ``pulsim.simulate(builder, ...)`` BEFORE the legacy
        # ``run_transient``/``run_transient_streaming``/``Simulator``
        # path-selection cascade below. Those paths still exist in
        # this method because some hosts (older PulsimGUI test
        # mocks, the pre-1.0 wheel) rely on them, but on a real
        # pulsim 1.4 install they were all calling
        # ``pulsim._pulsim.run_transient`` with v0 positional args
        # the new binding rejects. Without this gate, the chunked
        # path at "Prefer robust run_transient path first" (~25
        # lines down) wins the race and crashes with an
        # incompatible-args TypeError.
        if self._should_use_simulate_v13():
            total_steps = max(1, int((settings.t_stop - settings.t_start) / dt))
            emit_interval = max(1, total_steps // 50)
            callbacks.progress(8.0, "Running simulation...")

            def _v13_progress(percent: float, message: str) -> None:
                # Map 0..100 percent into the 8..80 solver-stage band
                # the rest of the GUI expects.
                mapped = 8.0 + (max(0.0, min(100.0, percent)) / 100.0) * 72.0
                callbacks.progress(mapped, message)

            def _v13_data(t: float, signals: dict[str, Any]) -> None:
                if callbacks.data_point is not None:
                    callbacks.data_point(t, signals)

            def _v13_cancel() -> bool:
                return callbacks.check_cancelled()

            try:
                times, states, success, message, virtual_channels = (
                    self._invoke_simulate_v13(
                        circuit=circuit,
                        settings=settings,
                        dt=dt,
                        emit_interval=emit_interval,
                        callbacks=callbacks,
                        progress_callback=_v13_progress,
                        data_callback=_v13_data,
                        cancel_check=_v13_cancel,
                    )
                )
            except Exception as exc:  # noqa: BLE001 — surface to UI
                result.error_message = f"simulate(): {type(exc).__name__}: {exc}"
                return result

            if not success:
                result.error_message = message
                return result
            result.error_message = ""
            callbacks.progress(84.0, "Finalizing results...")
            self._fill_result_from_samples(
                result, times, states, signal_names,
                callbacks=callbacks, progress_start=84.0,
                progress_span=8.0,
                progress_message="Finalizing results...",
            )
            if virtual_channels:
                self._merge_streaming_virtual_channels(result, virtual_channels)
            self._merge_motor_observer_signals(circuit, result)
            return result

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

        # Special key: per-device electrothermal summary built by
        # ``_compute_per_device_electrothermal``. Goes into
        # ``result.statistics["component_electrothermal"]`` where the
        # GUI thermal_service finds it (it ALSO needs the T(<device>)
        # signals merged below — pulsim's loss summary stamps both).
        rows = virtual_channels.get("__electrothermal_rows__")
        if isinstance(rows, list) and rows:
            result.statistics["component_electrothermal"] = rows

        sample_count = len(result.time)
        merged_names: set[str] = set()
        for raw_name, raw_series in virtual_channels.items():
            if raw_name == "__electrothermal_rows__":
                continue  # handled above as statistics, not a signal
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

        # Pulsim 1.3+ retired ``run_transient_streaming`` in favour of
        # ``pulsim.simulate(builder, t_end, dt, switch_fn=,
        # step_observer=)``. The shim path detects that case (host
        # exposes ``simulate`` but not ``run_transient_streaming``) and
        # routes through the modern API; legacy hosts keep the v0
        # path untouched.
        if self._should_use_simulate_v13():
            try:
                times, states, success, message, virtual_channels = (
                    self._invoke_simulate_v13(
                        circuit=circuit,
                        settings=settings,
                        dt=dt,
                        emit_interval=emit_interval,
                        callbacks=callbacks,
                        progress_callback=progress_callback,
                        data_callback=data_callback,
                        cancel_check=cancel_check,
                    )
                )
            except Exception as exc:  # pragma: no cover - surface as error
                result.error_message = f"simulate(): {type(exc).__name__}: {exc}"
                return result

            if not success:
                result.error_message = message
                return result
            result.error_message = ""
            callbacks.progress(84.0, "Finalizing results...")
            self._fill_result_from_samples(
                result, times, states, signal_names,
                callbacks=callbacks, progress_start=84.0,
                progress_span=8.0,
                progress_message="Finalizing results...",
            )
            if virtual_channels:
                self._merge_streaming_virtual_channels(result, virtual_channels)
            if result.time:
                final_sample = {
                    name: values[-1]
                    for name, values in result.signals.items()
                }
                callbacks.data_point(result.time[-1], final_sample)
            return result

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
            # Pulsim 1.3+: retired ``dc_operating_point`` /
            # ``Simulator.dc_operating_point`` / ``solve_dc`` in
            # favour of the new ``compute_dc_op(builder, strategy=…)``
            # surface. Detect that case first; everything else is
            # legacy fallbacks.
            if self._should_use_compute_dc_op_v13():
                return self._run_dc_compute_op_v13(
                    circuit, settings, circuit_data
                )

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
            # Pulsim 1.3+: ``run_ac`` / ``run_ac_analysis`` /
            # ``run_small_signal`` / ``ACAnalysis`` were retired in
            # favour of ``run_ac_sweep`` (swept-sine, accurate for
            # nonlinear small-signal) and ``run_mna_sweep`` (impulse
            # response + FFT, fast for linear systems). The GUI's
            # AC analysis pane targets linear-circuit Bode plots, so
            # we prefer the MNA path for speed; the swept-sine
            # variant is available as a per-call override.
            if self._should_use_ac_sweep_v13():
                return self._run_ac_sweep_v13(circuit, settings)

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
            # Pulsim 1.3+ retired the standalone ``ThermalSimulator``
            # in favour of Foster networks embedded in the circuit
            # (``add_foster_network`` at build time) and a post-hoc
            # ``compute_temperature(t, P, foster_stages, T_amb)``
            # convolution. The GUI's thermal pane runs as a post-
            # transient analysis, so we use the convolution helper.
            if self._should_use_thermal_v13():
                return self._run_thermal_compute_v13(
                    circuit, electrical_result, settings
                )

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

    # ------------------------------------------------------------------
    # Pulsim 1.3+ simulate() routing (post-namespace-flatten path)
    # ------------------------------------------------------------------
    def _should_use_simulate_v13(self) -> bool:
        """True iff host pulsim is the post-1.0 surface (``simulate`` is
        exported, ``run_transient_streaming`` was retired). Sleeping
        when either side of the predicate is false keeps legacy
        pulsim builds on their original code paths."""
        if not hasattr(self._module, "simulate"):
            return False
        # Legacy pulsim shipped both ``simulate`` (since 0.7) AND
        # ``run_transient_streaming``. Only the post-1.0 surface
        # dropped the streaming entry-point — that's the signal we use
        # to commit to the v1.3 path.
        return not hasattr(self._module, "run_transient_streaming")

    def _invoke_simulate_v13(
        self,
        circuit: Any,
        settings: SimulationSettings,
        dt: float,
        emit_interval: int,
        callbacks: BackendCallbacks,
        progress_callback: Callable[[float, str], None],
        data_callback: Callable[[float, dict], None],
        cancel_check: Callable[[], bool],
    ) -> tuple[Any, Any, bool, str, Any]:
        """Run a transient through pulsim 1.3+'s ergonomic
        ``simulate(builder, t_end, dt, switch_fn=, step_observer=)``.

        ``circuit`` is the GUI's shim ``Circuit`` (see
        ``pulsim_v0_compat.Circuit``); we pull its underlying
        ``builder`` and the per-switch metadata (``num_switches`` +
        ``switch_indices`` + ``virtual_component_records``) to
        assemble the simulate-time ``switch_fn``.

        The streaming/cancel/progress contract is preserved by
        wrapping a ``step_observer`` that translates ``(t, x)``
        callbacks into the GUI's progress / data-point / cancel
        signals at roughly the same cadence the legacy streaming API
        produced.
        """
        # The shim Circuit exposes ``.builder`` for the underlying
        # v1.3 CircuitBuilder. Fall back to ``circuit`` itself when
        # the host gave us a raw builder (defensive: tests sometimes
        # do this).
        builder = getattr(circuit, "builder", circuit)

        # ``import`` lazily to avoid module-import time penalty.
        from pulsimgui.services.switch_fn_builder import (
            assemble_switch_fn,
            configs_from_pwm_records,
        )

        # Per-device PWM configs: best-effort heuristic from the
        # shim's ``virtual_component_records`` (PWM-generator virtual
        # components the converter recorded). Devices with no matching
        # record default to OFF.
        configs = configs_from_pwm_records(circuit)
        switch_fn = assemble_switch_fn(circuit, configs, self._module)

        # Nonlinear-device observers FIRST (before the VSI switch_fns):
        # the dynamic-PMSM observer build also stashes the live
        # ``MotorObserverBundle`` on its spec, which the FOC loop below
        # reads for d-q feedback. Building it here (instead of after the
        # step-observer adapter) keeps that data available to
        # ``_build_foc_loops`` without a second observer instance. The
        # step-observers are folded into the adapter further down.
        device_step_observers, device_b_extra_fn = (
            self._build_nonlinear_device_observers(circuit, builder, dt)
        )
        has_pmsm = any(
            str(spec.get("kind") or "") == "pmsm"
            for spec in (getattr(circuit, "nonlinear_observer_specs", []) or [])
        )

        # Field-Oriented Control (additive): when the converter detected a
        # FOC marker (``circuit.foc_loop_descriptors``), close the i_d/i_q
        # + speed PI loops over the PMSM observer bundle and drive the
        # bound VSI's six switches via inverse Park/Clarke. The FOC step-
        # observers run AFTER the PMSM observer (fresh d-q feedback); the
        # FOC switch_fns REPLACE the open-loop SPWM for the controlled
        # inverter (so the two never fight for the same switch bits).
        foc_step_observers, foc_switch_fns, foc_vsi_names = (
            self._build_foc_loops(circuit, builder)
        )

        # 6-step trapezoidal BLDC (additive, same gating pattern as FOC):
        # when the converter detected a SIXSTEP_CONTROLLER, close an outer
        # speed PI over the PMSM observer bundle and drive the bound VSI's
        # six switches via a sector-table commutation mask, PWM-modulating
        # only the active high-side switch at the carrier frequency. The
        # sixstep step-observers also run AFTER the PMSM observer (fresh
        # ω + θ feedback); the sixstep switch_fns REPLACE the open-loop
        # SPWM for the controlled inverter — and they MUST NOT collide
        # with FOC's controlled set, so the two name sets are unioned
        # before SPWM exclusion below.
        sixstep_step_observers, sixstep_switch_fns, sixstep_vsi_names = (
            self._build_sixstep_loops(circuit, builder)
        )
        controlled_vsi_names = set(foc_vsi_names) | set(sixstep_vsi_names)

        # Native 3φ VSI SPWM (pulsim 1.6.4): the converter recorded each
        # inverter's six builder-global switch indices + SPWM drive on
        # ``circuit.vsi_specs``. Build one SPWM switch_fn per inverter and
        # compose with the rest of the circuit's switch_fn via
        # ``make_combined_switch_fn`` (bitwise-OR of masks). This handles
        # both (a) VSI-only — ``assemble_switch_fn`` returned an all-OFF
        # mask for the non-VSI bits, OR'd with SPWM leaves just the
        # inverter pattern — and (b) VSI + PFC boost MOSFET — the PFC's
        # PWM mask (from ``assemble_switch_fn``) and the SPWM mask drive
        # disjoint switch bits, so the OR preserves both. The SPWM
        # callables emit a full-width mask touching only the inverter's
        # bits, so no index clobbers another. Any FOC-controlled VSI is
        # excluded here — its FOC switch_fn drives those six bits instead.
        vsi_switch_fns = self._build_vsi_switch_fns(
            circuit, builder, exclude_names=controlled_vsi_names,
        )
        # Controlled switch_fns (FOC + 6-step) drive their inverter bits in
        # place of the SPWM. Order doesn't matter — masks are OR'd inside
        # ``make_combined_switch_fn`` and the two never claim the same VSI
        # because their inferences are mutually exclusive per topology.
        vsi_switch_fns = (
            list(vsi_switch_fns) + list(foc_switch_fns) + list(sixstep_switch_fns)
        )
        if vsi_switch_fns:
            num_switches = int(getattr(builder.graph, "num_switches", 0))
            make_combined = getattr(
                self._module, "make_combined_switch_fn", None
            )
            sub_fns = list(vsi_switch_fns)
            # Include the base switch_fn only when it actually drives
            # something — the all-OFF constant fn contributes nothing to
            # the OR and would just add a per-step GIL hop.
            if switch_fn is not None and bool(
                getattr(circuit, "switch_indices", {})
            ):
                sub_fns.append(switch_fn)
            if make_combined is not None and num_switches > 0 and (
                len(sub_fns) > 1
            ):
                switch_fn = make_combined(num_switches, sub_fns)
            elif len(sub_fns) == 1:
                switch_fn = sub_fns[0]

        # Step-observer adapter: translate per-step ``(t, x)`` into
        # the existing data / progress / cancel callbacks.
        t_start = float(settings.t_start)
        t_stop = float(settings.t_stop)
        t_span = max(t_stop - t_start, 1e-12)
        step_counter = [0]
        cancel_requested = [False]

        def step_observer(t: float, x: Any) -> None:
            step_counter[0] += 1
            # Only emit progress / data callbacks every
            # ``emit_interval`` steps to match the legacy streaming
            # cadence and avoid GIL contention.
            if step_counter[0] % max(1, emit_interval) != 0:
                return
            try:
                if cancel_check():
                    cancel_requested[0] = True
                    raise _SimulateCancelled()
            except _SimulateCancelled:
                raise
            except Exception:
                # ``check_cancelled`` shouldn't raise; if it does we
                # treat it as "keep going" and swallow.
                pass
            pct = 100.0 * (t - t_start) / t_span
            progress_callback(max(0.0, min(100.0, pct)),
                                "Simulating...")
            # The legacy data_callback was given a ``state_dict``; we
            # don't reconstruct the per-channel map here (the final
            # arrays carry full resolution) — pass an empty dict so
            # the existing ``data_callback`` signature is satisfied.
            data_callback(float(t), {})

        # ``simulate`` raises if cancelled via observer exception or
        # on any solver failure. Map both into the streaming
        # (times, states, success, message, virtual_channels) tuple.
        #
        # Live-stream: when ``callbacks.live_stream`` is set (typically
        # a ``pulsim.NativeLiveStream`` created by the GUI worker), the
        # kernel writes (t, x) samples into its C++ ring buffer at the
        # decimated rate (default 1/100 steps). The GUI's QTimer polls
        # the ring on the main thread — zero Python in the per-step
        # hot path. Falls back to the legacy ``step_observer`` data
        # callback when ``live_stream is None``.
        #
        # Closed-loop: when the converter detected a PI+PWM+MOSFET
        # chain (e.g. buck closed-loop schematic), it stashed structured
        # descriptors on ``circuit.closed_loop_descriptors``. We pre-build
        # the loops here via ``ps.bind_pi_to_switch`` and pass them in
        # via ``closed_loops=`` — pulsim composes their switch_fns +
        # step_observers internally. Note: pulsim ≥ 1.4 rejects passing
        # both ``closed_loops`` and ``switch_fn``/``step_observer``, so
        # we either go all-closed-loop or all-static.
        # Nonlinear-device observers (pulsim 1.5+ induction motor +
        # Jiles-Atherton hysteretic inductor + dynamic PMSM) were built
        # ABOVE (so the PMSM bundle was available to ``_build_foc_loops``).
        # A dynamic PMSM observer integrates the d-q current ODE off the
        # terminal voltages each step — its back-EMF residual only stays
        # consistent if the kernel re-evaluates the nonlinear sources
        # between substeps. ``has_pmsm`` (computed above) forces
        # enable_nonlinear_refresh on below.
        #
        # Fold the device step-observers into the base observer, then the
        # FOC step-observers AFTER them — the FOC reads the d-q feedback
        # the PMSM observer just refreshed, so it MUST run last.
        all_post_observers = (
            list(device_step_observers)
            + list(foc_step_observers)
            + list(sixstep_step_observers)
        )
        if all_post_observers:
            base_step_observer = step_observer

            def step_observer(t: float, x: Any) -> None:  # noqa: F811
                base_step_observer(t, x)
                for obs in all_post_observers:
                    obs(t, x)

        composed_loop = self._build_closed_loops(
            circuit, builder, step_observer, t_start,
            external_switch_fn=switch_fn,
        )
        simulate_kwargs: dict[str, Any] = {"t_start": t_start}
        if composed_loop is not None:
            simulate_kwargs["closed_loops"] = [composed_loop]
        else:
            simulate_kwargs["switch_fn"] = switch_fn
            simulate_kwargs["step_observer"] = step_observer
        # Device residual injection (back-EMF / dM/dt) is independent
        # of the switch_fn / closed-loop path — always forward it when
        # a nonlinear device is present. The TypeError-retry below
        # strips it if the host kernel rejects the combination.
        if device_b_extra_fn is not None:
            simulate_kwargs["b_extra_fn"] = device_b_extra_fn
        live_stream = getattr(callbacks, "live_stream", None)
        if live_stream is not None:
            simulate_kwargs["live_stream"] = live_stream

        # Forward the pulsim 1.5 simulate() controls the GUI now
        # exposes in Simulation Settings. None ⇒ let pulsim defaults
        # decide. Unknown kwargs on older builds are silently dropped
        # in the TypeError-retry path below.
        if settings.max_newton_iterations > 0:
            simulate_kwargs["max_newton_iterations"] = int(
                settings.max_newton_iterations,
            )
        if settings.max_event_iterations > 0:
            simulate_kwargs["max_event_iterations"] = int(
                settings.max_event_iterations,
            )
        if settings.tol_newton_dx is not None:
            simulate_kwargs["tol_newton_dx"] = float(settings.tol_newton_dx)
        if settings.tol_newton_res is not None:
            simulate_kwargs["tol_newton_res"] = float(settings.tol_newton_res)
        simulate_kwargs["enable_newton_line_search"] = bool(
            settings.enable_newton_line_search,
        )
        simulate_kwargs["enable_newton_lm"] = bool(settings.enable_newton_lm)
        simulate_kwargs["enable_substep_state_correction"] = bool(
            settings.enable_substep_state_correction,
        )
        if settings.enable_nonlinear_refresh is not None:
            simulate_kwargs["enable_nonlinear_refresh"] = bool(
                settings.enable_nonlinear_refresh,
            )
        if has_pmsm:
            # PMSM back-EMF residual requires per-substep nonlinear
            # refresh — override whatever the settings default was.
            simulate_kwargs["enable_nonlinear_refresh"] = True
        if settings.start_from_dc_op:
            simulate_kwargs["start_from_dc_op"] = True

        # pulsim 1.6 engine selector. Only forward the DSED kwargs
        # when the user actually selected DSED — keeps the PWL path
        # byte-identical to v1.4.x for users who haven't opted in.
        # The TypeError-retry block below strips ``engine``/DSED
        # kwargs if the installed pulsim is older than 1.6 (so a
        # mismatched install doesn't crash, the user just loses the
        # DSED path until they upgrade).
        engine_value = str(getattr(settings, "engine", "pwl") or "pwl").lower()
        if engine_value == "dsed":
            simulate_kwargs["engine"] = "dsed"
            simulate_kwargs["rtol"] = float(settings.dsed_rtol)
            simulate_kwargs["atol"] = float(settings.dsed_atol)
            simulate_kwargs["dt_init"] = float(settings.dsed_dt_init)
            simulate_kwargs["integrator"] = str(
                getattr(settings, "dsed_integrator", "auto") or "auto"
            )
            simulate_kwargs["stiffness_threshold"] = float(
                settings.dsed_stiffness_threshold
            )
            simulate_kwargs["h_bdf2"] = float(settings.dsed_h_bdf2)

        try:
            res = self._module.simulate(
                builder, t_stop, dt,
                **simulate_kwargs,
            )
        except _SimulateCancelled:
            return ([], [], False, "Cancelled by user", None)
        except TypeError as exc:
            # Backwards-compat: older pulsim builds reject any of the
            # new ``max_newton_iterations`` / ``tol_newton_*`` /
            # ``enable_newton_*`` / ``start_from_dc_op`` /
            # ``live_stream`` kwargs the GUI now passes through from
            # Simulation Settings. Strip every unrecognised kwarg
            # mentioned in the error and retry once — keeps stale
            # kernels working while users upgrade.
            err_text = str(exc)
            new_kwargs = {
                "max_newton_iterations", "max_event_iterations",
                "tol_newton_dx", "tol_newton_res",
                "enable_newton_line_search", "enable_newton_lm",
                "enable_substep_state_correction",
                "enable_nonlinear_refresh", "start_from_dc_op",
                "live_stream",
                # pulsim 1.6 engine selector + DSED knobs. Older
                # kernels (pulsim < 1.6) reject these; the strip-and-
                # retry path drops them so the sim still runs on the
                # default PWL engine. Users on stale installs lose
                # the DSED speedup but don't see a crash.
                "engine",
                "rtol", "atol", "dt_init", "integrator",
                "stiffness_threshold", "h_bdf2",
                # Nonlinear-device residual injection (induction motor
                # back-EMF / hysteretic-inductor dM/dt). Stripped only
                # if a kernel rejects it alongside another kwarg combo;
                # losing it means the device's nonlinear term is absent,
                # but the sim still runs (degraded, not crashed).
                "b_extra_fn",
            }
            stripped = {
                k for k in list(simulate_kwargs.keys())
                if k in new_kwargs and k in err_text
            }
            if stripped:
                for key in stripped:
                    simulate_kwargs.pop(key, None)
                try:
                    res = self._module.simulate(
                        builder, t_stop, dt,
                        **simulate_kwargs,
                    )
                except _SimulateCancelled:
                    return ([], [], False, "Cancelled by user", None)
                except RuntimeError as exc2:
                    return ([], [], False, str(exc2), None)
            else:
                raise
        except RuntimeError as exc:
            return ([], [], False, str(exc), None)

        # Per-device electrothermal post-processing: walk every
        # device via pulsim.losses.device_loss_summary, build a quick
        # Foster network per loss-carrying device, and call
        # compute_temperature to get a junction-temperature trace.
        # The result is stashed in ``virtual_channels`` so the
        # backend adapter merges it into ``result.statistics`` and
        # ``result.signals`` — thermal_service can then build per-
        # device ThermalDeviceResult entries instead of the legacy
        # single "system" lump.
        composed_switch_fn = (
            composed_loop.switch_fn
            if composed_loop is not None
            else switch_fn
        )
        electrothermal_rows = self._compute_per_device_electrothermal(
            builder=builder,
            sim_result=res,
            switch_fn=composed_switch_fn,
            t_amb_celsius=25.0,
        )

        # Pull arrays in the same layout the legacy streaming API
        # produced. ``SimulationResult.states`` is a list of NumPy
        # vectors (one per timestep); ``times`` is a 1-D array.
        # ``virtual_channels`` carries the new T(device) temperature
        # traces + the electrothermal summary dict — those get merged
        # into ``result.signals`` / ``result.statistics`` by the
        # caller.
        virtual_payload = None
        if electrothermal_rows:
            virtual_payload = {
                "__electrothermal_rows__": electrothermal_rows,
                # Temperature traces keyed as ``T(<device>)`` so the
                # thermal_service's ``_collect_transient_thermal_traces``
                # finds them via its existing T(…)/T_<…> heuristics.
                **{
                    f"T({row['component_name']})": row["temperature_trace"]
                    for row in electrothermal_rows
                    if row.get("temperature_trace")
                },
            }
        return (
            list(res.times),
            [list(s) for s in res.states],
            True,
            "",
            virtual_payload,  # may carry T(<device>) traces +
                              # ``__electrothermal_rows__`` for the
                              # caller to merge into result.signals /
                              # statistics.
        )

    # Default Foster network: single-stage TO-220 ballpark
    # (R_th_jc ≈ 1.5 K/W, τ ≈ 75 ms). Used for every loss-carrying
    # device until the GUI threads per-device Foster params through.
    _DEFAULT_FOSTER_RTH = 1.5
    _DEFAULT_FOSTER_TAU = 0.075

    # Device kinds that ``device_thermal_summary`` /
    # ``device_loss_summary`` can model. Capacitors / sources are
    # skipped (no conduction-loss model).
    _LOSS_CARRYING_KINDS = frozenset(
        {"resistor", "inductor", "switch", "diode"}
    )

    def _compute_per_device_electrothermal(
        self,
        builder: Any,
        sim_result: Any,
        switch_fn: Any,
        t_amb_celsius: float,
    ) -> list[dict[str, Any]]:
        """Post-process device losses + per-device junction temperature.

        Primary path (pulsim ≥ 1.5): one
        ``pulsim.device_thermal_summary`` call that, per device,
        reconstructs the real per-step conduction power ``P_cond(t)``
        (NOT a constant ``P_avg`` approximation), layers the
        averaged switching / core loss, and convolves the result
        with the device's Foster network into a junction-temperature
        trace. Strictly more accurate than the legacy constant-power
        approximation for circuits whose conduction current isn't
        flat (everything switching).

        Fallback path (pulsim < 1.5 or any failure): the legacy
        ``device_loss_summary`` + manual ``compute_temperature``
        loop with a constant ``P_avg``.

        Both produce the same row shape that
        ``thermal_service._build_from_transient_backend_telemetry``
        consumes: ``component_name``, ``kind``, ``final_temperature``,
        ``peak_temperature``, ``conduction``, ``turn_on``,
        ``turn_off``, ``temperature_trace``.

        Returns ``[]`` if no thermal post-processing is possible —
        keeps the transient run from blowing up on a thermal-only
        failure.
        """
        rows = self._electrothermal_via_thermal_summary(
            builder, sim_result, switch_fn, t_amb_celsius,
        )
        if rows is not None:
            return rows
        # Either pulsim < 1.5 (no device_thermal_summary) or the
        # call raised — fall back to the legacy constant-power loop.
        return self._electrothermal_legacy_constant_power(
            builder, sim_result, switch_fn, t_amb_celsius,
        )

    def _electrothermal_via_thermal_summary(
        self,
        builder: Any,
        sim_result: Any,
        switch_fn: Any,
        t_amb_celsius: float,
    ) -> list[dict[str, Any]] | None:
        """Primary electrothermal path via pulsim 1.5's
        ``device_thermal_summary``.

        Returns ``None`` (signal the caller to fall back) when the
        function isn't importable or raises; returns a (possibly
        empty) row list otherwise.
        """
        try:
            from pulsim import device_thermal_summary
        except Exception:  # noqa: BLE001 - pulsim < 1.5
            return None

        FosterStage = getattr(self._module, "FosterStage", None)
        if FosterStage is None:
            return None

        # Enumerate the builder's branches and build a thermal_specs
        # entry for every loss-carrying device, each with the default
        # single-stage Foster network. Names come straight from
        # ``builder.components()`` so the strict-mode KeyError that
        # device_loss_summary now raises on unknown names can't fire.
        try:
            components = list(builder.components())
        except Exception:  # noqa: BLE001
            return None

        try:
            default_stage = FosterStage(
                R_th_K_per_W=self._DEFAULT_FOSTER_RTH,
                tau_s=self._DEFAULT_FOSTER_TAU,
            )
        except Exception:  # noqa: BLE001
            return None

        thermal_specs: dict[str, dict[str, Any]] = {}
        kind_by_name: dict[str, str] = {}
        for comp in components:
            name = str(comp.get("name") or "").strip()
            kind = str(comp.get("kind") or "").lower()
            if not name or kind not in self._LOSS_CARRYING_KINDS:
                continue
            thermal_specs[name] = {"stages": [default_stage]}
            kind_by_name[name] = kind

        if not thermal_specs:
            return []

        try:
            summary = device_thermal_summary(
                builder, sim_result,
                thermal_specs=thermal_specs,
                T_ambient_C=float(t_amb_celsius),
                switch_fn=switch_fn,
            )
        except Exception:  # noqa: BLE001 - kernel/version mismatch
            return None

        rows: list[dict[str, Any]] = []
        for entry in summary or []:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            trace = entry.get("T_j_trace")
            temp_list = (
                [float(v) for v in trace] if trace is not None else []
            )
            if not temp_list:
                continue
            p_cond = max(0.0, float(entry.get("P_cond_avg") or 0.0))
            p_sw = max(0.0, float(entry.get("P_sw_avg") or 0.0))
            p_core = max(0.0, float(entry.get("P_core_avg") or 0.0))
            # Skip devices that dissipate nothing (ideal inductors,
            # open switches) — they'd sit at ambient and only clutter
            # the thermal panel. Matches the legacy path's
            # ``P_avg <= 0: continue`` filter.
            if (p_cond + p_sw + p_core) <= 0.0:
                continue
            # thermal_service has conduction / switching_on /
            # switching_off / reverse_recovery buckets but no core
            # bucket. Core loss is continuous (like conduction), so
            # fold it into ``conduction``. Switching avg has no
            # on/off split from the summary, so report it under
            # ``turn_on`` (keeps total = cond + core + sw correct).
            rows.append({
                "component_name": name,
                "kind": kind_by_name.get(name, str(entry.get("kind") or "").lower()),
                "final_temperature": temp_list[-1],
                "peak_temperature": max(temp_list),
                "conduction": p_cond + p_core,
                "turn_on": p_sw,
                "turn_off": 0.0,
                "temperature_trace": temp_list,
            })
        return rows

    def _electrothermal_legacy_constant_power(
        self,
        builder: Any,
        sim_result: Any,
        switch_fn: Any,
        t_amb_celsius: float,
    ) -> list[dict[str, Any]]:
        """Legacy electrothermal path: ``device_loss_summary`` +
        constant-``P_avg`` Foster convolution. Used only when
        ``device_thermal_summary`` is unavailable (pulsim < 1.5) or
        raised. Behaviourally identical to the pre-1.5 GUI."""
        try:
            import numpy as np
            from pulsim.losses import device_loss_summary
        except Exception:  # noqa: BLE001
            return []

        try:
            summary = device_loss_summary(
                builder, sim_result,
                switch_fn=switch_fn,
            )
        except Exception:  # noqa: BLE001 - pulsim version mismatch / device kind unsupported
            return []

        if not summary:
            return []

        times = np.asarray(sim_result.times, dtype=float)
        if times.size < 2:
            return []

        try:
            stages = [
                self._module.FosterStage(
                    R_th_K_per_W=self._DEFAULT_FOSTER_RTH,
                    tau_s=self._DEFAULT_FOSTER_TAU,
                )
            ]
        except Exception:  # noqa: BLE001
            return []

        rows: list[dict[str, Any]] = []
        for entry in summary:
            name = str(entry.get("name") or "").strip()
            p_avg = float(entry.get("P_avg") or 0.0)
            if not name or p_avg <= 0.0:
                continue
            # Constant-power approximation: trace.shape == times.shape,
            # uniformly P_avg watts. compute_temperature convolves with
            # the Foster Z_th(t) → ΔT(t) → adds T_amb.
            p_arr = np.full_like(times, p_avg, dtype=float)
            try:
                temperature = self._module.compute_temperature(
                    times, p_arr, stages, t_amb_celsius,
                )
            except Exception:  # noqa: BLE001
                continue
            temp_list = [float(v) for v in temperature]
            if not temp_list:
                continue
            kind = str(entry.get("kind") or "").lower()
            rows.append({
                "component_name": name,
                "kind": kind,
                "final_temperature": temp_list[-1],
                "peak_temperature": max(temp_list),
                "conduction": p_avg,
                "turn_on": 0.0,
                "turn_off": 0.0,
                "temperature_trace": temp_list,
            })
        return rows

    def _build_nonlinear_device_observers(
        self,
        circuit: Any,
        builder: Any,
        dt: float,
    ) -> tuple[list[Callable[[float, Any], None]], Callable[[float], Any] | None]:
        """Build the simulate-time observers for every nonlinear device
        (induction motor, Jiles-Atherton hysteretic inductor) the
        converter recorded on ``circuit.nonlinear_observer_specs``.

        Each pulsim ``make_<kind>_observer(builder, handle, dt=dt)``
        returns a ``(step_observer, b_extra_fn)`` pair:

        * ``step_observer(t, x)`` advances the device's internal state
          (rotor flux + mechanical for the motor; J-A magnetisation for
          the inductor) once per simulation step.
        * ``b_extra_fn(t)`` returns the residual-vector contribution
          (back-EMF source voltages / dM/dt) the kernel adds each step.

        Returns ``([step_observers], combined_b_extra_fn)``. The
        b_extra functions are summed element-wise into one callable
        (``None`` when there are no devices). Any failure to build an
        observer is logged and skipped so one bad device doesn't kill
        the whole run.
        """
        specs = list(getattr(circuit, "nonlinear_observer_specs", []) or [])
        if not specs:
            return [], None

        ps = self._module
        step_observers: list[Callable[[float, Any], None]] = []
        b_extra_fns: list[Callable[[float], Any]] = []

        maker_by_kind = {
            "induction_motor": getattr(ps, "make_induction_motor_observer", None),
            "hysteretic_inductor": getattr(ps, "make_hysteretic_inductor_observer", None),
            # Dynamic PMSM (pulsim 1.6.4). make_pmsm_observer(builder,
            # motor, dt=) returns (step_observer, b_extra_fn): the
            # step advances the d-q current + mechanical ODE, b_extra
            # injects the rotating back-EMF into the residual. Needs
            # enable_nonlinear_refresh=True (set by the caller when a
            # pmsm spec is present).
            "pmsm": getattr(ps, "make_pmsm_observer", None),
        }

        for spec in specs:
            kind = str(spec.get("kind") or "")
            handle = spec.get("handle")
            maker = maker_by_kind.get(kind)
            if maker is None or handle is None:
                continue
            try:
                obs, b_extra = maker(builder, handle, dt=float(dt))
            except Exception:  # noqa: BLE001 - one bad device shouldn't abort
                continue
            if callable(obs):
                step_observers.append(obs)
            if callable(b_extra):
                b_extra_fns.append(b_extra)
            # For the dynamic PMSM, ``obs`` IS the MotorObserverBundle
            # (it is iterable as ``(bundle, b_extra_fn)`` and exposes live
            # trace lists ``.i_d``/``.i_q``/``.omega_rad_s``/``.theta_rad``).
            # Stash it back on the spec so ``_build_foc_loops`` can close
            # the current/speed loops over the fresh d-q feedback without
            # rebuilding (and double-stepping) the observer.
            if kind == "pmsm":
                spec["bundle"] = obs

        if not b_extra_fns:
            return step_observers, None

        if len(b_extra_fns) == 1:
            return step_observers, b_extra_fns[0]

        # Sum the per-device residual vectors element-wise. Each
        # b_extra_fn returns a full-length list[float]; the kernel adds
        # the result to the constant residual. Devices write into
        # disjoint source rows so summation is just element-wise add.
        def combined_b_extra(t: float) -> list[float]:
            total: list[float] | None = None
            for fn in b_extra_fns:
                vec = fn(t)
                if vec is None:
                    continue
                if total is None:
                    total = list(vec)
                else:
                    for i, v in enumerate(vec):
                        if i < len(total):
                            total[i] += v
            return total if total is not None else []

        return step_observers, combined_b_extra

    def _build_vsi_switch_fns(
        self,
        circuit: Any,
        builder: Any,
        exclude_names: set[str] | None = None,
    ) -> list[Callable[[float], Any]]:
        """Build one SPWM ``switch_fn`` per native 3φ VSI the converter
        recorded on ``circuit.vsi_specs``.

        ``exclude_names`` (optional) names VSIs to SKIP — used to omit any
        inverter that a FOC loop already drives via inverse Park/Clarke,
        so the open-loop SPWM and the FOC don't fight for the same six
        switch bits.

        Each spec carries the inverter's builder-global high/low-side
        switch indices (from ``add_three_phase_vsi``'s result) plus the
        SPWM drive parameters. We map them onto pulsim 1.6.4's
        ``ThreePhaseLegIndices(hs_a, ls_a, hs_b, ls_b, hs_c, ls_c)`` +
        ``make_three_phase_spwm_fn(carrier_f, mod_f, mod_index, legs,
        num_switches, dead_time, modulation_phase=…)``.

        The returned callables each emit a ``SwitchStateMask`` that sets
        ONLY that inverter's six bits (every other bit stays 0). The
        caller composes them with the rest of the circuit's switch_fn via
        ``make_combined_switch_fn`` (bitwise-OR), so a co-resident PFC
        boost MOSFET keeps its own gate pattern. Returns ``[]`` when no
        native VSI is present or the kernel lacks the SPWM helpers.
        """
        specs = list(getattr(circuit, "vsi_specs", []) or [])
        if not specs:
            return []

        ps = self._module
        make_spwm = getattr(ps, "make_three_phase_spwm_fn", None)
        leg_cls = getattr(ps, "ThreePhaseLegIndices", None)
        if make_spwm is None or leg_cls is None:
            return []

        num_switches = int(getattr(builder.graph, "num_switches", 0))
        if num_switches <= 0:
            return []

        skip = exclude_names or set()
        import math
        fns: list[Callable[[float], Any]] = []
        for spec in specs:
            if str(spec.get("name") or "") in skip:
                continue
            hs = list(spec.get("high_side_switch_indices") or [])
            ls = list(spec.get("low_side_switch_indices") or [])
            if len(hs) != 3 or len(ls) != 3:
                continue
            try:
                legs = leg_cls(
                    int(hs[0]), int(ls[0]),
                    int(hs[1]), int(ls[1]),
                    int(hs[2]), int(ls[2]),
                )
                fn = make_spwm(
                    float(spec.get("carrier_frequency", 10e3)),
                    float(spec.get("modulation_frequency", 50.0)),
                    float(spec.get("modulation_index", 0.8)),
                    legs,
                    num_switches,
                    float(spec.get("dead_time", 0.0)),
                    math.radians(float(spec.get("modulation_phase_deg", 0.0))),
                )
            except Exception:  # noqa: BLE001 - one bad VSI shouldn't abort
                continue
            if callable(fn):
                fns.append(fn)
        return fns

    def _build_foc_loops(
        self,
        circuit: Any,
        builder: Any,
    ) -> tuple[
        list[Callable[[float, Any], None]],
        list[Callable[[float], Any]],
        set[str],
    ]:
        """Build the simulate-time Field-Oriented-Control loop(s) the
        converter recorded on ``circuit.foc_loop_descriptors``.

        Each descriptor binds a FOC marker to a native 3φ VSI (the
        ``circuit.vsi_specs`` entry whose ``name`` matches ``vsi_name``)
        and a dynamic PMSM (the ``circuit.nonlinear_observer_specs`` entry
        whose ``name`` matches ``pmsm_name``). The PMSM spec carries the
        live ``MotorObserverBundle`` (stashed by
        :meth:`_build_nonlinear_device_observers`) exposing the d-q
        currents + rotor angle each step.

        Returns ``(step_observers, switch_fns, controlled_vsi_names)``:

        * Each ``step_observer(t, x)`` runs the cascaded PI law AFTER the
          PMSM observer has refreshed the bundle's d-q feedback for this
          step: an outer speed PI produces ``iq_ref`` (clamped), inner
          ``i_d``/``i_q`` PIs (with the standard cross-coupling +
          back-EMF decoupling) produce ``v_d``/``v_q`` (clamped to a
          fraction of the half-bus), and the electrical angle
          ``θ_e = pole_pairs · θ_mech`` is latched.
        * Each ``switch_fn(t)`` runs inverse Park (with ``θ_e``) →
          inverse Clarke → per-phase carrier comparison at the switching
          frequency, emitting a complementary SwitchStateMask on exactly
          that inverter's six bits.
        * ``controlled_vsi_names`` is the set of VSI names the FOC drives
          — the caller EXCLUDES these from the open-loop SPWM
          (``_build_vsi_switch_fns``) so the two never fight for the same
          switch bits.

        CRITICAL: the inverse Park uses the ELECTRICAL angle
        ``pole_pairs · θ_mech``. The bundle's ``theta_rad`` is the
        MECHANICAL angle; feeding it raw makes i_d explode and the rotor
        stall. Empty result (``[], [], set()``) when no FOC marker is
        present or a binding can't be resolved.
        """
        descriptors = list(getattr(circuit, "foc_loop_descriptors", []) or [])
        if not descriptors:
            return [], [], set()

        ps = self._module
        mask_cls = getattr(ps, "SwitchStateMask", None)
        if mask_cls is None:
            return [], [], set()

        num_switches = int(getattr(builder.graph, "num_switches", 0))
        if num_switches <= 0:
            return [], [], set()

        # Index the VSI specs + PMSM bundles by name for binding.
        vsi_by_name: dict[str, dict[str, Any]] = {}
        for spec in (getattr(circuit, "vsi_specs", []) or []):
            vsi_by_name[str(spec.get("name") or "")] = spec
        pmsm_by_name: dict[str, dict[str, Any]] = {}
        for spec in (getattr(circuit, "nonlinear_observer_specs", []) or []):
            if str(spec.get("kind") or "") == "pmsm":
                pmsm_by_name[str(spec.get("name") or "")] = spec

        import math

        step_observers: list[Callable[[float, Any], None]] = []
        switch_fns: list[Callable[[float], Any]] = []
        controlled_vsi_names: set[str] = set()

        for desc in descriptors:
            vsi_name = str(desc.get("vsi_name") or "")
            pmsm_name = str(desc.get("pmsm_name") or "")
            vsi_spec = vsi_by_name.get(vsi_name)
            pmsm_spec = pmsm_by_name.get(pmsm_name)
            if vsi_spec is None or pmsm_spec is None:
                continue
            bundle = pmsm_spec.get("bundle")
            if bundle is None:
                continue
            hs = [int(i) for i in (vsi_spec.get("high_side_switch_indices") or [])]
            ls = [int(i) for i in (vsi_spec.get("low_side_switch_indices") or [])]
            if len(hs) != 3 or len(ls) != 3:
                continue

            # --- resolve the DC-bus magnitude for normalisation ---------
            # The VSI half-bus (Vbus/2) normalises the modulation and sets
            # the voltage clamp. Prefer the descriptor's explicit value;
            # else read it off the live builder by probing the two DC-rail
            # nodes the topology registered, falling back to a sane VLT403U
            # default (360 V bus). The kernel exposes the rail nodes on the
            # PMSM/VSI topology result only indirectly, so we accept an
            # optional descriptor override and otherwise use the default.
            v_bus = float(desc.get("v_bus", 360.0))
            half_bus = max(1.0, 0.5 * v_bus)

            pole_pairs = int(pmsm_spec.get("pole_pairs", 0) or 0)
            if pole_pairs <= 0:
                handle = pmsm_spec.get("handle")
                pole_pairs = int(getattr(handle, "pole_pairs", 3) or 3)
            l_s = float(pmsm_spec.get("L_s", 0.0) or 0.0)
            psi = float(pmsm_spec.get("psi_pm", 0.0) or 0.0)
            if l_s <= 0.0 or psi <= 0.0:
                handle = pmsm_spec.get("handle")
                l_s = float(getattr(handle, "L_s_H", 12e-3) or 12e-3)
                psi = float(getattr(handle, "psi_pm_Wb", 0.05) or 0.05)

            kp_w = float(desc.get("speed_kp", 0.17))
            ki_w = float(desc.get("speed_ki", 6.0))
            kp_i = float(desc.get("current_kp", 45.0))
            ki_i = float(desc.get("current_ki", 24000.0))
            id_ref = float(desc.get("id_ref", 0.0))
            iq_lim = float(desc.get("iq_limit", 3.0))
            v_lim = float(desc.get("v_limit_frac", 0.92)) * half_bus
            ref_rpm = float(desc.get("speed_ref_rpm", 1800.0))
            ramp_s = max(1e-9, float(desc.get("speed_ramp_s", 0.10)))
            f_sw = float(desc.get("switching_frequency_hz", 20000.0))
            # Mechanical speed reference: 0 → ref_rpm over ramp_s, then hold.
            ref_rad_s = ref_rpm * 2.0 * math.pi / 60.0

            def _make_loop(
                bundle: Any = bundle,
                hs: list[int] = hs,
                ls: list[int] = ls,
                pole_pairs: int = pole_pairs,
                l_s: float = l_s,
                psi: float = psi,
                kp_w: float = kp_w, ki_w: float = ki_w,
                kp_i: float = kp_i, ki_i: float = ki_i,
                id_ref: float = id_ref, iq_lim: float = iq_lim,
                v_lim: float = v_lim, half_bus: float = half_bus,
                ref_rad_s: float = ref_rad_s, ramp_s: float = ramp_s,
                f_sw: float = f_sw,
            ) -> tuple[Callable[[float, Any], None], Callable[[float], Any]]:
                # Mutable per-loop FOC state (integrators + latched
                # commands). Mirrors the validated /tmp/foc_demo.py state.
                st = {
                    "iw": 0.0, "iiq": 0.0, "iid": 0.0,
                    "vd": 0.0, "vq": 0.0, "th_e": 0.0, "last": -1.0,
                }
                # Per-step command log ``(t, vd, vq, th_e)`` so the
                # switch_fn is a deterministic, REPLAYABLE function of t.
                # pulsim evaluates ``switch_fn(t_n)`` BEFORE
                # ``step_observer(t_n, x)`` each step, so a switch_fn that
                # closed over the live ``st`` would (a) lag by one step —
                # matching the standalone demo, good — but (b) break when
                # the electrothermal post-processor REPLAYS ``switch_fn``
                # at historical timesteps (``st`` is frozen at its final
                # value → a wrong, near-DC pattern → garbage loss). The
                # log + ``_lookup`` give the historically-correct command
                # for any queried t while preserving the one-step lag.
                log_t: list[float] = [0.0]
                log_cmd: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
                cursor = {"i": 0}

                def _clip(v: float, lo: float, hi: float) -> float:
                    return lo if v < lo else (hi if v > hi else v)

                def _wref(t: float) -> float:
                    frac = t / ramp_s
                    if frac > 1.0:
                        frac = 1.0
                    return ref_rad_s * frac

                def _lookup(t: float) -> tuple[float, float, float]:
                    # Last logged command with logged_t <= t (the most
                    # recent COMPLETED step's command). A monotonic forward
                    # cursor handles the in-order live + replay sweep in
                    # O(1) amortised; reset + rescan on a backward jump.
                    i = cursor["i"]
                    if i >= len(log_t) or log_t[i] > t:
                        i = 0
                    while i + 1 < len(log_t) and log_t[i + 1] <= t:
                        i += 1
                    cursor["i"] = i
                    return log_cmd[i]

                def step_observer(t: float, x: Any) -> None:
                    dt = 2e-6 if st["last"] < 0.0 else max(1e-9, t - st["last"])
                    st["last"] = t
                    # Latest observer feedback (bundle refreshed THIS step
                    # by the PMSM observer that runs before us).
                    try:
                        w = float(bundle.omega_rad_s[-1])
                        th = float(bundle.theta_rad[-1])
                        idm = float(bundle.i_d[-1])
                        iqm = float(bundle.i_q[-1])
                    except (IndexError, TypeError):
                        return
                    we = pole_pairs * w
                    # Outer speed PI -> iq_ref (clamped).
                    ew = _wref(t) - w
                    st["iw"] += ew * dt
                    iqref = _clip(kp_w * ew + ki_w * st["iw"], -iq_lim, iq_lim)
                    # Inner current PIs with cross-coupling + back-EMF
                    # decoupling (id_ref typically 0 for a non-salient PMSM).
                    eq = iqref - iqm
                    st["iiq"] += eq * dt
                    vq = kp_i * eq + ki_i * st["iiq"] + we * (l_s * idm + psi)
                    ed = id_ref - idm
                    st["iid"] += ed * dt
                    vd = kp_i * ed + ki_i * st["iid"] - we * l_s * iqm
                    st["vd"] = _clip(vd, -v_lim, v_lim)
                    st["vq"] = _clip(vq, -v_lim, v_lim)
                    # ELECTRICAL angle for the inverse Park (pp · θ_mech).
                    st["th_e"] = pole_pairs * th
                    # Append this step's command to the replay log (kept
                    # monotonic in t; duplicate-t guarded so a substep
                    # re-call doesn't corrupt the lookup ordering).
                    if t > log_t[-1]:
                        log_t.append(t)
                        log_cmd.append((st["vd"], st["vq"], st["th_e"]))
                    else:
                        log_cmd[-1] = (st["vd"], st["vq"], st["th_e"])

                _sqrt3_2 = math.sqrt(3.0) / 2.0

                def switch_fn(t: float) -> Any:
                    m = mask_cls(num_switches)
                    vd, vq, th_e = _lookup(t)
                    c = math.cos(th_e)
                    s = math.sin(th_e)
                    # Inverse Park (dq -> αβ).
                    va = vd * c - vq * s
                    vb = vd * s + vq * c
                    # Inverse Clarke (αβ -> abc).
                    v_a = va
                    v_b = -0.5 * va + _sqrt3_2 * vb
                    v_c = -0.5 * va - _sqrt3_2 * vb
                    # Symmetric triangle carrier in [-1, 1] at f_sw.
                    car = 4.0 * abs(((t * f_sw) % 1.0) - 0.5) - 1.0
                    for k, vk in enumerate((v_a, v_b, v_c)):
                        ref = vk / half_bus
                        if ref > 1.0:
                            ref = 1.0
                        elif ref < -1.0:
                            ref = -1.0
                        on = ref > car
                        m.set(hs[k], bool(on))
                        m.set(ls[k], bool(not on))
                    return m

                return step_observer, switch_fn

            step_obs, sw_fn = _make_loop()
            step_observers.append(step_obs)
            switch_fns.append(sw_fn)
            controlled_vsi_names.add(vsi_name)

        return step_observers, switch_fns, controlled_vsi_names

    def _build_sixstep_loops(
        self,
        circuit: Any,
        builder: Any,
    ) -> tuple[
        list[Callable[[float, Any], None]],
        list[Callable[[float], Any]],
        set[str],
    ]:
        """Build the simulate-time 6-step trapezoidal BLDC loop(s) the
        converter recorded on ``circuit.sixstep_loop_descriptors``.

        Structure mirrors :meth:`_build_foc_loops` so the call-site logic
        (post-observers, switch_fn composition, SPWM exclusion) treats
        them symmetrically. The difference is the control law:

        * **No d-q transforms.** An outer speed PI produces a duty
          ``d ∈ [0, duty_max]`` from ``(ω_ref − ω_mech)``. There are
          no inner current loops — current shape comes naturally from
          the BEMF trapezoid + line inductance.
        * **Sector table.** The electrical angle ``θ_e = pole_pairs ·
          θ_mech`` (plus a small ``sector_advance`` offset) is mapped
          to one of six sectors. Each sector designates exactly one
          high-side switch (modulated) and one low-side switch (always
          on for that sector). The remaining four switches are off.
          Standard right-hand trapezoidal BLDC table (BAS-ABA-CBA …):

              sector 0 (0..60°)    : A+ PWM, B- ON
              sector 1 (60..120°)  : A+ PWM, C- ON
              sector 2 (120..180°) : B+ PWM, C- ON
              sector 3 (180..240°) : B+ PWM, A- ON
              sector 4 (240..300°) : C+ PWM, A- ON
              sector 5 (300..360°) : C+ PWM, B- ON

        * **Sensorless (back-EMF ZCD approximation).** The user picked
          sensorless in the dialog. We read ``θ`` from the dynamic-PMSM
          observer bundle directly — that bundle's angle is what the
          back-EMF observer would estimate after lock-in, and the
          electrical-angle sector boundaries are exactly the BEMF
          zero-crossings. Open-loop startup (rotor initially
          stationary) is therefore the same low-speed warmup the
          observer needs to lock; if startup misbehaves the user can
          raise ``speed_ramp_s`` to give the observer more time.

        Returns ``(step_observers, switch_fns, controlled_vsi_names)``
        with identical contracts to ``_build_foc_loops``. Empty
        result when no SIXSTEP marker is present or a binding can't
        be resolved.
        """
        descriptors = list(
            getattr(circuit, "sixstep_loop_descriptors", []) or []
        )
        if not descriptors:
            return [], [], set()

        ps = self._module
        mask_cls = getattr(ps, "SwitchStateMask", None)
        if mask_cls is None:
            return [], [], set()

        num_switches = int(getattr(builder.graph, "num_switches", 0))
        if num_switches <= 0:
            return [], [], set()

        vsi_by_name: dict[str, dict[str, Any]] = {}
        for spec in (getattr(circuit, "vsi_specs", []) or []):
            vsi_by_name[str(spec.get("name") or "")] = spec
        pmsm_by_name: dict[str, dict[str, Any]] = {}
        for spec in (getattr(circuit, "nonlinear_observer_specs", []) or []):
            if str(spec.get("kind") or "") == "pmsm":
                pmsm_by_name[str(spec.get("name") or "")] = spec

        import math

        # Sector -> (high_side_phase_idx, low_side_phase_idx). Phases
        # are A=0, B=1, C=2. The PWM modulates the high-side leg; the
        # complementary low-side of the SAME phase stays off (so the
        # phase floats during the off-cycle, matching the trapezoidal
        # 2-of-6 BLDC convention rather than synchronous rectification).
        # The opposite-phase low-side carries return current, kept ON
        # for the full sector.
        _SECTOR_TABLE: tuple[tuple[int, int], ...] = (
            (0, 1),  # A+ PWM, B-
            (0, 2),  # A+ PWM, C-
            (1, 2),  # B+ PWM, C-
            (1, 0),  # B+ PWM, A-
            (2, 0),  # C+ PWM, A-
            (2, 1),  # C+ PWM, B-
        )

        step_observers: list[Callable[[float, Any], None]] = []
        switch_fns: list[Callable[[float], Any]] = []
        controlled_vsi_names: set[str] = set()

        for desc in descriptors:
            vsi_name = str(desc.get("vsi_name") or "")
            pmsm_name = str(desc.get("pmsm_name") or "")
            vsi_spec = vsi_by_name.get(vsi_name)
            pmsm_spec = pmsm_by_name.get(pmsm_name)
            if vsi_spec is None or pmsm_spec is None:
                continue
            bundle = pmsm_spec.get("bundle")
            if bundle is None:
                continue
            hs = [int(i) for i in (vsi_spec.get("high_side_switch_indices") or [])]
            ls = [int(i) for i in (vsi_spec.get("low_side_switch_indices") or [])]
            if len(hs) != 3 or len(ls) != 3:
                continue

            pole_pairs = int(pmsm_spec.get("pole_pairs", 0) or 0)
            if pole_pairs <= 0:
                handle = pmsm_spec.get("handle")
                pole_pairs = int(getattr(handle, "pole_pairs", 3) or 3)

            kp_w = float(desc.get("speed_kp", 0.0025))
            ki_w = float(desc.get("speed_ki", 0.05))
            duty_max = max(0.0, min(1.0, float(desc.get("duty_max", 0.95))))
            ref_rpm = float(desc.get("speed_ref_rpm", 1800.0))
            ramp_s = max(1e-9, float(desc.get("speed_ramp_s", 0.10)))
            f_sw = float(desc.get("switching_frequency_hz", 20000.0))
            advance_rad = (
                float(desc.get("sector_advance_deg", 0.0)) * math.pi / 180.0
            )
            ref_rad_s = ref_rpm * 2.0 * math.pi / 60.0

            def _make_loop(
                bundle: Any = bundle,
                hs: list[int] = hs,
                ls: list[int] = ls,
                pole_pairs: int = pole_pairs,
                kp_w: float = kp_w, ki_w: float = ki_w,
                duty_max: float = duty_max,
                ref_rad_s: float = ref_rad_s, ramp_s: float = ramp_s,
                f_sw: float = f_sw,
                advance_rad: float = advance_rad,
            ) -> tuple[Callable[[float, Any], None], Callable[[float], Any]]:
                # Per-loop state: integrator + latched (sector, duty).
                st = {
                    "iw": 0.0,
                    "duty": 0.0,
                    "sector": 0,
                    "last": -1.0,
                }
                # Log of (t, sector, duty) so switch_fn replays
                # deterministically — mirrors the FOC log+lookup pattern
                # for electrothermal post-processing correctness.
                log_t: list[float] = [0.0]
                log_cmd: list[tuple[int, float]] = [(0, 0.0)]
                cursor = {"i": 0}

                def _clip(v: float, lo: float, hi: float) -> float:
                    return lo if v < lo else (hi if v > hi else v)

                def _wref(t: float) -> float:
                    frac = t / ramp_s
                    if frac > 1.0:
                        frac = 1.0
                    return ref_rad_s * frac

                def _lookup(t: float) -> tuple[int, float]:
                    i = cursor["i"]
                    if i >= len(log_t) or log_t[i] > t:
                        i = 0
                    while i + 1 < len(log_t) and log_t[i + 1] <= t:
                        i += 1
                    cursor["i"] = i
                    return log_cmd[i]

                _two_pi = 2.0 * math.pi
                _sector_width = _two_pi / 6.0

                def step_observer(t: float, x: Any) -> None:
                    dt = 2e-6 if st["last"] < 0.0 else max(1e-9, t - st["last"])
                    st["last"] = t
                    try:
                        w = float(bundle.omega_rad_s[-1])
                        th = float(bundle.theta_rad[-1])
                    except (IndexError, TypeError):
                        return
                    # Outer speed PI -> duty (0..duty_max). No negative
                    # duty — direction comes from the commutation table,
                    # not a signed PWM.
                    ew = _wref(t) - w
                    st["iw"] += ew * dt
                    raw = kp_w * ew + ki_w * st["iw"]
                    st["duty"] = _clip(raw, 0.0, duty_max)
                    # Anti-windup: clamp integrator when output saturates.
                    if raw > duty_max:
                        st["iw"] -= ew * dt
                    elif raw < 0.0:
                        st["iw"] -= ew * dt
                    # Electrical angle + sector advance, wrapped to [0, 2π).
                    th_e = pole_pairs * th + advance_rad
                    th_e = th_e - _two_pi * math.floor(th_e / _two_pi)
                    st["sector"] = int(th_e / _sector_width) % 6
                    if t > log_t[-1]:
                        log_t.append(t)
                        log_cmd.append((st["sector"], st["duty"]))
                    else:
                        log_cmd[-1] = (st["sector"], st["duty"])

                def switch_fn(t: float) -> Any:
                    m = mask_cls(num_switches)
                    sector, duty = _lookup(t)
                    hp, lp = _SECTOR_TABLE[sector]
                    # Carrier: sawtooth in [0, 1) at f_sw. PWM ON while
                    # carrier < duty (standard up-counter compare).
                    car = (t * f_sw) % 1.0
                    pwm_on = car < duty
                    # All six bits explicitly written each call — never
                    # rely on the mask's default state.
                    for k in range(3):
                        m.set(hs[k], bool(k == hp and pwm_on))
                        m.set(ls[k], bool(k == lp))
                    return m

                return step_observer, switch_fn

            step_obs, sw_fn = _make_loop()
            step_observers.append(step_obs)
            switch_fns.append(sw_fn)
            controlled_vsi_names.add(vsi_name)

        return step_observers, switch_fns, controlled_vsi_names

    def _build_cblock_closed_loops(
        self,
        descriptors: list[dict[str, Any]],
        builder: Any,
        t_start: float,
    ) -> list[Any]:
        """Build a ClosedLoop per C_BLOCK control-loop descriptor.

        Each descriptor (emitted by the converter for a python_numba
        C_BLOCK regulating a PWM-driven switch) carries the control-law
        source, the feedback node, the switch device, the PWM
        frequency, and the sample time. We compile the source via
        :class:`FastBlockService` and return a duck-typed ClosedLoop
        whose:

        * ``step_observer(t, x)`` — throttled to the sample time —
          reads the feedback ``measured = x[fb_idx]``, calls the
          control law ``law(measured, setpoint, dt, state) → duty``,
          and stores the clamped duty;
        * ``switch_fn(t)`` — produces the PWM mask by comparing the
          carrier phase against the stored duty.

        Mirrors the duty/PWM mechanics ``bind_pi_to_switch`` runs
        internally, but with the user's compiled law in place of the
        PI. A descriptor that fails to compile or resolve is skipped
        (logged-silent) so one bad block doesn't abort the run.
        """
        if not descriptors:
            return []

        from pulsimgui.services.fast_block_service import (
            FastBlockCompileError,
            FastBlockService,
        )

        ps = self._module
        mask_cls = getattr(ps, "SwitchStateMask", None)
        if mask_cls is None:
            return []

        try:
            num_sw = int(builder.graph.num_switches)
        except Exception:  # noqa: BLE001
            num_sw = 1

        svc = FastBlockService()
        loops: list[Any] = []

        for desc in descriptors:
            try:
                source = str(desc.get("source") or "")
                n_states = max(0, int(desc.get("n_states", 1) or 1))
                law = svc.compile_control_law(source, n_states=n_states)
            except FastBlockCompileError:
                # Bad user code — skip this loop. (The properties-panel
                # "Validate" button is where the user gets the detailed
                # error; here we just keep the sim alive.)
                continue

            try:
                fb_idx = int(builder.node_id_of(str(desc["feedback_node"])))
                switch_idx = int(builder.switch_index_of(str(desc["switch_device"]))) \
                    if hasattr(builder, "switch_index_of") else int(desc.get("switch_index", 0))
            except Exception:  # noqa: BLE001
                continue

            freq = max(1.0, float(desc.get("pwm_frequency", 100_000.0)))
            t_pwm = 1.0 / freq
            sample_time = float(desc.get("sample_time", 0.0) or 0.0)
            # Default the control period to one PWM period when the
            # user left sample_time at 0 (continuous-ish).
            ctrl_dt = sample_time if sample_time > 0.0 else t_pwm
            setpoint = float(desc.get("setpoint_value", 0.0) or 0.0)
            duty_min = float(desc.get("output_min", 0.0))
            duty_max = float(desc.get("output_max", 1.0))
            arg_count = law.arg_count

            state = law.make_state()
            duty_cell = [max(duty_min, min(duty_max, 0.5))]
            last_update = [float(t_start) - ctrl_dt]

            def _make_observer(
                _law=law, _fb=fb_idx, _state=state, _duty=duty_cell,
                _last=last_update, _dt=ctrl_dt, _sp=setpoint,
                _argc=arg_count, _dmin=duty_min, _dmax=duty_max,
            ) -> Callable[[float, Any], None]:
                def observer(t: float, x: Any) -> None:
                    if (t - _last[0]) < _dt:
                        return
                    _last[0] = t
                    measured = float(x[_fb])
                    # Supply exactly ``_argc`` scalar arguments (the
                    # count BEFORE the trailing ``state`` param), in the
                    # canonical order [measured, setpoint, dt], padded
                    # with zeros, then the persistent state vector:
                    #   1 → control(measured, state)
                    #   2 → control(measured, setpoint, state)
                    #   3 → control(measured, setpoint, dt, state)
                    #   n → control(measured, setpoint, dt, 0…, state)
                    canonical = [measured, _sp, _dt]
                    if _argc <= len(canonical):
                        scalars = canonical[:_argc]
                    else:
                        scalars = canonical + [0.0] * (_argc - len(canonical))
                    try:
                        out = float(_law(*scalars, _state))
                    except Exception:  # noqa: BLE001
                        return
                    _duty[0] = max(_dmin, min(_dmax, out))
                return observer

            def _make_switch_fn(
                _idx=switch_idx, _freq=freq, _duty=duty_cell,
                _n=num_sw, _mask=mask_cls,
            ) -> Callable[[float], Any]:
                def switch_fn(t: float) -> Any:
                    phase = (t * _freq) % 1.0
                    mask = _mask(int(_n))
                    if phase < _duty[0]:
                        mask.set(int(_idx), True)
                    return mask
                return switch_fn

            from types import SimpleNamespace
            loops.append(SimpleNamespace(
                switch_fn=_make_switch_fn(),
                step_observer=_make_observer(),
            ))

        return loops

    def _build_pfc_loops(
        self,
        descriptors: list[dict[str, Any]],
        builder: Any,
        t_start: float,
    ) -> list[Any]:
        """Build one ``ClosedLoop`` per PFC boost controller descriptor.

        Each loop runs the cascaded outer-voltage / inner-current PI cascade
        with sine-modulated inner setpoint:

            outer_pi(V_bus_ref − V_bus, dt_outer) → I_pk_ref
            i_L_ref(t) = I_pk_ref · |V_rect(t)|/Vac_pk_nom
            duty(t)   = inner_pi(i_L_ref − i_L, dt_inner)
            switch_state(t) = (carrier(t) < duty)

        The outer PI ticks at ~1 kHz (slow enough that the 120 Hz bus ripple
        doesn't feed back into the current reference, fast enough to track
        load steps). The inner PI runs at the PWM rate (f_sw, default 65 kHz)
        via ``pulsim.bind_pi_to_switch``, with a closure that updates the
        shared ``I_pk_ref`` and reads the latest ``|V_rect|`` from the solver
        state on every inner-loop measurement call.

        Composes with the same machinery as the buck closed-loop and the
        C_BLOCK closed loops — returns ``[]`` when the pulsim kernel is too
        old to support ``bind_pi_to_switch`` or no descriptors are present.
        """
        if not descriptors:
            return []
        ps = self._module
        if not hasattr(ps, "bind_pi_to_switch") or not hasattr(ps, "PIController"):
            return []

        loops: list[Any] = []
        for desc in descriptors:
            try:
                v_bus_node = str(desc.get("v_bus_node") or "").strip()
                v_ac_node = str(desc.get("v_ac_node") or "").strip()
                mosfet_name = str(desc.get("mosfet_name") or "").strip()
                if not v_bus_node or not v_ac_node or not mosfet_name:
                    continue
                v_bus_idx = int(builder.node_id_of(v_bus_node))
                v_ac_idx = int(builder.node_id_of(v_ac_node))
            except Exception:  # noqa: BLE001 — bad descriptor → skip
                continue

            # Tuning + targets.
            v_bus_ref = float(desc.get("v_bus_ref", 400.0))
            i_pk_limit = float(desc.get("i_pk_limit", 20.0))
            duty_max = max(0.05, min(0.99, float(desc.get("duty_max", 0.95))))
            voltage_kp = float(desc.get("voltage_kp", 0.30))
            voltage_ki = float(desc.get("voltage_ki", 6.0))
            current_kp = float(desc.get("current_kp", 31.4))
            current_ki = float(desc.get("current_ki", 3140.0))
            vac_pk_nom = max(1.0, float(desc.get("vac_pk_nom", 325.0)))
            f_sw = max(1.0, float(desc.get("f_sw", 65_000.0)))
            soft_start_time = max(0.0, float(desc.get("soft_start_time", 0.05)))
            v_bus_initial = float(desc.get("v_bus_initial", 310.0))

            # Outer PI cadence: target ~1 kHz update. Coerce to a whole
            # number of PWM ticks so the throttle math is exact.
            T_pwm = 1.0 / f_sw
            outer_dt = 1.0e-3  # 1 ms = 1 kHz, well below 2·f_line
            outer_period_ticks = max(1, int(round(outer_dt / T_pwm)))

            outer_pi = ps.PIController(
                Kp=voltage_kp, Ki=voltage_ki,
                output_min=0.0, output_max=i_pk_limit,
            )
            inner_pi = ps.PIController(
                Kp=current_kp, Ki=current_ki,
                output_min=0.0, output_max=duty_max,
            )

            # Shared state between the outer cadence and the inner loop.
            # ``i_pk_ref``: latest output of the outer voltage PI.
            # ``v_rect_latest``: latest |V_rect(x)| sample (read on every
            #   inner-loop measurement call).
            # ``elapsed``: outer-PI ticks × outer_dt, used by the
            #   soft-start ramp.
            state: dict[str, Any] = {
                "i_pk_ref": 0.0,
                "v_rect_latest": 0.0,
                "tick": 0,
                "elapsed": 0.0,
            }

            def _ramped_v_bus_ref(
                elapsed: float,
                _v0=v_bus_initial,
                _v1=v_bus_ref,
                _T=soft_start_time,
            ) -> float:
                """Linear soft-start ramp on the outer voltage setpoint.

                Returns ``v_bus_initial`` at ``elapsed=0`` and grows to
                ``v_bus_ref`` at ``elapsed >= soft_start_time``. With the
                ramp in place the outer PI never sees the cold-start
                400 V − 0 V step that would otherwise saturate the
                integrator to ``i_pk_limit`` on the first millisecond.
                ``_T <= 0`` disables the ramp and matches the pre-1.1.2
                behaviour.
                """
                if _T <= 0.0 or elapsed >= _T:
                    return _v1
                return _v0 + (_v1 - _v0) * (elapsed / _T)

            def _measured_and_cascade(
                x,
                _outer_pi=outer_pi,
                _state=state,
                _v_bus_idx=v_bus_idx,
                _v_ac_idx=v_ac_idx,
                _outer_dt=outer_dt,
                _period=outer_period_ticks,
                _ramp=_ramped_v_bus_ref,
            ) -> float:
                _state["v_rect_latest"] = abs(float(x[_v_ac_idx]))
                _state["tick"] += 1
                if _state["tick"] >= _period:
                    _state["tick"] = 0
                    _state["elapsed"] += _outer_dt
                    v_bus_meas = float(x[_v_bus_idx])
                    _state["i_pk_ref"] = float(_outer_pi.update(
                        setpoint=_ramp(_state["elapsed"]),
                        measured=v_bus_meas,
                        dt=_outer_dt,
                    ))
                # See comment below; without a current-probe branch we
                # return 0 so the inner PI integrates toward the duty
                # ceiling and the outer voltage loop dominates.
                return 0.0

            # If the converter resolved a current-probe BRANCH name, prefer
            # it: the inner loop's measurement is the inductor current i_L.
            il_branch_name = str(desc.get("i_l_branch_name") or "").strip()
            if il_branch_name and hasattr(builder, "branch_index_of"):
                try:
                    il_idx = int(builder.branch_index_of(il_branch_name))
                except Exception:  # noqa: BLE001
                    il_idx = -1
            else:
                il_idx = -1

            if il_idx >= 0:
                def _measured_and_cascade(  # noqa: F811 — shadowed by design
                    x,
                    _outer_pi=outer_pi,
                    _state=state,
                    _v_bus_idx=v_bus_idx,
                    _v_ac_idx=v_ac_idx,
                    _outer_dt=outer_dt,
                    _period=outer_period_ticks,
                    _il_idx=il_idx,
                    _ramp=_ramped_v_bus_ref,
                ) -> float:
                    _state["v_rect_latest"] = abs(float(x[_v_ac_idx]))
                    _state["tick"] += 1
                    if _state["tick"] >= _period:
                        _state["tick"] = 0
                        _state["elapsed"] += _outer_dt
                        _state["i_pk_ref"] = float(_outer_pi.update(
                            setpoint=_ramp(_state["elapsed"]),
                            measured=float(x[_v_bus_idx]),
                            dt=_outer_dt,
                        ))
                    return float(x[_il_idx])

            # Sine-modulated inner setpoint: i_L_ref = I_pk_ref · |V_rect|/Vac_pk
            def _inner_setpoint(
                _t, _state=state, _vac_pk=vac_pk_nom,
            ) -> float:
                return _state["i_pk_ref"] * _state["v_rect_latest"] / _vac_pk

            try:
                loop = ps.bind_pi_to_switch(
                    builder,
                    pi=inner_pi,
                    measured=_measured_and_cascade,
                    setpoint=_inner_setpoint,
                    switch=mosfet_name,
                    freq=f_sw,
                    t_start=float(t_start),
                )
            except Exception:  # noqa: BLE001 — kernel rejected binding
                continue
            loops.append(loop)
        return loops

    def _build_closed_loops(
        self,
        circuit: Any,
        builder: Any,
        progress_observer: Callable[[float, Any], None],
        t_start: float,
        *,
        external_switch_fn: Callable[..., Any] | None = None,
    ) -> Any:
        """Wire ``pulsim.bind_pi_to_switch`` for every closed-loop the
        converter detected on ``circuit``.

        Returns a single duck-typed ``ClosedLoop`` (with ``.switch_fn``
        and ``.step_observer``) that:

        - Calls every detected loop's switch_fn (composed via
          ``make_combined_switch_fn``) so multi-loop schematics work.
        - Chains every loop's step_observer with the GUI's
          ``progress_observer`` so progress / cancel keep firing
          alongside the PI updates.

        Returns ``None`` when the circuit has no descriptors (open-loop
        or pre-1.4 path) so the caller falls back to the legacy static
        ``switch_fn`` + ``step_observer`` pair.
        """
        descriptors = list(getattr(circuit, "closed_loop_descriptors", []) or [])
        cblock_descriptors = list(
            getattr(circuit, "cblock_loop_descriptors", []) or []
        )
        pfc_descriptors = list(
            getattr(circuit, "pfc_loop_descriptors", []) or []
        )
        if not descriptors and not cblock_descriptors and not pfc_descriptors:
            return None

        ps = self._module
        if not hasattr(ps, "bind_pi_to_switch") or not hasattr(ps, "PIController"):
            # Older kernel — silently skip the closed-loop path so the
            # legacy static switch_fn at least drives the MOSFET.
            return None

        real_loops: list[Any] = []
        for desc in descriptors:
            try:
                pi = ps.PIController(
                    Kp=float(desc.get("kp", 0.1)),
                    Ki=float(desc.get("ki", 100.0)),
                    output_min=float(desc.get("output_min", 0.0)),
                    output_max=float(desc.get("output_max", 1.0)),
                )
                # Inner-loop feedback can be voltage (single node) or
                # current (computed from two nodes + a bypass R).
                feedback_kind = str(desc.get("feedback_kind") or "voltage")
                if feedback_kind == "current":
                    n_in = int(builder.node_id_of(
                        str(desc["feedback_node_in"])
                    ))
                    n_out_raw = str(desc.get("feedback_node_out") or "0")
                    # "0" / "gnd" sentinel for the ground rail
                    if n_out_raw in {"0", "gnd", ""}:
                        n_out = -1
                    else:
                        n_out = int(builder.node_id_of(n_out_raw))
                    bypass_r = max(float(desc.get("feedback_bypass_r", 1e-4)),
                                    1e-12)

                    def _measured_current(x, _in=n_in, _out=n_out,
                                           _r=bypass_r) -> float:
                        v_in = float(x[_in])
                        v_out = 0.0 if _out < 0 else float(x[_out])
                        return (v_in - v_out) / _r

                    measured_fn = _measured_current
                else:
                    feedback_node = str(desc["feedback_node"])
                    node_idx = int(builder.node_id_of(feedback_node))
                    measured_fn = (lambda x, _i=node_idx: float(x[_i]))
            except Exception:  # noqa: BLE001 — bad descriptor → skip
                continue

            # Cascaded? Build a time-varying setpoint that's the
            # output of an outer PI controller. The outer PI runs at
            # its OWN sample rate (typically slower than the PWM)
            # via a throttle counter in the inner ``measured``
            # closure — see the cascaded block below.
            outer_spec = desc.get("outer_pi") if isinstance(desc.get("outer_pi"), dict) else None
            if outer_spec is not None:
                try:
                    outer_pi = ps.PIController(
                        Kp=float(outer_spec.get("kp", 0.1)),
                        Ki=float(outer_spec.get("ki", 100.0)),
                        output_min=float(outer_spec.get("output_min", 0.0)),
                        output_max=float(outer_spec.get("output_max", 1.0)),
                    )
                    outer_fb_node = str(outer_spec["feedback_node"])
                    outer_fb_neg_node = str(outer_spec.get("feedback_node_neg") or "0")
                    outer_fb_idx = int(builder.node_id_of(outer_fb_node))
                    outer_fb_neg_idx = (
                        -1 if outer_fb_neg_node in {"0", "gnd", ""}
                        else int(builder.node_id_of(outer_fb_neg_node))
                    )
                    outer_setpoint_val = float(outer_spec.get("setpoint_value", 0.0))
                    pwm_freq = float(desc.get("pwm_frequency", 100_000.0))
                    T_pwm = 1.0 / max(pwm_freq, 1.0)
                    # Outer PI sample period. If the descriptor carries
                    # an explicit ``sample_time``, use that; otherwise
                    # default to 1 ms so the voltage loop runs at
                    # 1 kHz — slow enough that the integrator doesn't
                    # wind up over a single PWM cycle, fast enough to
                    # track DC-bus transients in normal use.
                    outer_dt = float(outer_spec.get("sample_time") or 1.0e-3)
                    if outer_dt < T_pwm:
                        # Outer can't be faster than the inner PWM tick
                        outer_dt = T_pwm
                    # How many PWM ticks per outer update
                    outer_period_ticks = max(1, int(round(outer_dt / T_pwm)))
                except Exception:  # noqa: BLE001
                    outer_spec = None  # fall through to single-loop binding

            if outer_spec is not None:
                # Cascaded path: shared cell stores the outer PI's last
                # output and a throttle counter. The INNER
                # ``measured_fn`` wraps the raw one — every call ticks
                # the throttle, and the outer PI updates only when
                # ``outer_period_ticks`` PWM cycles have elapsed.
                outer_state: dict[str, Any] = {
                    "output": outer_setpoint_val * 0.0,
                    "tick": 0,
                }
                inner_measured_raw = measured_fn

                def _measured_and_tick_outer(
                    x,
                    _outer_pi=outer_pi,
                    _outer_sp=outer_setpoint_val,
                    _fb_idx=outer_fb_idx,
                    _fb_neg_idx=outer_fb_neg_idx,
                    _outer_dt=outer_dt,
                    _period=outer_period_ticks,
                    _state=outer_state,
                    _inner=inner_measured_raw,
                ) -> float:
                    _state["tick"] += 1
                    if _state["tick"] >= _period:
                        _state["tick"] = 0
                        v_pos = float(x[_fb_idx])
                        v_neg = 0.0 if _fb_neg_idx < 0 else float(x[_fb_neg_idx])
                        outer_meas = v_pos - v_neg
                        _state["output"] = float(_outer_pi.update(
                            setpoint=_outer_sp,
                            measured=outer_meas,
                            dt=_outer_dt,
                        ))
                    return _inner(x)

                setpoint_callable: Any = (
                    lambda _t, _s=outer_state: _s["output"]
                )
                loop = ps.bind_pi_to_switch(
                    builder,
                    pi=pi,
                    measured=_measured_and_tick_outer,
                    setpoint=setpoint_callable,
                    switch=str(desc["switch_device"]),
                    freq=float(desc.get("pwm_frequency", 100_000.0)),
                    t_start=float(t_start),
                )
            else:
                loop = ps.bind_pi_to_switch(
                    builder,
                    pi=pi,
                    measured=measured_fn,
                    setpoint=float(desc.get("setpoint_value", 0.0)),
                    switch=str(desc["switch_device"]),
                    freq=float(desc.get("pwm_frequency", 100_000.0)),
                    t_start=float(t_start),
                )
            real_loops.append(loop)

        # C_BLOCK control loops (pulsim 1.5 fast_block). Each compiles
        # its Python control law and runs it as a duty-driving loop —
        # same shape as the PI loops above, so it composes into the
        # combined switch_fn + observer transparently.
        real_loops.extend(
            self._build_cblock_closed_loops(cblock_descriptors, builder, t_start)
        )
        # Closed-loop PFC boost (cascaded outer voltage / inner current
        # PI with sine-modulated inner setpoint). Drops in as additional
        # ClosedLoop entries that the composition code handles the same
        # way as the other PI loops.
        real_loops.extend(
            self._build_pfc_loops(
                getattr(circuit, "pfc_loop_descriptors", []) or [],
                builder, t_start,
            )
        )

        if not real_loops:
            return None

        # Compose the switch_fns over the full switch count so each
        # loop's OR mask layers correctly.
        try:
            num_sw = int(builder.graph.num_switches)
        except Exception:  # noqa: BLE001
            num_sw = max(getattr(circuit, "num_switches", 0), 1)

        loop_switch_fns: list[Any] = [loop.switch_fn for loop in real_loops]
        # When the host wires additional switch_fns (e.g. the FOC inverse-
        # Park/Clarke driver + open-loop SPWM for non-FOC VSIs), include
        # them in the OR so the PFC closed_loops path doesn't accidentally
        # drop the inverter drive. Tested via the FOC + PFC compressor
        # example: motor was stuck at 0 A before this composition.
        if external_switch_fn is not None:
            loop_switch_fns.append(external_switch_fn)

        if hasattr(ps, "make_combined_switch_fn"):
            combined_sw = ps.make_combined_switch_fn(
                num_sw, loop_switch_fns,
            )
        else:
            # Older kernel: chain by hand using SwitchStateMask OR.
            mask_cls = ps.SwitchStateMask

            def combined_sw(t: float, _fns=tuple(loop_switch_fns),
                             _n=num_sw, _mask=mask_cls) -> Any:
                out = _mask(int(_n))
                for fn in _fns:
                    sub = fn(t)
                    for bit in range(int(_n)):
                        if sub.is_on(bit):
                            out.turn_on(bit)
                return out

        loop_observers = [loop.step_observer for loop in real_loops]

        def composed_observer(t: float, x: Any,
                                _obs=tuple(loop_observers),
                                _prog=progress_observer) -> None:
            for obs in _obs:
                obs(t, x)
            _prog(t, x)

        # Duck-typed ``ClosedLoop``: pulsim's ``simulate`` only reads
        # ``.switch_fn`` and ``.step_observer`` off each entry in
        # ``closed_loops``, so a SimpleNamespace is sufficient — no
        # need to subclass the frozen dataclass.
        from types import SimpleNamespace
        return SimpleNamespace(
            switch_fn=combined_sw,
            step_observer=composed_observer,
        )

    # ------------------------------------------------------------------
    # Pulsim 1.3+ compute_dc_op() routing (post-namespace-flatten path)
    # ------------------------------------------------------------------
    def _should_use_compute_dc_op_v13(self) -> bool:
        """True iff host pulsim exposes ``compute_dc_op`` and no
        longer ships the v0 ``dc_operating_point`` / ``solve_dc``
        entry points. The legacy v0/v1 builds still answer
        ``hasattr(module, "dc_operating_point")``, so the predicate
        sleeps for them and the original fallback ladder takes
        over."""
        if not hasattr(self._module, "compute_dc_op"):
            return False
        return not hasattr(self._module, "dc_operating_point")

    def _run_dc_compute_op_v13(
        self,
        circuit: Any,
        settings: DCSettings,
        circuit_data: dict | None = None,
    ) -> DCResult:
        """Compute the DC operating point through pulsim 1.3+'s
        ``compute_dc_op(builder, strategy=…)``.

        The v1.3 entry point returns just an ``np.ndarray`` — the
        state vector. There's no per-iteration history, no explicit
        success / message, no problematic-variable list; failure
        manifests as a ``RuntimeError`` when ``strategy="auto"`` runs
        out of fallbacks. We map that into the same
        :class:`DCResult` shape the legacy paths produced so callers
        don't notice the rewire.

        Node voltages are extracted from the front of the state
        vector via the shim's ``_node_id_to_name`` map (i-th entry =
        voltage at node ``i`` once ground is filtered out).
        ``branch_currents`` / ``power_dissipation`` are left empty
        for now — the shim doesn't track branch-index → device-name
        mappings yet, and the eventual users of those fields
        (loss-thermal dashboards, etc.) consume them from the
        transient path anyway.
        """
        # The shim exposes ``Circuit.builder`` for the underlying
        # CircuitBuilder; fall back to ``circuit`` itself for raw
        # builders in case a test mock passes one.
        builder = getattr(circuit, "builder", circuit)

        # Pick the strategy from settings if the GUI surfaces one,
        # otherwise let ``compute_dc_op`` auto-cascade through naive
        # → pseudo_trans → source_step.
        strategy = (
            getattr(settings, "dc_strategy", None) or "auto"
        )
        strategy = str(strategy).strip().lower() or "auto"
        if strategy not in {"auto", "naive", "pseudo_trans", "source_step"}:
            strategy = "auto"

        # v1.5 lands `should_continue=` on every long-running analysis;
        # forward the GUI's cancel-check so the Cancel button preempts
        # the DC Newton between strategy fallbacks (Auto path). Older
        # pulsim builds don't accept the kwarg — try/TypeError-fallback
        # for graceful degradation.
        cancel_fn = getattr(callbacks, "check_cancelled", None)
        sc_kw: dict = {}
        if cancel_fn is not None:
            sc_kw["should_continue"] = lambda: not cancel_fn()
        try:
            try:
                state = self._module.compute_dc_op(
                    builder, strategy=strategy, **sc_kw)
            except TypeError:
                state = self._module.compute_dc_op(builder, strategy=strategy)
        except RuntimeError as exc:
            return DCResult(
                error_message=str(exc),
                convergence_info=ConvergenceInfo(
                    converged=False,
                    failure_reason=str(exc),
                    strategy_used=strategy,
                ),
            )

        # Map the state vector back to a {node_name: voltage} dict
        # the GUI's DC-results panel expects. The shim's node map
        # has gnd at id ``-1`` and the real nodes at consecutive ids
        # ``0, 1, 2, …`` matching the builder's enumeration.
        node_voltages: dict[str, float] = {}
        id_to_name = getattr(circuit, "_node_id_to_name", {}) or {}
        n_nodes_in_state = min(int(builder.graph.num_nodes), len(state))
        for node_id in range(n_nodes_in_state):
            name = id_to_name.get(node_id)
            if not name or name == "gnd":
                continue
            try:
                node_voltages[name] = float(state[node_id])
            except (TypeError, ValueError, IndexError):
                continue
        # Ground is by convention 0 V — the GUI's results panel
        # tends to list it explicitly so DC reports look complete.
        node_voltages.setdefault("gnd", 0.0)

        # Build a DCResult with full success diagnostics. The
        # ``strategy_used`` value reports what the user (or
        # ``auto``) requested; the actual strategy that won inside
        # ``compute_dc_op`` is not exposed back to Python at the
        # moment.
        info = ConvergenceInfo(
            converged=True,
            iterations=0,
            final_residual=0.0,
            strategy_used=strategy,
        )
        return DCResult(
            node_voltages=node_voltages,
            branch_currents={},
            power_dissipation={},
            convergence_info=info,
            error_message="",
        )

    # ------------------------------------------------------------------
    # Pulsim 1.3+ AC sweep routing (post-namespace-flatten path)
    # ------------------------------------------------------------------
    def _should_use_ac_sweep_v13(self) -> bool:
        """True iff host pulsim ships the modern AC entry points
        (``run_ac_sweep`` / ``run_mna_sweep``) AND no longer exposes
        any of the legacy ones (``run_ac`` / ``run_ac_analysis`` /
        ``run_small_signal`` / ``ACAnalysis``)."""
        modern = hasattr(self._module, "run_ac_sweep") or hasattr(
            self._module, "run_mna_sweep"
        )
        if not modern:
            return False
        legacy = any(
            hasattr(self._module, name)
            for name in (
                "run_ac",
                "run_ac_analysis",
                "run_small_signal",
                "ACAnalysis",
            )
        )
        return not legacy

    def _run_ac_sweep_v13(
        self,
        circuit: Any,
        settings: ACSettings,
    ) -> ACResult:
        """Frequency sweep through pulsim 1.3+'s impulse-FFT API.

        Uses ``run_mna_sweep(builder, freqs=, output_idx=, …)`` —
        one transient with an impulse + FFT to extract H(f). Fast
        for linear circuits, which is what the GUI's AC panel
        targets in 99 % of cases. The swept-sine variant
        (``run_ac_sweep``) is more accurate for nonlinear small-
        signal but requires a hand-written ``excite_fn``; the GUI
        doesn't surface that knob yet.

        The result is mapped into the GUI's :class:`ACResult` shape:
        ``frequencies`` is the log-spaced grid from
        ``ACSettings.f_start`` / ``f_stop`` / ``points_per_decade``;
        ``magnitude`` and ``phase`` are dicts keyed by output-node
        name. Multiple ``output_nodes`` are run as separate sweeps —
        each is a fresh impulse response.
        """
        import math
        import numpy as np

        builder = getattr(circuit, "builder", circuit)

        # Log-spaced frequency grid the GUI expects to see in the
        # result. Pulsim's MNA sweep accepts an explicit ``freqs=``
        # parameter and interpolates internally onto it, so we set
        # the grid once and reuse it across outputs.
        f_lo = max(float(settings.f_start), 1e-9)
        f_hi = max(float(settings.f_stop), f_lo * 10.0)
        ppd = max(int(settings.points_per_decade), 1)
        n_decades = max(1.0, math.log10(f_hi / f_lo))
        n_points = max(2, int(round(ppd * n_decades)) + 1)
        freqs = np.logspace(math.log10(f_lo), math.log10(f_hi), n_points)

        # Solver time-step: must satisfy Nyquist for ``f_hi``.
        dt = 1.0 / (4.0 * f_hi)
        # Total horizon: ≥ 10 / f_lo for clean low-frequency reading.
        t_end = max(10.0 / f_lo, 100.0 * dt)

        outputs = list(settings.output_nodes) or []
        if not outputs:
            return ACResult(
                error_message=(
                    "AC analysis requires at least one output node. "
                    "Add a node to ACSettings.output_nodes."
                ),
            )

        magnitude: dict[str, list[float]] = {}
        phase: dict[str, list[float]] = {}

        for node_name in outputs:
            # Translate node name to state-vector index. Shim
            # circuits expose ``get_node(name) -> int``; legacy
            # backends use ``node_id_of``. Try shim first.
            output_idx = None
            getter = getattr(circuit, "get_node", None)
            if callable(getter):
                idx = getter(node_name)
                if isinstance(idx, int) and idx >= 0:
                    output_idx = idx
            if output_idx is None and hasattr(builder, "node_id_of"):
                try:
                    idx = builder.node_id_of(node_name)
                    if isinstance(idx, int) and idx >= 0:
                        output_idx = idx
                except Exception:
                    pass
            if output_idx is None:
                magnitude[node_name] = []
                phase[node_name] = []
                continue

            try:
                sweep_kwargs: dict[str, Any] = dict(
                    output_idx=output_idx,
                    dt=dt,
                    t_end=t_end,
                    freqs=list(freqs),
                )
                input_branch = self._resolve_ac_input_branch_id(
                    builder, settings
                )
                if input_branch is not None:
                    sweep_kwargs["v_in_branch_id"] = input_branch
                # v1.5: forward Cancel button into the AC sweep so it
                # preempts between frequency points (50-point sweep
                # would otherwise block the GUI for several seconds).
                cancel_fn = getattr(callbacks, "check_cancelled", None)
                if cancel_fn is not None:
                    sweep_kwargs["should_continue"] = lambda: not cancel_fn()
                try:
                    sweep_res = self._module.run_mna_sweep(
                        builder, **sweep_kwargs
                    )
                except TypeError:
                    sweep_kwargs.pop("should_continue", None)
                    sweep_res = self._module.run_mna_sweep(
                        builder, **sweep_kwargs
                    )
            except Exception as exc:  # pragma: no cover - failure path
                return ACResult(
                    error_message=(
                        f"run_mna_sweep failed for output '{node_name}': "
                        f"{type(exc).__name__}: {exc}"
                    ),
                )

            # ``MnaSweepResult`` exposes ``.freqs`` (NumPy array),
            # ``.H`` (complex), ``.mag_dB`` and ``.phase_deg`` as
            # the Bode-extracted pair. Fall back to computing them
            # from ``H`` if the convenience fields are absent.
            mag_db = getattr(sweep_res, "mag_dB", None)
            phase_deg = getattr(sweep_res, "phase_deg", None)
            if mag_db is None or phase_deg is None:
                H = np.asarray(sweep_res.H)
                mag_db = 20.0 * np.log10(np.maximum(np.abs(H), 1e-30))
                phase_deg = np.unwrap(np.angle(H)) * 180.0 / math.pi
            magnitude[node_name] = [float(x) for x in mag_db]
            phase[node_name] = [float(x) for x in phase_deg]

        return ACResult(
            frequencies=[float(f) for f in freqs],
            magnitude=magnitude,
            phase=phase,
            error_message="",
        )

    @staticmethod
    def _resolve_ac_input_branch_id(
        builder: Any,
        settings: ACSettings,
    ) -> int | None:
        """Find the branch id of the input source ``run_mna_sweep``
        should perturb. Tries the explicit ``settings.input_source``
        name first; falls back to the first voltage source in
        builder-call order. Returns ``None`` when no source can be
        identified (caller then lets pulsim's default kick in).

        v1.3's ``builder.components()`` lists every device with
        ``{"kind", "name", "branch_id", ...}`` in insertion order, so
        we walk it looking for a matching name. The lookup is name-
        first (cheaper / unambiguous) with a kind-based fallback so
        a circuit that omits the input-source name still works.
        """
        components = []
        getter = getattr(builder, "components", None)
        if callable(getter):
            try:
                components = list(getter())
            except Exception:
                components = []
        if not components:
            return None

        wanted_name = (settings.input_source or "").strip()
        if wanted_name:
            for entry in components:
                if str(entry.get("name", "")).strip() == wanted_name:
                    return int(entry.get("branch_id", -1))

        # Fallback: the first voltage / sine / pulse / PWM source in
        # the builder. This matches pulsim's own ``run_buck`` example
        # which calls ``run_mna_sweep`` without naming the source
        # explicitly because the buck has exactly one source.
        source_kinds = {
            "voltage_source",
            "sine_voltage_source",
            "pulse_voltage_source",
            "pwm_voltage_source",
            "current_source",
        }
        for entry in components:
            if str(entry.get("kind", "")).lower() in source_kinds:
                return int(entry.get("branch_id", -1))
        return None

    # ------------------------------------------------------------------
    # Pulsim 1.3+ thermal routing (post-namespace-flatten path)
    # ------------------------------------------------------------------
    def _should_use_thermal_v13(self) -> bool:
        """True iff host pulsim exposes the modern thermal surface
        (``compute_temperature`` and/or the ``FosterStage`` /
        ``add_foster_network`` helpers) AND no longer ships the
        legacy ``ThermalSimulator`` /
        ``create_simple_thermal_model``."""
        modern = hasattr(self._module, "compute_temperature") or hasattr(
            self._module, "add_foster_network"
        )
        if not modern:
            return False
        legacy = hasattr(self._module, "ThermalSimulator") or hasattr(
            self._module, "create_simple_thermal_model"
        )
        return not legacy

    def _run_thermal_compute_v13(
        self,
        circuit: Any,
        electrical_result: TransientResult,
        settings: ThermalSettings,
    ) -> ThermalResult:
        """System-level thermal estimate via pulsim 1.3's
        ``compute_temperature`` post-hoc convolution.

        v1.3's thermal philosophy is "Foster network inside the
        electrical simulation": ``add_foster_network(builder, …)``
        at build time + ``make_thermal_observer`` for live trace
        capture. The GUI's existing thermal pane is a post-transient
        analysis, so we use the standalone ``compute_temperature(t,
        P, foster_stages, T_amb)`` helper — convolve P(t) with the
        Foster Z_th(t) to get ΔT_j(t).

        Today the result is **system-level** rather than per-device:
        the GUI's electrical result doesn't track per-device
        instantaneous power, so we estimate total system loss from
        the source-side power-in trace (when available) and present
        a single virtual ``"system"`` device with default Foster
        stages. Per-device thermal awaits a branch-index ↔
        device-name map + per-device loss instrumentation; tracked
        for a follow-up PR.
        """
        import numpy as np

        times = list(electrical_result.time or [])
        if len(times) < 2:
            return ThermalResult(
                error_message=(
                    "Thermal analysis needs a transient time series — "
                    "run a transient first, then re-run thermal."
                ),
                is_synthetic=False,
            )

        # Estimate total system power from the electrical result.
        # The GUI's TransientResult stores per-signal time series
        # in ``signals``; we sum the named-power probe channels if
        # the GUI surfaced any, otherwise fall back to zero and
        # report a synthetic-ish result so the user sees the
        # ambient line plus a warning rather than a blank panel.
        power_trace = self._estimate_total_power(electrical_result, times)

        # Sensible default Foster stages — a fast die-to-case stage
        # plus a slow case-to-ambient stage. Roughly matches a
        # TO-247-style MOSFET sitting on a small heatsink. Users
        # who want device-specific values can populate
        # ``settings.foster_stages`` once that field exists; for
        # now the GUI doesn't carry it so we use these defaults.
        default_stages = self._default_foster_stages()

        try:
            FosterStageCls = self._module.FosterStage
            # v1.3's FosterStage takes (R_th_K_per_W, tau_s) — note
            # different field names than the GUI's FosterStage
            # (which uses ``resistance`` / ``capacitance``).
            stages_module = [
                FosterStageCls(
                    float(stage.resistance),
                    float(stage.time_constant),
                )
                for stage in default_stages
            ]
            t_arr = np.asarray(times, dtype=float)
            p_arr = np.asarray(power_trace, dtype=float)
            t_amb_celsius = float(settings.ambient_temperature)
            # v1.3 ``compute_temperature`` works in absolute units
            # (Kelvin or Celsius — it just convolves ΔT and adds
            # T_amb back). The GUI surfaces Celsius so we stay
            # in Celsius the whole way.
            # ``_run_thermal_compute_v13`` runs OUTSIDE the transient
            # callback chain (post-processing convolution that takes
            # well under a second for typical traces), so it doesn't
            # have a ``callbacks`` arg to read ``check_cancelled``
            # from. The earlier ``cancel_fn = getattr(callbacks, …)``
            # raised ``NameError`` and bricked the Thermal Viewer
            # whenever the user clicked the action. Just call
            # ``compute_temperature`` plain — cancel support can be
            # added back once ``ThermalAnalysisService.build_result``
            # passes its own callbacks down.
            try:
                t_j = self._module.compute_temperature(
                    t_arr, p_arr, stages_module, t_amb_celsius,
                )
            except TypeError:
                t_j = self._module.compute_temperature(
                    t_arr, p_arr, stages_module, t_amb_celsius
                )
        except Exception as exc:
            return ThermalResult(
                error_message=(
                    f"compute_temperature failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
                is_synthetic=False,
            )

        t_j_list = [float(v) for v in t_j]
        peak = float(max(t_j_list, default=t_amb_celsius))
        steady = float(
            sum(t_j_list[-min(50, len(t_j_list)):])
            / max(1, min(50, len(t_j_list)))
        )

        # Surface a single virtual device. The GUI's thermal pane
        # iterates ``ThermalResult.devices`` and plots one trace per
        # entry; a single "system" entry keeps the panel populated
        # and makes the limitation visible.
        device = ThermalDeviceResult(
            name="system",
            junction_temperature=t_j_list,
            peak_temperature=peak,
            steady_state_temperature=steady,
            foster_stages=list(default_stages),
        )

        # Loss breakdown: best-effort total — we know total power
        # but not the switching/conduction split. Attribute
        # everything to ``conduction`` so the loss-pie chart at
        # least sums correctly.
        try:
            total_loss_W = float(np.trapezoid(power_trace, times))
            total_loss_avg_W = total_loss_W / max(
                times[-1] - times[0], 1e-12
            )
        except Exception:
            total_loss_avg_W = 0.0
        device.losses.conduction = max(0.0, total_loss_avg_W)

        return ThermalResult(
            time=list(times),
            devices=[device],
            ambient_temperature=t_amb_celsius,
            is_synthetic=False,
            error_message="",
        )

    @staticmethod
    def _estimate_total_power(
        electrical_result: TransientResult,
        times: list[float],
    ) -> list[float]:
        """Best-effort total-system power trace.

        Walks ``electrical_result.signals`` for any channel whose
        name contains "power" or "p_" — the GUI's power-probe
        components emit one of those. Falls back to a zero trace
        when none are present (the resulting temperature stays at
        T_amb, signalling to the user that the circuit needs a
        power probe to drive the thermal panel).
        """
        signals = getattr(electrical_result, "signals", None) or {}
        n = len(times)
        accum = [0.0] * n
        any_found = False
        for name, series in signals.items():
            lname = str(name).lower()
            if not ("power" in lname or lname.startswith("p_") or lname.startswith("p(")):
                continue
            series_list = list(series)
            for i in range(min(n, len(series_list))):
                try:
                    accum[i] += float(series_list[i])
                except (TypeError, ValueError):
                    continue
            any_found = True
        if not any_found:
            return [0.0] * n
        return accum

    @staticmethod
    def _default_foster_stages() -> list[FosterStage]:
        """Sensible default Foster network when the user hasn't
        wired one through the GUI yet.

        Stage 1: die-to-case, ~0.5 K/W, τ ≈ 10 ms — captures the
        millisecond-scale junction transient.

        Stage 2: case-to-ambient via a typical bolted-on heatsink,
        ~10 K/W, τ ≈ 100 s — captures the slow soak.

        These are deliberately conservative (warmer than a real
        well-designed cooling path) so the panel doesn't lull the
        user into thinking thermal is fine when it isn't.
        """
        return [
            FosterStage(resistance=0.5,  capacitance=10e-3 / 0.5),   # τ = 10 ms
            FosterStage(resistance=10.0, capacitance=100.0 / 10.0),  # τ = 100 s
        ]

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

        # ``num_nodes`` / ``num_branches`` are methods on the legacy
        # v0 ``Circuit`` but properties on the v0-compat shim. Handle
        # both shapes so the path works regardless of which Circuit
        # implementation a host wires up.
        if hasattr(circuit, "num_nodes"):
            n_nodes = circuit.num_nodes
            opts.num_nodes = n_nodes() if callable(n_nodes) else int(n_nodes)
        if hasattr(circuit, "num_branches"):
            n_branches = circuit.num_branches
            opts.num_branches = (
                n_branches() if callable(n_branches) else int(n_branches)
            )

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
        # Pulsim 1.3+ ships ``compute_dc_op``; older v0/v1 builds shipped
        # ``dc_operating_point`` / ``solve_dc`` / ``run_dc``.
        if any(
            hasattr(module, name)
            for name in (
                "compute_dc_op",
                "dc_operating_point",
                "solve_dc",
                "run_dc",
                "run_dc_analysis",
            )
        ):
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
        # Pulsim 1.3+ exposes ``run_ac_sweep`` (impulse-response Bode) and
        # ``run_mna_sweep`` (frequency-domain MNA solve). The older v0/v1
        # surface used ``run_ac`` / ``run_ac_analysis`` / ``run_small_signal``
        # / ``ACAnalysis`` — kept here for backwards compatibility.
        if any(
            hasattr(module, name)
            for name in (
                "run_ac_sweep",
                "run_mna_sweep",
                "run_ac",
                "run_ac_analysis",
                "run_small_signal",
                "ACAnalysis",
            )
        ):
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
        # Pulsim 1.3+ ships thermal Foster networks (``FosterStage``,
        # ``add_foster_network``, ``make_thermal_observer``,
        # ``compute_temperature``, ``fit_foster_from_zth``). The older
        # v0/v1 surface used ``ThermalSimulator`` /
        # ``create_simple_thermal_model`` / ``run_thermal*``.
        if any(
            hasattr(module, name)
            for name in (
                "add_foster_network",
                "FosterStage",
                "make_thermal_observer",
                "compute_temperature",
                "fit_foster_from_zth",
                "run_thermal",
                "run_thermal_analysis",
            )
        ):
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
