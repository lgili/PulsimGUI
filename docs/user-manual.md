# User Manual

Operational guide for day-to-day PulsimGui usage.

## 1. Create and Edit Schematics

### Insert components

- Drag components from the library into the schematic canvas.
- Or use keyboard shortcuts when available (for example: `R`, `C`, `L`, `V`, `G`).

### Wiring

- Enable the wire tool (`W`).
- Click the source pin, route the wire, and finish on the destination pin.
- Use junctions to branch nodes.

### Quick editing

- Multi-select: `Ctrl + click` or selection box.
- Move: drag.
- Rotate: use rotate action in the schematic.
- Delete: `Delete`.

## 2. Configure Component Parameters

- Select a component.
- Edit values in the **Properties Panel**.
- Use SI prefixes when applicable (`k`, `m`, `u`, `n`).
- Parameters with fixed valid choices (e.g. `carrier`, `color`, `thermal_network`,
  `switching_loss_model`, `magnetic_core_model`, `magnetic_core_loss_policy`) are rendered
  as **dropdown menus** automatically — no free-text entry is required.

### Control blocks (`Ts`)

- Control blocks use per-block `Ts` (`sample_time`) in the **Properties Panel**.
- `Ts = 0`: auto/continuous update (runs every control evaluation step).
- `Ts > 0`: discrete update with sampling period `Ts` (output is held between updates).
- Scopes and probes do not expose `Ts`.

### PWM Generator — optional `DUTY_IN` port

- By default the PWM block has a single output pin (`PWM`).
- To feed duty cycle from a control signal at runtime, enable the optional `DUTY_IN` input
  in the **Properties Panel** (`enable_duty_input = True`).
- When enabled, a second pin appears and the static `duty` parameter is ignored while the
  port is connected.

### Saturable Inductor — nonlinear magnetic core

- The **Sat. Inductor** component exposes a full **Magnetic Core** parameter group.
- The `magnetic_core_model` dropdown selects the core behavior:
  - `saturation` — smooth saturation curve (default). Symbol: solid bar.
  - `hysteresis` — bounded hysteresis state model. Symbol: two dashed bars.
- The `magnetic_core_loss_policy` dropdown selects how core loss is reported:
  - `telemetry_only` — loss waveform exported as a virtual channel only.
  - `loss_summary` — loss also appended to the thermal/loss summary tables.
- See [Simulation Configuration → Magnetic Core Parameters](gui/configuracao-simulacao.md#magnetic-core-parameters-saturable-inductor)
  for the full parameter list.

## 3. Run Simulation

1. Open `Simulation Settings`.
2. Configure time window, integration method, and tolerances.
3. Click **Run** (`F5`).
4. Monitor progress in the status bar.

## 4. Analyze Waveforms

- Plot voltage/current signals in the viewer.
- Use zoom and pan for local inspection.
- Use cursors for delta-time and amplitude measurements.
- Compare multiple traces for phase and dynamic analysis.

## 5. Manage Projects

- Use `File → Save` to persist `.pulsim` projects.
- Use examples as starting points for new studies.
- Keep descriptive component/node names to simplify debugging.

## 6. Best Practices

- Start with a minimal topology and validate incrementally.
- Avoid changing many parameters at once.
- For convergence issues, tune `step size`, `max step`, and transient robustness first.
- Keep backend pinned to `v0.7.9` in shared environments.
