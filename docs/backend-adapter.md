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
- Normalizes magnetic core parameters for `SATURABLE_INDUCTOR` (e.g. renames
  `i_equiv_init` → `magnetic_i_equiv_init` expected by the backend).

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

### `BackendRunResult.statistics` (telemetry keys)

When using modern Pulsim backends, `statistics` can include structured diagnostics:

- Core run metadata:
  - `execution_path`
  - `status`
  - `diagnostic`
  - `total_steps`
  - `newton_iterations_total`
  - `timestep_rejections`
  - `total_time_seconds`
  - `message`
- Linear solver telemetry:
  - `linear_solver_telemetry` (calls, iterations, timings, solver/preconditioner info)
- Backend/runtime telemetry:
  - `backend_telemetry` (selected backend, formulation mode, counters, cache metrics, failure reason)
- Fallback/retry trace:
  - `fallback_trace`
  - `fallback_trace_count`
- Loss and thermal telemetry:
  - `loss_summary`
  - `system_total_loss`
  - `loss_device_count`
  - `thermal_summary`
  - `thermal_max_temperature`
  - `component_electrothermal`
  - `electrothermal_component_count`
  - `electrothermal_peak_temperature`
- Magnetic core virtual channels (pulsim ≥ v0.7.9):
  - `virtual_channels` — dict of channel arrays keyed by `<component>.<channel>`
  - `virtual_channel_metadata` — metadata per channel (`domain`, `unit`, `source_component`)

All telemetry keys are optional and depend on backend version/capabilities.

### Magnetic Virtual Channels (pulsim ≥ v0.7.9)

When a `SATURABLE_INDUCTOR` component has `magnetic_core_enabled = True`, the backend
exports additional signal channels via `result.virtual_channels`:

| Channel key | Domain | Unit | Condition |
| --- | --- | --- | --- |
| `<component>.core_loss` | `loss` | W | Always when enabled. |
| `<component>.h_state` | — | — | Only when `model = hysteresis`. |
| `T(<component>.core)` | `thermal` | °C | When thermal simulation is enabled. |

The GUI merges these channels into the waveform viewer automatically alongside regular
electrical signals. When `loss_policy = loss_summary`, the backend also appends a row to
`loss_summary.device_losses` with `device_name = "<component>.core"`.

For advanced electrothermal parity on magnetic components, ensure the backend exposes:

- `MagneticCoreConfig.model`, `loss_policy`
- `MagneticCoreConfig.core_loss_k`, `core_loss_alpha`, `core_loss_freq_coeff`
- `MagneticCoreConfig.hysteresis_band/strength/loss_coeff/state_init`

## Operational Best Practices

- Pin backend to `v0.7.9` for reproducibility.
- For advanced electrothermal parity on semiconductors, ensure backend exposes:
  - `SimulationOptions.switching_energy_surfaces`
  - `ThermalDeviceConfig.network_kind`, `stage_rth/stage_cth`
  - `ThermalDeviceConfig.shared_sink_id/shared_sink_rth/shared_sink_cth`
- For magnetic core simulation, ensure backend version ≥ `v0.7.9` and `MagneticCoreConfig`
  is available (see [Magnetic Virtual Channels](#magnetic-virtual-channels-pulsim-v079) above).
- Keep `Auto-sync` enabled in validation environments.
- For convergence failures, tune `step size`, `max step`, `max iterations`, and transient robustness first.
