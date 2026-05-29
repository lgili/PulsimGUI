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

### Run Bar (v0.8.1+)

Above the schematic, a horizontal **Run Bar** surfaces the primary
simulation controls so they're always one click away:

```
 [▶ Run]   [⏸ Pause]   [■ Stop]   ░░░░░░░░░░  t = 12.4 / 50.0 ms   2.3×   Idle
```

- **Run / Pause / Stop** — buttons enable/disable based on the
  current simulation state.
- **Progress bar** — fills as the simulation advances, color-coded by
  state (blue running, green completed, red failed).
- **Time readout** — current simulation time (auto-scales between
  µs / ms / s).
- **Realtime factor** — `t_sim / t_wall` (how many simulated seconds
  per wall-clock second).
- **Status label** — `Idle`, `Newton (3 iter)`, `Completed in 845 ms`,
  `Failed: ...`.

### Solver pill (v0.8.1+)

The status bar contains a glanceable **Solver pill** showing the
active integrator, timestep, linear solver, and adaptive flag —
color-coded by last-run convergence health:

| Color | Meaning |
|---|---|
| gray | idle / no run yet |
| green | last run converged cleanly |
| amber | last run needed retries / fallback |
| red | last run did not converge |

**Click the pill** to jump to the Simulation Settings dialog
focused on the Solver tab.

### Step-by-step

1. (Optional) Click the solver pill or **Simulation → Settings** to
   configure the time window, integrator, and tolerances.
2. Click **Run** on the Run Bar (or press `F5`).
3. Watch progress + realtime factor on the Run Bar.
4. Watch the solver pill turn green / amber / red on completion.

## 4. Analyze Waveforms

Open the **Scope Workbench** by double-clicking a scope component or via
**View → Scope Workbench**.  Full reference: [Scope Workbench](gui/scope-workbench.md).

### Quick workflow

1. After a simulation completes, the scope opens automatically.
2. Use **zoom / pan** for local inspection (scroll wheel, `Shift`+scroll, `Ctrl`+scroll).
3. Enable **Cursors** (`C`) to activate the bottom measurement panel.
4. Choose the **interval target** (A→B, Visible Window, Cursor A, or Cursor B) to control
   which time window the statistics are computed over.
5. Click **+ Add Measurement** to select which columns are visible (RMS, Peak, Min,
   Pk-Pk, Mean, C1, C2, ΔV).
6. Use the **Views** tab to save and recall named zoom ranges.

### Multi-scope

- Click **+ Scope** in the Scopes tab to open a second independent scope.
- Each scope keeps its own signal set, cursor positions, and measurement columns.
- Drag signals between panes or use right-click → **Send to pane** to overlay traces.

### Sidebar

Press **Ctrl+B** to collapse the sidebar to a compact icon rail; press it again to expand.

## 5. Manage Projects

- Use `File → Save` to persist `.pulsim` projects.
- Use **examples as starting points** for new studies — fifteen
  canonical topologies ship in [`examples/gallery/`](examples-gallery.md)
  (buck, boost, flyback, full-bridge, LLC, NPC, 3-phase rectifier,
  PLL, vector-control, DC motor, …).
- Keep descriptive component/node names to simplify debugging.

## 6. Three-phase / vector control (Phase 28)

Six new virtual control blocks ship under the **Three-Phase / Vector
Control** palette category, mirroring the Pulsim 0.9.0 Phase-28
runtime additions:

| Block | Inputs | Outputs (channels) |
|---|---|---|
| `clarke_transform` | a, b, c | α, β, γ |
| `inverse_clarke_transform` | α, β, γ | a, b, c |
| `park_transform` | α, β (+ θ via metadata) | d, q, zero |
| `inverse_park_transform` | d, q (+ θ via metadata) | α, β |
| `pll` | sine input | θ, ω, lock_error |
| `svm` | α, β reference (+ V_DC) | d_a, d_b, d_c |

Cross-block channel wiring uses the same `*_from_channel` metadata
pattern as `pwm_generator` — set
`theta_from_channel: PLL.theta` on a Park block and the angle is
delivered without an electrical wire.

The shipped **`vector_control_open_loop.pulsim`** example wires
3-phase sources → Clarke → PLL → Park → InvPark → SVM end-to-end as
a starting template for vector-controlled drives.

## 7. Best Practices

- Start with a minimal topology and validate incrementally.
- Avoid changing many parameters at once.
- For convergence issues, tune `step size`, `max step`, and transient robustness first.
- Pair PulsimGui **v0.8.x** with Pulsim **v0.9.x** for the full
  Phase-28 component coverage (Clarke / Park / PLL / SVM).
- Keep backend pinned to `v0.9.0` in shared environments.
