## Context
PulsimGUI currently runs entirely on placeholder simulation code located in `pulsimgui/services/simulation_service.py`. The real solver lives in the sibling `PulsimCore` project and ships as the `pulsim` Python package (native extension). The backend exposes the following GUI-facing APIs:

- `pulsim.Circuit`, `pulsim.Simulator`, `pulsim.SimulationOptions`
- `pulsim.SimulationController` for pause/resume/stop
- `pulsim.SimulationProgress`, `ProgressCallbackConfig`, `StreamingConfig`
- Validation helpers (`validate_circuit`, `Diagnostic`, `ValidationResult`)
- Component metadata registry for palette/property editors

To keep the GUI decoupled from the specific backend build (stable/nightly, local dev, remote gRPC), we introduce a thin adapter interface that hides discovery, versioning, and object conversion.

## Adapter Interface
`pulsimgui.services.backend_adapter` provides the data contracts consumed by the GUI:

```python
@dataclass
class BackendInfo:
    identifier: str          # Stable key persisted in settings
    name: str                # Human readable source ("pulsim", "demo")
    version: str             # Distribution version string
    status: str              # available | detected | missing | placeholder
    location: str | None
    capabilities: set[str]
    message: str             # Surface status/details in UI

@dataclass
class BackendCallbacks:
    progress: Callable[[float, str], None]
    data_point: Callable[[float, dict[str, float]], None]
    check_cancelled: Callable[[], bool]
    wait_if_paused: Callable[[], None]

class SimulationBackend(Protocol):
    info: BackendInfo

    def run_transient(
        self,
        circuit_data: dict,
        settings: SimulationSettings,
        callbacks: BackendCallbacks,
    ) -> BackendRunResult: ...

    def request_pause(self, run_id: int | None = None) -> None: ...
    def request_resume(self, run_id: int | None = None) -> None: ...
    def request_stop(self, run_id: int | None = None) -> None: ...
```

`BackendRunResult` mirrors the waveform payload currently emitted by `SimulationService` and keeps the GUI decoupled from solver-specific result objects.

### Progress / Control
- Control requests are funneled through `SimulationBackend.request_*` so implementations can drive `pulsim.SimulationController` instances on their own threads.
- `BackendCallbacks` provides throttled hooks for progress and streaming datapoints; backends must honor `check_cancelled` and `wait_if_paused` to keep the GUI responsive.
    ) -> ParameterSweepResult: ...
```

- Extend existing `SimulationService.convert_gui_circuit` to emit a backend-friendly dictionary that includes component parameters, resolved node identifiers per pin, node aliases, and raw wire geometry. `CircuitConverter` consumes this data to construct `pulsim.Circuit` objects with schematic positions.
- Support metadata lookups from `pulsim.ComponentRegistry` to translate GUI component IDs into backend enums (e.g., `pulsim.ComponentType.Resistor`).
- Provide fallback JSON export to debug mismatches (via `pulsim.circuit_to_json`).
- Adapter responsible for throttling via `pulsim.ProgressCallbackConfig` using GUI preferences (min interval, min steps).

### Circuit Conversion
- Extend existing `SimulationService.convert_gui_circuit` to build real `pulsim.Circuit` primitives (components, nodes, waveforms) and set schematic positions via `pulsim.SchematicPosition`.
- Support metadata lookups from `pulsim.ComponentRegistry` to translate GUI component IDs into backend enums (e.g., `pulsim.ComponentType.Resistor`).
- Provide fallback JSON export to debug mismatches (via `pulsim.circuit_to_json`).

## Discovery Flow
1. At application startup, initialize `BackendLoader(preferred_id=SettingsService.backend_preference)`:
    - Enumerate installed distributions (`pulsim`, `pulsim-nightly`, entry points under `pulsimgui.backends`).
    - Always register the placeholder backend so the GUI can stay in demo mode.
    - Honor persisted preference when present; otherwise default to the newest compatible native backend.
2. Attempt to `import pulsim`. On ImportError, record failure + hint command (`pip install pulsim`).
3. Build `BackendInfo` with runtime capability checks:
   - `hasattr(pulsim.Simulator, "run_ac")`
   - `hasattr(pulsim, "ThermalSimulator")`, etc.
4. Expose info through `SimulationService.backend_info` and Simulation Settings UI.

## SimulationService Refactor
- Inject `SimulationBackend` into `SimulationService` (default = adapter instance; fallback = NullBackend for demo mode).
- Replace `SimulationWorker` placeholder loop with adapter-driven execution:
  - Worker thread calls `backend.run_transient(...)` and emits progress via Qt signals.
  - Use `pulsim.SimulationController` inside worker to support pause/resume/stop.
- Parameter sweep manager reuses backend `.run_transient` per sweep point while respecting cancellation.
- DC/AC actions call `backend.run_dc / run_ac`; disable menu items if capability missing.

## Settings & UI
- Extend Simulation Settings dialog to show backend badge: `Backend: pulsim 0.1.0 (local)`.
- Provide drop-down when multiple versions detected (persist selection via `SettingsService`).
- When no backend is available, disable Run/DC/AC controls and show tooltip/button linking to installation instructions.
- Surface backend errors (ImportError, incompatible ABI) through status bar + dialog.

## Risks / Mitigations
- **Missing backend**: Provide NullBackend that raises actionable errors and leaves GUI functional.
- **Compatibility drift**: Gate features by capability checks; add telemetry/logging to detect API mismatches.
- **Thread safety**: All adapter calls occur in worker threads; only Qt signals cross into GUI thread. The controller object handles pause/resume without blocking UI.
- **Packaging**: Document dependency (`pip install pulsim`) in README and packaging scripts; consider bundling minimal backend build for demo.

## Open Questions
1. Do we need remote (gRPC) backend support in v1? If yes, adapter should abstract transport (local native vs remote server).
2. How should we handle backend updates at runtime? (Prompt restart vs hot reload.)
3. Should NullBackend keep placeholder simulations for demos, or block entirely? (Current plan: block with messaging.)

## Next Steps
- Validate change with `openspec validate add-backend-adapter --strict` once the spec/todo set is complete.
- Prototype adapter that imports pulsim from sibling checkout to prove conversion path before shipping.
- Add service tests that mock adapter to avoid hard dependency during CI.
