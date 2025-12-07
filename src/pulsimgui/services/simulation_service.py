"""Simulation service for running Pulsim simulations."""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any
import time

from PySide6.QtCore import QObject, Signal, QThread, QMutex, QWaitCondition


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


class SimulationWorker(QThread):
    """Worker thread for running simulations."""

    progress = Signal(float, str)  # progress (0-100), message
    data_point = Signal(float, dict)  # time, signal_values
    finished_signal = Signal(SimulationResult)
    error = Signal(str)

    def __init__(self, circuit_data: dict, settings: SimulationSettings, parent=None):
        super().__init__(parent)
        self._circuit_data = circuit_data
        self._settings = settings
        self._cancelled = False
        self._paused = False
        self._mutex = QMutex()
        self._pause_condition = QWaitCondition()

    def run(self) -> None:
        """Run the simulation."""
        result = SimulationResult()

        try:
            self.progress.emit(0, "Initializing simulation...")

            # Convert GUI circuit to simulation format
            # In a real implementation, this would use Pulsim's Circuit class
            circuit = self._convert_circuit()

            if self._cancelled:
                return

            self.progress.emit(5, "Building circuit equations...")

            # Simulate - this is a placeholder implementation
            # In production, this would call Pulsim's solver
            t = self._settings.t_start
            dt = (self._settings.t_stop - self._settings.t_start) / self._settings.output_points
            total_steps = self._settings.output_points

            result.time = []
            result.signals = {}

            self.progress.emit(10, "Running transient simulation...")

            for i in range(total_steps + 1):
                # Check for cancellation
                if self._cancelled:
                    result.error_message = "Simulation cancelled"
                    self.finished_signal.emit(result)
                    return

                # Handle pause
                self._mutex.lock()
                while self._paused and not self._cancelled:
                    self._pause_condition.wait(self._mutex)
                self._mutex.unlock()

                t = self._settings.t_start + i * dt
                result.time.append(t)

                # Placeholder: Generate dummy waveforms
                # In real implementation, this would be actual simulation data
                signals = self._simulate_step(t, circuit)
                for name, value in signals.items():
                    if name not in result.signals:
                        result.signals[name] = []
                    result.signals[name].append(value)

                # Emit data point for real-time plotting
                if i % 100 == 0:
                    self.data_point.emit(t, signals)

                # Update progress
                progress = 10 + (i / total_steps) * 85
                if i % (total_steps // 20 + 1) == 0:
                    self.progress.emit(progress, f"Time: {t*1e6:.1f}µs")

            self.progress.emit(95, "Finalizing results...")

            # Calculate statistics
            result.statistics = {
                "simulation_time": self._settings.t_stop - self._settings.t_start,
                "time_steps": len(result.time),
                "signals_count": len(result.signals),
            }

            self.progress.emit(100, "Simulation complete")
            self.finished_signal.emit(result)

        except Exception as e:
            result.error_message = str(e)
            self.error.emit(str(e))
            self.finished_signal.emit(result)

    def _convert_circuit(self) -> dict:
        """Convert GUI circuit data to simulation format."""
        # Placeholder - in real implementation, this would create Pulsim Circuit
        return self._circuit_data

    def _simulate_step(self, t: float, circuit: dict) -> dict[str, float]:
        """Simulate one time step - placeholder implementation."""
        import math

        # Generate placeholder waveforms based on circuit components
        signals = {}

        # Example: Generate some dummy signals
        # In real implementation, this would be actual node voltages and currents
        signals["V(out)"] = 5.0 * (1 - math.exp(-t * 10000)) * math.sin(2 * math.pi * 1000 * t)
        signals["V(in)"] = 10.0 * math.sin(2 * math.pi * 1000 * t)
        signals["I(R1)"] = signals["V(out)"] / 1000 if "V(out)" in signals else 0

        return signals

    def cancel(self) -> None:
        """Cancel the simulation."""
        self._cancelled = True
        self._paused = False
        self._pause_condition.wakeAll()

    def pause(self) -> None:
        """Pause the simulation."""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()

    def resume(self) -> None:
        """Resume a paused simulation."""
        self._mutex.lock()
        self._paused = False
        self._mutex.unlock()
        self._pause_condition.wakeAll()

    @property
    def is_paused(self) -> bool:
        """Check if simulation is paused."""
        return self._paused


class SimulationService(QObject):
    """Service for managing simulations."""

    # Signals
    state_changed = Signal(SimulationState)
    progress = Signal(float, str)
    data_point = Signal(float, dict)
    simulation_finished = Signal(SimulationResult)
    dc_finished = Signal(DCResult)
    ac_finished = Signal(ACResult)
    error = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._state = SimulationState.IDLE
        self._worker: SimulationWorker | None = None
        self._settings = SimulationSettings()
        self._last_result: SimulationResult | None = None

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

    def run_transient(self, circuit_data: dict) -> None:
        """Run a transient simulation."""
        if self.is_running:
            self.error.emit("Simulation already running")
            return

        self._set_state(SimulationState.RUNNING)

        # Create and start worker thread
        self._worker = SimulationWorker(circuit_data, self._settings)
        self._worker.progress.connect(self._on_progress)
        self._worker.data_point.connect(self._on_data_point)
        self._worker.finished_signal.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def run_dc_operating_point(self, circuit_data: dict) -> None:
        """Run DC operating point analysis."""
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

    def stop(self) -> None:
        """Stop the current simulation."""
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(5000)  # Wait up to 5 seconds
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
        if result.error_message:
            self._set_state(SimulationState.ERROR)
        else:
            self._set_state(SimulationState.COMPLETED)
        self.simulation_finished.emit(result)

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
        }

        if project and project.current_schematic:
            circuit = project.current_schematic.circuit

            # Convert components
            for comp in circuit.components:
                comp_data = {
                    "id": str(comp.id),
                    "type": comp.type.name,
                    "name": comp.name,
                    "parameters": comp.parameters.copy(),
                    "pins": [(p.name, p.x, p.y) for p in comp.pins],
                }
                circuit_data["components"].append(comp_data)

            # Convert wires
            for wire in circuit.wires:
                wire_data = {
                    "id": str(wire.id),
                    "segments": [(s.x1, s.y1, s.x2, s.y2) for s in wire.segments],
                    "connections": wire.connections,
                }
                circuit_data["wires"].append(wire_data)

        return circuit_data
