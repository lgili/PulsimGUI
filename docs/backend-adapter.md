# Backend Adapter

Technical overview of how PulsimGui converts GUI schematics and executes simulations using the Pulsim backend.

## Architecture

```text
MainWindow
  -> SimulationService
      -> convert_gui_circuit()
      -> BackendLoader
          -> PulsimBackend | PlaceholderBackend
              -> CircuitConverter
              -> run_transient()
```

## Core Responsibilities

### `SimulationService`

- Keeps `SimulationSettings` in memory.
- Converts GUI project data into simulation format.
- Executes simulation in a worker thread.
- Emits progress updates, streaming points, and final results.

### `BackendLoader`

- Discovers available backends.
- Activates the preferred backend saved in settings.
- Falls back to placeholder backend when Pulsim is unavailable.

### `CircuitConverter`

- Maps GUI components to `pulsim.Circuit`.
- Resolves electrical nodes and aliases.
- Ignores visualization-only instrumentation components.
- Translates waveform parameters (including legacy keys like `td/tr/tf/pw/per`).

## Data Contracts

### `BackendInfo`

UI/backend selection metadata: `identifier`, `version`, `status`, `capabilities`, `message`.

### `BackendCallbacks`

Execution hooks:

- `progress(value, message)`
- `data_point(time, signals)`
- `check_cancelled()`
- `wait_if_paused()`

### `BackendRunResult`

Normalized simulation output:

- `time: list[float]`
- `signals: dict[str, list[float]]`
- `statistics: dict[str, Any]`
- `error_message: str`

## Operational Best Practices

- Pin backend to `v0.5.2` for reproducibility.
- Keep `Auto-sync` enabled in validation environments.
- For convergence failures, tune `step size`, `max step`, `max iterations`, and transient robustness first.
