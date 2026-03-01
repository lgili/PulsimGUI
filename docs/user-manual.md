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
- Keep backend pinned to `v0.5.2` in shared environments.
