## Why

A capability gap audit of Pulsim 0.9.0 (the version PulsimGui ships against today) versus the current PulsimGui palette / menus surfaced twelve high-value backend features that the runtime exposes but the GUI does not yet make reachable: FMU 2.0 co-simulation export, C99 real-time codegen, FRA (closed-loop frequency response), periodic-steady-state shooting, harmonic balance, three-phase grid source, PMSM/FOC + DC-motor + mechanical-load components, saturable-transformer / hysteresis-inductor magnetics, Monte-Carlo sweep with non-uniform distributions, loss-and-efficiency dashboard, advanced convergence diagnostics, and the gRPC remote backend client. Three of these (motors, three-phase source, advanced magnetics) also need pybind exposure on the Pulsim side — the C++ classes exist in `core/include/pulsim/v1/{motors,grid,magnetic}/` but are not yet at the Python boundary. Without these, users still have to drop into the Python API for power-electronics workflows the GUI was meant to own.

## What Changes

Wave-4 ships as three sub-waves of increasing risk so each can be tagged and stress-tested before the next lands.

**Sub-wave A — GUI-only plumbing (lowest risk, no backend changes):**
- File ▸ Export ▸ FMU 2.0… dialog wrapping `pulsim.fmu.export`
- File ▸ Export ▸ C99 controller… dialog wrapping `pulsim.codegen.generate`
- Upgrade `ParameterSweepDialog` to multi-parameter Monte-Carlo with `Distribution` (uniform / log-uniform / normal) and the existing custom metrics (`rms`, `settling_time`, `custom`)
- New "Losses" tab in the scope workbench reading `LossAccumulator` / `EfficiencyCalculator` / `SystemLossSummary` — per-device conduction vs. switching breakdown
- Convergence diagnostics dialog reads `ConvergenceHistory` / `IterationRecord` / `PerVariableConvergence` / `FallbackTraceEntry` / `LinearSolverTelemetry`
- Advanced solver knobs panel (Gmin stepping, source stepping, pseudo-transient, KLU/GMRES/BiCGSTAB selection, ILUT, BDF order, Richardson LTE)

**Sub-wave B — new analysis modes (medium risk, new dialogs + result viewers):**
- Simulation ▸ FRA… action + `FraDialog` reusing `BodePlotDialog`'s axes — wraps `Simulator.run_fra`
- Simulation ▸ Periodic Steady-State… action + `PeriodicSteadyStateDialog` — wraps `PeriodicSteadyStateOptions/Result`
- Simulation ▸ Harmonic Balance… action + `HarmonicBalanceDialog` — wraps `HarmonicBalanceOptions/Result`

**Sub-wave C — palette + magnetics (highest risk, needs cross-repo pybind work):**
- New "Motors & Drives" palette category: PMSM, PMSM with FOC, DC motor, mechanical load (inertia + friction)
- Three-phase voltage source component (feeds the existing Clarke/Park/PLL/SVM blocks)
- Saturable transformer + hysteresis inductor variants in the magnetics palette
- BH-curve editor inside the properties dialog for saturable / hysteresis devices
- Pulsim-side pybind11 bindings for `motors/{pmsm,pmsm_foc,dc_motor,mechanical}.hpp`, `grid/three_phase_source.hpp`, `magnetic/{saturable_transformer,hysteresis_inductor,bh_curve}.hpp` — released as Pulsim 0.10.0

The gRPC remote backend client (item 12 from the audit) is **out of scope** for wave-4; it needs project-wide settings/preferences work and is parked for wave-5.

## Impact

- **Affected specs:**
  - `simulation-control` — new analysis modes, sweep upgrade, advanced solver knobs, FMU/codegen export actions, loss dashboard
  - `component-library` — Motors & Drives category, three-phase source, saturable transformer, hysteresis inductor, BH-curve editor
  - `application-shell` — File ▸ Export submenu, Simulation menu additions
- **Affected code (PulsimGui):**
  - `src/pulsimgui/views/dialogs/` — `fmu_export_dialog.py`, `c99_export_dialog.py`, `fra_dialog.py`, `periodic_ss_dialog.py`, `harmonic_balance_dialog.py`, new advanced-solver tab in `simulation_settings_dialog.py`, sweep dialog rewrite
  - `src/pulsimgui/views/scope/` — new `LossesTab` widget in the scope workbench
  - `src/pulsimgui/views/main_window.py` — File and Simulation menu wiring
  - `src/pulsimgui/models/component.py` + `component_catalog.py` — new ComponentType entries
  - `src/pulsimgui/services/simulation_service.py` — wiring for the new analysis modes
- **Affected code (Pulsim, sub-wave C only):**
  - `python/bindings.cpp` — pybind11 entries for the motors / grid / magnetic classes
  - `python/pulsim/__init__.py` — `__all__` additions and re-exports
- **Release plan:** sub-wave A → PulsimGui v0.10.0, sub-wave B → v0.11.0, sub-wave C → Pulsim v0.10.0 + PulsimGui v0.12.0.
