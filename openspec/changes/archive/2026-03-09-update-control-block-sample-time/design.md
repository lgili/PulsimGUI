# Design: update-control-block-sample-time

## Context
Control-domain blocks currently rely on a global scheduling policy defined in Simulation Settings (`control_mode`, `control_sample_time`). This prevents mixed-rate control and forces unrelated blocks to run at the same sampling period.

## Goals
- Add per-control-block `Ts` in component parameters.
- Keep default behavior simple (`Ts=0` auto/continuous).
- Support mixed-rate control chains.
- Preserve compatibility when loading legacy projects.

## Non-Goals
- Changing probe or scope behavior.
- Introducing a new visual pin or wiring mode for sampling clocks.
- Reworking solver or transient UI beyond removing global control scheduling controls.

## Decisions

### 1) Canonical parameter name
Use `sample_time` as the canonical persisted parameter name on control blocks.
- UI label: `Ts`.
- Alias compatibility: continue accepting `sample_period` where legacy blocks already use it.

### 2) Eligible component types
Apply per-block `sample_time` to signal/control blocks that produce or transform control signals, excluding measurement and visualization components.
- Included: `CONSTANT`, `GAIN`, `SUM`, `SUBTRACTOR`, `PI_CONTROLLER`, `PID_CONTROLLER`, `PWM_GENERATOR`, `INTEGRATOR`, `DIFFERENTIATOR`, `LIMITER`, `RATE_LIMITER`, `HYSTERESIS`, `LOOKUP_TABLE`, `TRANSFER_FUNCTION`, `DELAY_BLOCK`, `SAMPLE_HOLD`, `STATE_MACHINE`, `SIGNAL_MUX`, `SIGNAL_DEMUX`, `C_BLOCK`, and other control-domain processing blocks.
- Excluded: `ELECTRICAL_SCOPE`, `THERMAL_SCOPE`, `VOLTAGE_PROBE`, `VOLTAGE_PROBE_GND`, `CURRENT_PROBE`, `POWER_PROBE`.

### 3) Runtime semantics
- `sample_time <= 0`: continuous/auto scheduling for that block.
- `sample_time > 0`: discrete scheduling; the block updates only on sampling instants and otherwise keeps last output.

### 4) Legacy compatibility
When opening projects that only have global `control_mode/control_sample_time` and missing per-block `sample_time`, migrate at load time:
- if legacy mode is discrete (or sample time > 0), stamp that value into eligible control blocks that do not already define `sample_time`.
- keep existing explicit per-block `sample_time` untouched.

### 5) Backend compatibility bridge
For backend paths that still consume global control options, derive a compatibility aggregate from per-block values:
- if any eligible block has `sample_time > 0`, use global discrete mode with representative period = minimum positive `sample_time`.
- otherwise use auto/continuous.

This keeps old backend paths operational while the canonical source of truth becomes per-block scheduling.

## Risks and Mitigations
- Risk: behavior drift in existing projects after migration.
  - Mitigation: migrate only when per-block value is absent; add regression tests for legacy project load.
- Risk: inconsistent parameter naming (`sample_time` vs `sample_period`).
  - Mitigation: normalize aliases in one helper and test both names.
- Risk: UI test breakage from removed controls in Simulation Settings.
  - Mitigation: update tests to assert control fields are absent and move assertions to properties/defaults tests.
