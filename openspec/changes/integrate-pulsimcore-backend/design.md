# Design: PulsimCore Backend Integration

## Context

PulsimGui needs to integrate with PulsimCore (C++/Python simulation engine) while maintaining:
1. **Isolation**: GUI code should not directly depend on PulsimCore internals
2. **Flexibility**: Ability to swap backend versions or implementations
3. **Graceful Degradation**: GUI works with placeholder when backend unavailable
4. **Forward Compatibility**: Backend API changes don't break the GUI

### Stakeholders
- GUI developers: Need stable interface to backend
- Core developers: Need freedom to evolve C++/Python API
- Users: Need working simulations with clear error messages

### Constraints
- PulsimCore uses pybind11 bindings (C++ → Python)
- Backend may not be installed (demo mode required)
- Multiple backend versions may coexist
- GUI must remain responsive during long simulations

## Goals / Non-Goals

### Goals
1. Define stable `BackendCapabilities` protocol independent of PulsimCore internals
2. Support DC, AC, transient, and thermal simulations through unified interface
3. Enable backend version detection and compatibility checking
4. Provide clear diagnostics when simulations fail
5. Allow future backends (ngspice, Xyce) without GUI changes

### Non-Goals
- Implementing new simulation algorithms (that's PulsimCore's job)
- Supporting multiple simultaneous backends
- Hot-reloading backend during active simulation
- Remote backend execution (future work)

## Decisions

### Decision 1: Backend Capabilities Protocol

**What**: Define a Python Protocol (`BackendCapabilities`) that all backends must implement.

**Why**: Decouples GUI from specific backend implementation. New backends just implement the protocol.

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BackendCapabilities(Protocol):
    """Protocol defining the full backend interface."""

    @property
    def info(self) -> BackendInfo: ...

    @property
    def capabilities(self) -> set[str]: ...  # {"transient", "dc", "ac", "thermal"}

    def run_transient(
        self,
        circuit_data: dict,
        settings: TransientSettings,
        callbacks: BackendCallbacks,
    ) -> TransientResult: ...

    def run_dc(
        self,
        circuit_data: dict,
        settings: DCSettings,
    ) -> DCResult: ...

    def run_ac(
        self,
        circuit_data: dict,
        settings: ACSettings,
    ) -> ACResult: ...

    def run_thermal(
        self,
        circuit_data: dict,
        electrical_result: TransientResult,
        thermal_settings: ThermalSettings,
    ) -> ThermalResult: ...

    def has_capability(self, name: str) -> bool: ...
```

**Alternatives Considered**:
- Abstract base class: Rejected - too rigid, forces inheritance
- Duck typing only: Rejected - no static type checking
- Interface class: Python doesn't have true interfaces

### Decision 2: Semantic Versioning for Backend API

**What**: Use `BackendVersion` class with major.minor.patch and API version.

**Why**: Allows compatibility checks and graceful degradation.

```python
@dataclass
class BackendVersion:
    major: int
    minor: int
    patch: int
    api_version: int  # Incremented on breaking changes

    @classmethod
    def from_string(cls, version: str) -> "BackendVersion":
        # Parse "0.2.1" or "0.2.1+api3"
        ...

    def is_compatible_with(self, required: "BackendVersion") -> bool:
        """Check if this version satisfies required version."""
        return self.api_version >= required.api_version

# GUI defines minimum required API version
MIN_BACKEND_API = BackendVersion(0, 2, 0, api_version=2)
```

### Decision 3: Result Dataclasses (Backend-Agnostic)

**What**: Define result types in GUI that backends convert to.

**Why**: GUI doesn't depend on backend's internal types.

```python
@dataclass
class DCResult:
    """Backend-agnostic DC analysis result."""
    node_voltages: dict[str, float]
    branch_currents: dict[str, float]
    power_dissipation: dict[str, float]
    convergence_info: ConvergenceInfo
    error_message: str = ""

    @property
    def is_valid(self) -> bool:
        return not self.error_message

@dataclass
class ConvergenceInfo:
    """Convergence diagnostics from solver."""
    converged: bool
    iterations: int
    final_residual: float
    strategy_used: str  # "newton", "gmin_stepping", etc.
    history: list[IterationRecord] = field(default_factory=list)
    problematic_nodes: list[str] = field(default_factory=list)

@dataclass
class ACResult:
    """Backend-agnostic AC analysis result."""
    frequencies: list[float]
    magnitude: dict[str, list[float]]  # signal_name -> magnitude_dB
    phase: dict[str, list[float]]      # signal_name -> phase_degrees
    error_message: str = ""

@dataclass
class ThermalResult:
    """Backend-agnostic thermal analysis result."""
    time: list[float]
    devices: list[ThermalDeviceResult]
    ambient_temperature: float
    is_synthetic: bool = False  # True if using placeholder data
```

### Decision 4: Feature Detection Pattern

**What**: Backends report their capabilities; GUI adapts accordingly.

**Why**: Not all backends support all features. GUI should degrade gracefully.

```python
class PulsimBackend:
    @property
    def capabilities(self) -> set[str]:
        caps = {"transient"}

        if hasattr(self._module, "v2") and hasattr(self._module.v2, "solve_dc"):
            caps.add("dc")

        if hasattr(self._module, "run_ac"):
            caps.add("ac")

        if hasattr(self._module, "ThermalSimulator"):
            caps.add("thermal")

        return caps

    def has_capability(self, name: str) -> bool:
        return name in self.capabilities

# GUI usage
if backend.has_capability("dc"):
    result = backend.run_dc(circuit, settings)
else:
    self.error.emit("DC analysis not available with current backend")
```

### Decision 5: Settings Dataclasses for Each Analysis Type

**What**: Separate settings classes for each simulation type.

**Why**: Clear API, type safety, easy serialization.

```python
@dataclass
class TransientSettings:
    t_start: float = 0.0
    t_stop: float = 1e-3
    t_step: float = 1e-6
    max_step: float = 1e-6
    integration_method: str = "bdf2"  # "euler", "trapezoidal", "bdf2"
    rel_tol: float = 1e-4
    abs_tol: float = 1e-6
    output_points: int = 10000

@dataclass
class DCSettings:
    strategy: str = "auto"  # "direct", "gmin", "source", "pseudo", "auto"
    max_iterations: int = 100
    tolerance: float = 1e-9
    enable_limiting: bool = True
    max_voltage_step: float = 5.0
    gmin_initial: float = 1e-3
    gmin_final: float = 1e-12

@dataclass
class ACSettings:
    f_start: float = 1.0
    f_stop: float = 1e6
    points_per_decade: int = 10
    input_source: str = ""
    output_nodes: list[str] = field(default_factory=list)

@dataclass
class ThermalSettings:
    ambient_temperature: float = 25.0
    include_switching_losses: bool = True
    include_conduction_losses: bool = True
    thermal_network: str = "foster"  # "foster", "cauer"
```

### Decision 6: Adapter Pattern for PulsimCore

**What**: `PulsimBackend` adapts PulsimCore's native types to GUI types.

**Why**: Isolates GUI from pybind11 binding details.

```python
class PulsimBackend(BackendCapabilities):
    """Adapter from PulsimCore native API to GUI protocol."""

    def __init__(self, module: Any, info: BackendInfo):
        self._module = module
        self.info = info
        self._converter = CircuitConverter(module)

    def run_dc(
        self,
        circuit_data: dict,
        settings: DCSettings,
    ) -> DCResult:
        # 1. Convert GUI circuit to PulsimCore Circuit
        circuit = self._converter.build(circuit_data)

        # 2. Build PulsimCore options from GUI settings
        opts = self._build_dc_options(settings)

        # 3. Call PulsimCore API
        try:
            native_result = self._module.v2.solve_dc(circuit, opts)
        except Exception as e:
            return DCResult(error_message=str(e), ...)

        # 4. Convert PulsimCore result to GUI DCResult
        return self._convert_dc_result(native_result, circuit)

    def _build_dc_options(self, settings: DCSettings) -> Any:
        """Convert GUI DCSettings to pulsim.v2.NewtonOptions."""
        opts = self._module.v2.NewtonOptions()
        opts.max_iterations = settings.max_iterations
        opts.enable_limiting = settings.enable_limiting
        opts.max_voltage_step = settings.max_voltage_step
        # ... map other fields
        return opts

    def _convert_dc_result(self, native: Any, circuit: Any) -> DCResult:
        """Convert pulsim.v2.NewtonResult to GUI DCResult."""
        node_voltages = {}
        for i, name in enumerate(circuit.node_names()):
            node_voltages[f"V({name})"] = float(native.solution[i])

        # Extract branch currents from solution vector
        branch_currents = self._extract_branch_currents(native, circuit)

        return DCResult(
            node_voltages=node_voltages,
            branch_currents=branch_currents,
            convergence_info=self._build_convergence_info(native),
            error_message="" if native.success() else native.error_message,
        )
```

### Decision 7: Backend Registry for Discovery

**What**: Centralized registry that discovers and manages backends.

**Why**: Supports multiple backend sources (installed packages, entry points, local).

```python
class BackendRegistry:
    """Discovers and manages available backends."""

    def __init__(self):
        self._backends: dict[str, BackendFactory] = {}
        self._active: BackendCapabilities | None = None
        self._discover_backends()

    def _discover_backends(self) -> None:
        # 1. Try pulsim package
        pulsim_backend = self._try_load_pulsim()
        if pulsim_backend:
            self._backends["pulsim"] = pulsim_backend

        # 2. Try entry points (future backends)
        for ep in self._load_entry_points():
            self._backends[ep.name] = ep.factory

        # 3. Always have placeholder fallback
        self._backends["placeholder"] = PlaceholderBackend

    def available_backends(self) -> list[BackendInfo]:
        """List all discovered backends."""
        return [factory().info for factory in self._backends.values()]

    def activate(self, identifier: str) -> BackendCapabilities:
        """Activate a specific backend."""
        if identifier not in self._backends:
            raise ValueError(f"Unknown backend: {identifier}")
        self._active = self._backends[identifier]()
        return self._active

    @property
    def active(self) -> BackendCapabilities:
        """Get currently active backend."""
        if self._active is None:
            self._active = self._select_best_backend()
        return self._active
```

### Decision 8: Convergence Diagnostics UI

**What**: New dialog showing detailed convergence information.

**Why**: Users need to understand why simulations fail and how to fix them.

```python
class ConvergenceDiagnosticsDialog(QDialog):
    """Display detailed convergence diagnostics."""

    def __init__(self, convergence_info: ConvergenceInfo, parent=None):
        super().__init__(parent)
        self._info = convergence_info
        self._setup_ui()

    def _setup_ui(self):
        # Tab 1: Summary
        # - Converged: Yes/No
        # - Iterations: N
        # - Strategy used: GMIN stepping
        # - Final residual: 1.2e-8

        # Tab 2: Iteration History
        # - Plot of residual vs iteration
        # - Table of iteration records

        # Tab 3: Problematic Variables
        # - List of nodes that didn't converge
        # - Their current values and tolerances

        # Tab 4: Suggestions
        # - "Try increasing max_iterations"
        # - "Enable voltage limiting"
        # - "Check for floating nodes"
```

## Risks / Trade-offs

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PulsimCore API changes break adapter | Medium | High | Version check, graceful degradation |
| Performance overhead from conversion | Low | Medium | Profile hot paths, optimize if needed |
| Memory usage from result copies | Low | Low | Use views where possible |
| User confusion with backend options | Medium | Low | Sensible defaults, help text |

### Trade-offs

1. **Abstraction vs Performance**: Adding adapter layer adds overhead, but isolation benefits outweigh small performance cost.

2. **Feature Detection vs Static Config**: Runtime detection is more flexible but slightly slower than compile-time config.

3. **Separate Settings Classes vs Single Config**: More classes but cleaner API and better type safety.

## Migration Plan

### Phase 1: Backend Abstraction
1. Create `BackendCapabilities` protocol
2. Create result dataclasses (`DCResult`, `ACResult`, etc.)
3. Create settings dataclasses
4. Refactor `PulsimBackend` to implement protocol

### Phase 2: DC Integration
1. Add `run_dc()` to `PulsimBackend`
2. Modify `SimulationService.run_dc_operating_point()`
3. Add DC settings to `SimulationSettingsDialog`
4. Create `DCResultsDialog` with real data

### Phase 3: AC Integration
1. Add `run_ac()` to `PulsimBackend`
2. Modify `SimulationService.run_ac_analysis()`
3. Update Bode plot dialog with real data

### Phase 4: Thermal Integration
1. Add `run_thermal()` to `PulsimBackend`
2. Modify `ThermalAnalysisService`
3. Add synthetic fallback flag

### Phase 5: Solver Options UI
1. Extend `SimulationSettingsDialog` with Solver tab
2. Extend `SimulationSettings` dataclass
3. Wire settings to backend

### Phase 6: Convergence Diagnostics
1. Create `ConvergenceDiagnosticsDialog`
2. Add "Show Diagnostics" button to error dialogs
3. Integrate with DC and transient failure paths

### Rollback Strategy
- Each phase is independently deployable
- Placeholder fallback always available
- Feature flags can disable new functionality

## Open Questions

1. **Remote Backend**: Should we support running simulations on a remote server? (Deferred)

2. **Backend Plugins**: Should third-party backends be installable? (Entry points ready, not priority)

3. **Result Caching**: Should we cache simulation results to avoid re-running? (Future enhancement)

4. **Parallel Backends**: Could we run multiple backends simultaneously for comparison? (Not priority)
