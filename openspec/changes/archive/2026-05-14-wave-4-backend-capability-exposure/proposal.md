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

**Sub-wave C — REMOVED FROM WAVE-4 (deferred to wave-5):**
A mid-wave feasibility check on the Pulsim runtime revealed that the C++ classes
this sub-wave targeted (`grid::three_phase_source`, `motors::{pmsm,pmsm_foc,dc_motor,
mechanical}`, `magnetic::{saturable_transformer,hysteresis_inductor,bh_curve}`) are
not yet integrated into the `Circuit` device variant — their own headers flag a
"Circuit-variant integration follow-up" that hasn't shipped yet. The math objects
exist (`evaluate()` / `step()` methods) but there is no `Circuit::add_pmsm()` /
`add_three_phase_source()` / `add_saturable_transformer()` API. Exposing the math
objects through pybind alone would give users calculator-style classes that cannot
be wired into a schematic, which is low value relative to the implementation cost.
A new OpenSpec change is opened on the Pulsim side to track the upstream device-
integration work; once that lands, a wave-5 GUI change reopens the palette items.

The gRPC remote backend client (item 12 from the original audit) was also out of
scope for wave-4 and remains parked.

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
- **Affected code (Pulsim, sub-wave C only):** *Not touched in wave-4* — see the
  separate Pulsim-side OpenSpec for the device-integration work that has to land
  before sub-wave C can reopen.
- **Release plan:** sub-wave A → PulsimGui **v0.10.0 ✅ (tag `v0.10.0`)**;
  sub-wave B → PulsimGui **v0.11.0 ✅ (tag `v0.11.0`)**; sub-wave C → deferred to
  wave-5 once the Pulsim runtime ships the `Circuit::add_*` hooks for motors,
  three-phase sources, and saturable magnetics.
