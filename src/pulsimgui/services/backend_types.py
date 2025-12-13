"""Backend-agnostic types for simulation results and settings.

These types decouple the GUI from backend-specific implementations,
allowing different backends to be used interchangeably.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
# Version Management
# =============================================================================


@dataclass
class BackendVersion:
    """Semantic version with API version tracking for compatibility checks.

    Attributes:
        major: Major version number (breaking changes).
        minor: Minor version number (new features, backwards compatible).
        patch: Patch version number (bug fixes).
        api_version: API version for compatibility checking. Incremented on breaking API changes.
    """

    major: int
    minor: int
    patch: int
    api_version: int = 1

    @classmethod
    def from_string(cls, version: str) -> "BackendVersion":
        """Parse a version string into a BackendVersion.

        Supports formats:
            - "0.2.1" -> (0, 2, 1, api=1)
            - "0.2.1+api3" -> (0, 2, 1, api=3)
            - "1.0.0-beta" -> (1, 0, 0, api=1)

        Args:
            version: Version string to parse.

        Returns:
            BackendVersion instance.

        Raises:
            ValueError: If the version string cannot be parsed.
        """
        # Extract API version if present
        api_version = 1
        api_match = re.search(r"\+api(\d+)", version)
        if api_match:
            api_version = int(api_match.group(1))
            version = version[: api_match.start()]

        # Remove pre-release suffix (e.g., -beta, -rc1)
        version = re.sub(r"-.*$", "", version)

        # Parse major.minor.patch
        parts = version.split(".")
        if len(parts) < 2:
            raise ValueError(f"Invalid version string: {version}")

        try:
            major = int(parts[0])
            minor = int(parts[1])
            patch = int(parts[2]) if len(parts) > 2 else 0
        except ValueError as e:
            raise ValueError(f"Invalid version string: {version}") from e

        return cls(major=major, minor=minor, patch=patch, api_version=api_version)

    def is_compatible_with(self, required: "BackendVersion") -> bool:
        """Check if this version satisfies the required version.

        Compatibility is determined by:
        1. API version must be >= required API version
        2. If API versions match, semantic version comparison applies

        Args:
            required: The minimum required version.

        Returns:
            True if this version is compatible with required version.
        """
        if self.api_version != required.api_version:
            return self.api_version >= required.api_version

        # Same API version: compare semantic version
        return (self.major, self.minor, self.patch) >= (
            required.major,
            required.minor,
            required.patch,
        )

    def __str__(self) -> str:
        """Return string representation of version."""
        base = f"{self.major}.{self.minor}.{self.patch}"
        if self.api_version > 1:
            return f"{base}+api{self.api_version}"
        return base


# Minimum required backend API version for full functionality
MIN_BACKEND_API = BackendVersion(0, 2, 0, api_version=1)


# =============================================================================
# Convergence Information
# =============================================================================


@dataclass
class IterationRecord:
    """Record of a single Newton iteration.

    Attributes:
        iteration: Iteration number (0-based).
        residual_norm: Norm of the residual vector.
        voltage_error: Maximum voltage error (for convergence check).
        current_error: Maximum current error (for convergence check).
        damping_factor: Damping factor applied to Newton step.
        step_norm: Norm of the Newton step vector.
    """

    iteration: int
    residual_norm: float
    voltage_error: float = 0.0
    current_error: float = 0.0
    damping_factor: float = 1.0
    step_norm: float = 0.0


@dataclass
class ProblematicVariable:
    """Information about a variable that didn't converge.

    Attributes:
        index: Variable index in solution vector.
        name: Human-readable name (e.g., "V(out)" or "I(M1)").
        value: Current value of the variable.
        change: Change in last iteration.
        tolerance: Convergence tolerance.
        normalized_error: Error normalized by tolerance.
        is_voltage: True if this is a voltage variable.
    """

    index: int
    name: str
    value: float
    change: float
    tolerance: float
    normalized_error: float
    is_voltage: bool = True


@dataclass
class ConvergenceInfo:
    """Detailed convergence diagnostics from solver.

    Attributes:
        converged: Whether the solver converged successfully.
        iterations: Total number of iterations performed.
        final_residual: Final residual norm.
        strategy_used: Strategy name (e.g., "newton", "gmin_stepping").
        time_of_failure: Simulation time at failure (for transient).
        history: List of iteration records for plotting.
        problematic_variables: Variables that didn't converge.
        failure_reason: Human-readable failure description.
    """

    converged: bool
    iterations: int = 0
    final_residual: float = 0.0
    strategy_used: str = "newton"
    time_of_failure: float | None = None
    history: list[IterationRecord] = field(default_factory=list)
    problematic_variables: list[ProblematicVariable] = field(default_factory=list)
    failure_reason: str = ""

    @property
    def trend(self) -> str:
        """Analyze convergence trend from history.

        Returns:
            One of: "converging", "stalling", "diverging", "unknown"
        """
        if len(self.history) < 3:
            return "unknown"

        recent = self.history[-3:]
        residuals = [r.residual_norm for r in recent]

        if residuals[-1] > residuals[0] * 1.1:
            return "diverging"
        if abs(residuals[-1] - residuals[0]) < residuals[0] * 0.01:
            return "stalling"
        return "converging"


# =============================================================================
# Result Types
# =============================================================================


@dataclass
class TransientResult:
    """Backend-agnostic transient simulation result.

    Attributes:
        time: List of time points.
        signals: Dictionary mapping signal names to value lists.
        statistics: Simulation statistics (steps, elapsed time, etc.).
        convergence_info: Convergence diagnostics (if available).
        error_message: Error message if simulation failed.
    """

    time: list[float] = field(default_factory=list)
    signals: dict[str, list[float]] = field(default_factory=dict)
    statistics: dict[str, Any] = field(default_factory=dict)
    convergence_info: ConvergenceInfo | None = None
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if result contains valid data."""
        return not self.error_message and len(self.time) > 0


@dataclass
class DCResult:
    """Backend-agnostic DC operating point result.

    Attributes:
        node_voltages: Dictionary mapping node names to voltages.
        branch_currents: Dictionary mapping device names to currents.
        power_dissipation: Dictionary mapping device names to power (W).
        convergence_info: Convergence diagnostics.
        error_message: Error message if analysis failed.
    """

    node_voltages: dict[str, float] = field(default_factory=dict)
    branch_currents: dict[str, float] = field(default_factory=dict)
    power_dissipation: dict[str, float] = field(default_factory=dict)
    convergence_info: ConvergenceInfo = field(
        default_factory=lambda: ConvergenceInfo(converged=False)
    )
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if result contains valid data."""
        return not self.error_message and self.convergence_info.converged


@dataclass
class ACResult:
    """Backend-agnostic AC analysis result.

    Attributes:
        frequencies: List of frequency points (Hz).
        magnitude: Dictionary mapping signal names to magnitude (dB).
        phase: Dictionary mapping signal names to phase (degrees).
        error_message: Error message if analysis failed.
    """

    frequencies: list[float] = field(default_factory=list)
    magnitude: dict[str, list[float]] = field(default_factory=dict)
    phase: dict[str, list[float]] = field(default_factory=dict)
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if result contains valid data."""
        return not self.error_message and len(self.frequencies) > 0


@dataclass
class FosterStage:
    """Single stage of a Foster thermal network.

    Attributes:
        resistance: Thermal resistance (K/W).
        capacitance: Thermal capacitance (J/K).
    """

    resistance: float
    capacitance: float

    @property
    def time_constant(self) -> float:
        """Return thermal time constant (tau = R * C)."""
        return self.resistance * self.capacitance


@dataclass
class LossBreakdown:
    """Power loss breakdown for a semiconductor device.

    Attributes:
        conduction: Conduction losses (W).
        switching_on: Turn-on switching losses (W).
        switching_off: Turn-off switching losses (W).
        reverse_recovery: Reverse recovery losses (W).
    """

    conduction: float = 0.0
    switching_on: float = 0.0
    switching_off: float = 0.0
    reverse_recovery: float = 0.0

    @property
    def total(self) -> float:
        """Return total losses."""
        return self.conduction + self.switching_on + self.switching_off + self.reverse_recovery

    @property
    def switching_total(self) -> float:
        """Return total switching losses."""
        return self.switching_on + self.switching_off + self.reverse_recovery


@dataclass
class ThermalDeviceResult:
    """Thermal result for a single device.

    Attributes:
        name: Device name (e.g., "M1", "D1").
        junction_temperature: Time series of junction temperature (°C).
        peak_temperature: Maximum junction temperature (°C).
        steady_state_temperature: Steady-state junction temperature (°C).
        losses: Power loss breakdown.
        foster_stages: Foster network parameters.
        thermal_limit: Maximum rated temperature (°C), if known.
    """

    name: str
    junction_temperature: list[float] = field(default_factory=list)
    peak_temperature: float = 0.0
    steady_state_temperature: float = 0.0
    losses: LossBreakdown = field(default_factory=LossBreakdown)
    foster_stages: list[FosterStage] = field(default_factory=list)
    thermal_limit: float | None = None

    @property
    def exceeds_limit(self) -> bool:
        """Check if peak temperature exceeds thermal limit."""
        if self.thermal_limit is None:
            return False
        return self.peak_temperature > self.thermal_limit

    @property
    def total_thermal_resistance(self) -> float:
        """Return total thermal resistance from Foster network."""
        return sum(stage.resistance for stage in self.foster_stages)


@dataclass
class ThermalResult:
    """Backend-agnostic thermal simulation result.

    Attributes:
        time: Time points for temperature traces.
        devices: Per-device thermal results.
        ambient_temperature: Ambient temperature (°C).
        is_synthetic: True if using placeholder/synthetic data.
        error_message: Error message if analysis failed.
    """

    time: list[float] = field(default_factory=list)
    devices: list[ThermalDeviceResult] = field(default_factory=list)
    ambient_temperature: float = 25.0
    is_synthetic: bool = False
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        """Check if result contains valid data."""
        return not self.error_message and len(self.devices) > 0

    @property
    def total_losses(self) -> float:
        """Return sum of all device losses."""
        return sum(dev.losses.total for dev in self.devices)

    def device_by_name(self, name: str) -> ThermalDeviceResult | None:
        """Find device result by name."""
        for dev in self.devices:
            if dev.name == name:
                return dev
        return None


# =============================================================================
# Settings Types
# =============================================================================


@dataclass
class TransientSettings:
    """Settings for transient simulation.

    Attributes:
        t_start: Start time (s).
        t_stop: Stop time (s).
        t_step: Initial time step (s).
        max_step: Maximum time step (s).
        integration_method: Integration method ("euler", "trapezoidal", "bdf2").
        rel_tol: Relative tolerance.
        abs_tol: Absolute tolerance.
        output_points: Number of output points.
        max_iterations: Maximum Newton iterations per time step.
        enable_limiting: Enable voltage limiting.
        max_voltage_step: Maximum voltage change per iteration (V).
    """

    t_start: float = 0.0
    t_stop: float = 1e-3
    t_step: float = 1e-6
    max_step: float = 1e-6
    integration_method: str = "bdf2"
    rel_tol: float = 1e-4
    abs_tol: float = 1e-6
    output_points: int = 10000
    max_iterations: int = 50
    enable_limiting: bool = True
    max_voltage_step: float = 5.0


@dataclass
class DCSettings:
    """Settings for DC operating point analysis.

    Attributes:
        strategy: DC solving strategy.
            - "auto": Automatically select best strategy.
            - "direct": Direct Newton-Raphson.
            - "gmin": GMIN stepping for difficult circuits.
            - "source": Source stepping.
            - "pseudo": Pseudo-transient analysis.
        max_iterations: Maximum Newton iterations.
        tolerance: Convergence tolerance.
        enable_limiting: Enable voltage limiting to prevent divergence.
        max_voltage_step: Maximum voltage change per iteration (V).
        gmin_initial: Initial GMIN value (for gmin strategy).
        gmin_final: Final GMIN value (for gmin strategy).
        source_steps: Number of source stepping steps (for source strategy).
    """

    strategy: str = "auto"
    max_iterations: int = 100
    tolerance: float = 1e-9
    enable_limiting: bool = True
    max_voltage_step: float = 5.0
    gmin_initial: float = 1e-3
    gmin_final: float = 1e-12
    source_steps: int = 10


@dataclass
class ACSettings:
    """Settings for AC frequency-domain analysis.

    Attributes:
        f_start: Start frequency (Hz).
        f_stop: Stop frequency (Hz).
        points_per_decade: Number of frequency points per decade.
        input_source: Name of AC input source.
        output_nodes: List of output node names to analyze.
    """

    f_start: float = 1.0
    f_stop: float = 1e6
    points_per_decade: int = 10
    input_source: str = ""
    output_nodes: list[str] = field(default_factory=list)


@dataclass
class ThermalSettings:
    """Settings for thermal simulation.

    Attributes:
        ambient_temperature: Ambient temperature (°C).
        include_switching_losses: Include switching losses in calculation.
        include_conduction_losses: Include conduction losses in calculation.
        thermal_network: Thermal network type ("foster" or "cauer").
    """

    ambient_temperature: float = 25.0
    include_switching_losses: bool = True
    include_conduction_losses: bool = True
    thermal_network: str = "foster"


__all__ = [
    # Version
    "BackendVersion",
    "MIN_BACKEND_API",
    # Convergence
    "IterationRecord",
    "ProblematicVariable",
    "ConvergenceInfo",
    # Results
    "TransientResult",
    "DCResult",
    "ACResult",
    "ThermalResult",
    "ThermalDeviceResult",
    "FosterStage",
    "LossBreakdown",
    # Settings
    "TransientSettings",
    "DCSettings",
    "ACSettings",
    "ThermalSettings",
]
