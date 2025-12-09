# Backend Adapter Overview

This document describes how PulsimGUI discovers simulation backends, how the adapter interface is structured, and what data flows between the GUI and Pulsim Core.

## Architecture Summary

```
GUI (Qt) ──┐
           │  SimulationService
Project ───┼────────────┐
           │            │
           │   BackendLoader  ──▶  SimulationBackend (pulsim, placeholder, ...)
           │            │
CircuitConverter ◀──────┘
```

1. `SimulationService` serializes the active schematic via `convert_gui_circuit()`.
2. `CircuitConverter` turns that dictionary into a `pulsim.Circuit` ready for analysis.
3. `BackendLoader` chooses an adapter implementation (`PulsimBackend`, `PlaceholderBackend`, or any registered entry point) and exposes metadata through `BackendInfo`.
4. Workers call `SimulationBackend.run_transient()` while streaming progress/data via `BackendCallbacks`.
5. Pause/resume/stop requests propagate to the backend through explicit hook methods so long simulations stay responsive.

## Data Contracts

### `BackendInfo`

```python
@dataclass
class BackendInfo:
    identifier: str          # persisted key (e.g. "pulsim", "placeholder")
    name: str                # human label for menus
    version: str             # distribution semantic version
    status: str              # available | detected | missing | placeholder
    location: str | None     # resolved filesystem path when known
    capabilities: set[str]   # {"transient", "thermal", ...}
    message: str             # tooltip/status text shown in UI
```

Instances appear in drop-downs (Preferences, Simulation Settings) and drive capability gating.

### `BackendRunResult`

```python
@dataclass
class BackendRunResult:
    time: list[float]
    signals: dict[str, list[float]]
    statistics: dict[str, Any]
    error_message: str
```

The adapter normalizes solver output into primitive Python containers so Qt signals can shuttle the data without native bindings.

### `BackendCallbacks`

```python
@dataclass
class BackendCallbacks:
    progress: Callable[[float, str], None]
    data_point: Callable[[float, dict[str, float]], None]
    check_cancelled: Callable[[], bool]
    wait_if_paused: Callable[[], None]
```

Backends invoke these hooks to update the GUI and respond to pause/cancel requests. The `wait_if_paused` callable blocks until `SimulationWorker` resumes.

### `SimulationBackend` protocol

```python
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

`run_id` is the Python thread identifier recorded by `SimulationWorker`. A backend can ignore it if it maintains a single controller.

### `SimulationSettings` → Pulsim mapping

`SimulationService` owns a `SimulationSettings` dataclass whose fields mirror the knobs exposed by `pulsim.SimulationOptions`:

| Field | Meaning | Pulsim option |
| --- | --- | --- |
| `t_start` | Absolute start time (seconds) | `SimulationOptions.tstart` |
| `t_stop` | Absolute stop time (seconds) | `SimulationOptions.tstop` |
| `t_step` | Requested fixed time step; set to `0` to enable automatic spacing | `SimulationOptions.dt` |
| `max_step` | Upper bound on adaptive steps | `SimulationOptions.dtmax` / `max_step` |
| `rel_tol` | Relative tolerance | `SimulationOptions.reltol` |
| `abs_tol` | Absolute tolerance | `SimulationOptions.abstol` |
| `output_points` | GUI streaming cadence; also used to derive fallback `dt` | Derived if `t_step == 0` |

Adapters should copy these fields straight into the Pulsim API, falling back to solver defaults only when the GUI leaves a parameter unset.

### Adapter lifecycle responsibilities

1. **Instantiate solver objects** – The adapter is responsible for translating `circuit_data` into native Pulsim objects (`pulsim.Circuit`, `pulsim.Simulator`, `pulsim.SimulationController`).
2. **Forward progress & streaming data** – Pulsim progress callbacks should be wrapped so that `BackendCallbacks.progress` stays under ~20 Hz. Streaming time/value samples should be relayed through `BackendCallbacks.data_point` for live charting.
3. **Honor control hooks** – `request_pause`, `request_resume`, and `request_stop` must route down to the Pulsim controller so toolbar buttons respond immediately.
4. **Populate `BackendRunResult`** – Convert solver-owned buffers to primitive Python lists/dicts, include solver statistics (steps, elapsed time, solver status), and set `error_message` whenever Pulsim reports a failure.
5. **Report availability** – `BackendInfo.status` should be `"available"` when the adapter is ready. Use `"missing"`, `"error"`, or `"placeholder"` with a helpful `message` when discovery fails so the GUI can disable run controls.

## Backend Discovery & Selection

`BackendLoader` is responsible for:

- registering a placeholder (demo) backend so the GUI stays functional without Pulsim.
- importing the `pulsim` module when present and wrapping it inside `PulsimBackend`.
- optionally loading third-party adapters published via the `pulsimgui.backends` entry-point group.
- exposing `available_backends()` so the UI can populate selection widgets.
- activating the preferred backend (`activate(identifier)`) while persisting the choice through `SettingsService`.

When a user switches builds in the Preferences dialog, `SimulationService.set_backend_preference()` re-instantiates the adapter and saves the identifier. Subsequent launches call `BackendLoader(preferred_id=...)` to honor that choice.

## Circuit Conversion Contract

`SimulationService.convert_gui_circuit()` produces a dictionary with the following shape:

```python
{
    "components": [  # Each entry matches Component.to_dict()
        {
            "id": "uuid",
            "type": "RESISTOR",
            "name": "R1",
            "parameters": {...},
            "pins": [...],
            "pin_nodes": ["1", "0"],  # resolved node IDs per pin
            ...
        },
        ...
    ],
    "wires": [wire.to_dict(), ...],
    "node_map": {"<component-id>": ["n1", "n2", ...]},
    "node_aliases": {"3": "VOUT"},
    "metadata": {"name": "Buck example"},
}
```

`CircuitConverter` requires the `pin_nodes` array to map schematic pins to backend nodes. Aliases are sanitized (spaces replaced with `_`) before being written into the `pulsim.Circuit` so exported netlists remain SPICE-compatible.

Waveform parameters follow a normalized schema (`{"type": "sine", "amplitude": 1.0, ...}`) and the converter builds the corresponding Pulsim waveform objects (`SineWaveform`, `PulseWaveform`, etc.). Unsupported component types raise `CircuitConversionError`, which surfaces to the GUI as a backend error message.

## Control & Progress Flow

1. `SimulationWorker` spawns a thread, captures its identifier, and hands `BackendCallbacks` to the backend.
2. `PulsimBackend` wraps a `pulsim.SimulationController` so pause/resume/stop requests can be relayed through `SimulationBackend.request_*`.
3. Progress callbacks from Pulsim are throttled (`min_interval_ms=50`, `min_steps=200`) before being forwarded to Qt, avoiding UI saturation while still supporting streaming charts.
4. When the GUI cancels a run, `SimulationWorker` sets `_cancelled` and immediately calls `request_stop`, allowing Pulsim to exit gracefully.

## Extending the Adapter

To add a new backend implementation:

1. Publish an entry point under `pulsimgui.backends` pointing to a callable that returns a `SimulationBackend` instance.
2. Ensure the backend exposes a unique `BackendInfo.identifier` so preferences can persist the selection.
3. Honor the `BackendCallbacks` contract and fill out `BackendRunResult` with primitive Python collections.
4. Add the module/package to the environment; PulsimGUI will automatically list it in the Backend selector once the entry point resolves.

This structure keeps GUI code unaware of solver specifics while still allowing power users to toggle between stable, nightly, or remote backends.

## Installing & Switching Backend Versions

### End-user workflow

1. Activate the same virtual environment PulsimGUI uses (or the system interpreter on Windows/macOS).
2. Install or upgrade Pulsim from PyPI:

    ```bash
    python -m pip install --upgrade pulsim
    ```

3. Launch PulsimGUI and open `Preferences → Simulation`.
4. Pick the desired backend from the “Active backend” dropdown. The dialog shows each build’s version, status, install path, and capabilities so you can confirm the upgrade succeeded.

To roll back to a specific release:

```bash
python -m pip install "pulsim==2.1.0"
```

Restart PulsimGUI and re-select the backend if multiple builds are present.

### Developer workflow

- **Local PulsimCore checkout**: from the PulsimCore repo run `python -m pip install -e .` inside the `python/` package (or the project root if it exposes the package). This editable install automatically appears in the backend selector using the identifier defined by the adapter.
- **Nightly/alternate channels**: publish the experimental wheel to an internal index or use `pip install --pre pulsim-nightly.whl`. Multiple distributions can coexist; the GUI preserves your last selection in `SettingsService`.
- **Testing failure paths**: uninstall Pulsim (`python -m pip uninstall pulsim`) to verify the GUI falls back to the demo backend and disables run controls with the appropriate warning.

Whenever a new backend build is installed or removed you only need to restart the GUI—the loader rediscovers the environment on launch.
