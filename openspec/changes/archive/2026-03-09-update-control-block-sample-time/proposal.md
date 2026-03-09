# Proposal: update-control-block-sample-time

## Status
DRAFT

## Summary
Move control scheduling from global Simulation Settings into per-block parameters, using a Simulink-style `Ts` (`sample_time`) field on control blocks. Default `Ts=0` means auto/continuous execution, and `Ts>0` means discrete execution at that period.

## Why
The current global `Control update mode` + `Control sample time` makes mixed-rate control hard and couples all control blocks to the same rate. Users need per-block sampling to model realistic control loops where each block may run continuously or at a specific sampling period.

## What Changes
- Remove global control scheduling controls from the Simulation Settings dialog.
- Add editable `Ts` (`sample_time`) parameter to control blocks (excluding scopes and probes).
- Define runtime semantics:
  - `Ts = 0`: auto/continuous update (every solver/control evaluation step).
  - `Ts > 0`: discrete update at `Ts`, hold last output between updates.
- Persist `Ts` per component in project files and templates.
- Add backward-compatibility migration for legacy project-level `control_mode`/`control_sample_time`.

## Impact
- Affected specs:
  - `simulation-control`
  - `parameter-editor`
- Affected code:
  - `src/pulsimgui/views/dialogs/simulation_settings_dialog.py`
  - `src/pulsimgui/models/component.py`
  - `src/pulsimgui/services/backend_adapter.py`
  - `src/pulsimgui/services/circuit_data_builder.py`
  - `src/pulsimgui/models/project.py`
  - tests for solver dialog, backend adapter transient compatibility, and control block defaults
