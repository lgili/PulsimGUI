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

        # Check for DC analysis (v2 solver)
        if hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
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
            # Build Newton options from DCSettings
            newton_opts = self._build_dc_options(settings)

            # Try v1 namespace first (DCConvergenceSolver)
            if hasattr(self._module, "v1") and hasattr(self._module.v1, "DCConvergenceSolver"):
                return self._run_dc_v1(circuit, settings, newton_opts)

            # Try v2 namespace
            if hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
                native_result = self._module.v2.solve_dc(circuit, newton_opts)
                return self._convert_dc_result(native_result, circuit)

            return DCResult(
                error_message="No DC solver available in backend",
                convergence_info=ConvergenceInfo(converged=False, failure_reason="No solver"),
            )

        except Exception as exc:
            return DCResult(
                error_message=str(exc),
                convergence_info=ConvergenceInfo(converged=False, failure_reason=str(exc)),
            )

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
        # Try v1 NewtonOptions first
        if hasattr(self._module, "v1") and hasattr(self._module.v1, "NewtonOptions"):
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

        # Build convergence info
        convergence_info = self._build_convergence_info(native_result)

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

    def _build_convergence_info(self, native_result: Any) -> ConvergenceInfo:
        """Build ConvergenceInfo from native result."""
        converged = getattr(native_result, "converged", False)
        if not converged and hasattr(native_result, "success"):
            converged = native_result.success()

        iterations = getattr(native_result, "iterations", 0)
        final_residual = getattr(native_result, "final_residual", 0.0)
        strategy_used = getattr(native_result, "strategy_used", "newton")

        # Extract iteration history if available
        history: list[IterationRecord] = []
        if hasattr(native_result, "history"):
            for i, record in enumerate(native_result.history):
                history.append(IterationRecord(
                    iteration=i,
                    residual_norm=getattr(record, "residual_norm", 0.0),
                    voltage_error=getattr(record, "voltage_error", 0.0),
                    current_error=getattr(record, "current_error", 0.0),
                    damping_factor=getattr(record, "damping_factor", 1.0),
                    step_norm=getattr(record, "step_norm", 0.0),
                ))

        # Extract problematic variables if available
        problematic_variables: list[ProblematicVariable] = []
        if hasattr(native_result, "problematic_nodes"):
            for node in native_result.problematic_nodes:
                problematic_variables.append(ProblematicVariable(
                    index=getattr(node, "index", 0),
                    name=getattr(node, "name", "unknown"),
                    value=getattr(node, "value", 0.0),
                    change=getattr(node, "change", 0.0),
                    tolerance=getattr(node, "tolerance", 1e-9),
                    normalized_error=getattr(node, "normalized_error", 0.0),
                    is_voltage=getattr(node, "is_voltage", True),
                ))

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

        if hasattr(opts, "f_start"):
            opts.f_start = settings.f_start
        if hasattr(opts, "f_stop"):
            opts.f_stop = settings.f_stop
        if hasattr(opts, "points_per_decade"):
            opts.points_per_decade = settings.points_per_decade
        if hasattr(opts, "input_source"):
            opts.input_source = settings.input_source

        return opts

    def _convert_ac_result(self, native_result: Any, settings: ACSettings) -> ACResult:
        """Convert PulsimCore AC result to GUI ACResult."""
        frequencies = list(getattr(native_result, "frequencies", []))
        magnitude: dict[str, list[float]] = {}
        phase: dict[str, list[float]] = {}

        # Extract magnitude and phase data
        if hasattr(native_result, "magnitude"):
            for name, values in native_result.magnitude.items():
                magnitude[name] = list(values)
        if hasattr(native_result, "phase"):
            for name, values in native_result.phase.items():
                phase[name] = list(values)

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

        # Check for DC analysis capability
        if hasattr(module, "v2") and hasattr(module.v2, "solve_dc"):
            capabilities.add("dc")
        elif hasattr(module, "v1") and hasattr(module.v1, "DCConvergenceSolver"):
            capabilities.add("dc")

        # Check for AC analysis capability
        if hasattr(module, "run_ac") or hasattr(module, "ACAnalysis"):
            capabilities.add("ac")

        # Check for thermal simulation capability
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
