## 1. Sub-wave A — GUI-only plumbing (ship as v0.10.0)

### 1.1 FMU 2.0 export
- [x] 1.1.1 Add `File ▸ Export ▸ FMU 2.0…` action in `main_window.py`.
- [x] 1.1.2 Create `src/pulsimgui/views/dialogs/fmu_export_dialog.py` (model name, output path,
      integration step, optional output-node selector). FMI 2.0 co-sim only; the runtime API
      does not yet expose model-exchange or GUID overrides.
- [x] 1.1.3 Wire the dialog to `pulsim.fmu.export` via a new `PulsimBackend.export_fmu()` +
      `SimulationService.export_fmu()` helper pair (kept on the backend adapter, not the
      ExportService, so circuit conversion stays in the simulation pipeline).
- [x] 1.1.4 Surface backend exceptions in a clear error dialog (no silent failures).
- [x] 1.1.5 Tests: 8 unit tests cover default model name, button gating, browse-extension
      handling, output-list collection, settings-collection roundtrip, capability gate,
      backend-error path, and ".fmu" extension auto-append.

### 1.2 C99 real-time controller codegen
- [ ] 1.2.1 Add `File ▸ Export ▸ C99 controller…` action.
- [ ] 1.2.2 Create `c99_export_dialog.py` (output dir, target prefix, discretization choice, sample-rate).
- [ ] 1.2.3 Wire to `pulsim.codegen.generate` via `export_service.export_c99()`.
- [ ] 1.2.4 Tests: dialog renders, smoke-write of a stub controller.

### 1.3 Monte-Carlo sweep upgrade
- [ ] 1.3.1 Extend `parameter_sweep_dialog.py` with a tab/page for "Monte-Carlo" alongside
      the existing linear/log range mode.
- [ ] 1.3.2 Multi-row component+parameter table; each row picks a `Distribution`
      (uniform / log-uniform / normal / cartesian) with bound editors.
- [ ] 1.3.3 Metric selector wired to `pulsim.sweep.metrics` (`steady_state` / `peak` / `rms` /
      `settling_time` / `custom`).
- [ ] 1.3.4 Results viewer: histogram + scatter on metric axes, CSV export.
- [ ] 1.3.5 Tests: distribution wiring, metric computation roundtrip.

### 1.4 Losses & efficiency dashboard
- [ ] 1.4.1 New `LossesTab` widget under the scope workbench (sibling to FFT / Compare).
- [ ] 1.4.2 Reads `SystemLossSummary` / `LossAccumulator` / `EfficiencyCalculator` from the
      current simulation result.
- [ ] 1.4.3 Per-device table: conduction loss / switching loss / total / share %; sortable.
- [ ] 1.4.4 Stacked bar chart for system-level breakdown; efficiency readout vs. input/output power.
- [ ] 1.4.5 Tests: tab populates from a synthetic `SystemLossSummary`, hides cleanly when no data.

### 1.5 Convergence diagnostics deep-dive
- [ ] 1.5.1 Extend `convergence_diagnostics_dialog.py` with three new sub-views:
      Per-iteration residual chart, Per-variable convergence table, Linear-solver fallback chain list.
- [ ] 1.5.2 Reads `ConvergenceHistory` / `IterationRecord` / `PerVariableConvergence` /
      `FallbackTraceEntry` / `LinearSolverTelemetry` from the latest `BackendTelemetry`.
- [ ] 1.5.3 Tests: dialog renders all three sub-views from a synthetic telemetry blob.

### 1.6 Advanced solver knobs
- [ ] 1.6.1 Add an "Advanced" tab to `simulation_settings_dialog.py`.
- [ ] 1.6.2 Surface `GminConfig`, `SourceSteppingConfig`, `PseudoTransientConfig`,
      `InitializationConfig`, `DCConvergenceConfig`.
- [ ] 1.6.3 Surface `BDFOrderConfig`, `RichardsonLTEConfig`, `AdvancedTimestepConfig`.
- [ ] 1.6.4 Surface `LinearSolverStackConfig` with a combobox of stacks (KLU / EnhancedSparseLU /
      GMRES / BiCGSTAB) and `IterativeSolverConfig` editors (ILUT, scaling).
- [ ] 1.6.5 Roundtrip these through `SimulationOptions` save/load.
- [ ] 1.6.6 Tests: each new knob persists, loads, applies; the dialog gracefully ignores
      unknown fields when reading older project files.

### 1.7 Release sub-wave A
- [ ] 1.7.1 Bump PulsimGui `0.9.2 → 0.10.0`.
- [ ] 1.7.2 Tag `v0.10.0`, push, monitor.

## 2. Sub-wave B — new analysis modes (ship as v0.11.0)

### 2.1 FRA (Frequency Response Analysis)
- [ ] 2.1.1 Add `Simulation ▸ FRA…` action.
- [ ] 2.1.2 Create `fra_dialog.py` (start/stop freq, points/decade, perturbation amplitude,
      probe selection, output type magnitude/phase).
- [ ] 2.1.3 Wire to `Simulator.run_fra` via `simulation_service.run_fra()`.
- [ ] 2.1.4 Result view: reuse `BodePlotDialog` axes, overlay via `fra_overlay` helper.
- [ ] 2.1.5 Export FRA result to CSV via existing `export_fra_csv` / `export_fra_json`.
- [ ] 2.1.6 Tests: dialog roundtrip, run on a synthetic plant, result renders.

### 2.2 Periodic Steady-State (shooting)
- [ ] 2.2.1 Add `Simulation ▸ Periodic Steady-State…` action.
- [ ] 2.2.2 Create `periodic_ss_dialog.py` (period guess, Newton tol, max shooting iterations,
      use-IC checkbox).
- [ ] 2.2.3 Wire to `PeriodicSteadyStateOptions/Result`.
- [ ] 2.2.4 Result view: single-period waveform inset + ripple metrics summary.
- [ ] 2.2.5 Tests: convergence on a synthetic buck, divergence path surfaces a clear error.

### 2.3 Harmonic Balance
- [ ] 2.3.1 Add `Simulation ▸ Harmonic Balance…` action.
- [ ] 2.3.2 Create `harmonic_balance_dialog.py` (fundamental freq, harmonics count, balancing tol).
- [ ] 2.3.3 Wire to `HarmonicBalanceOptions/Result`.
- [ ] 2.3.4 Result view: spectrum chart with magnitude/phase per harmonic.
- [ ] 2.3.5 Tests: roundtrip on a synthetic rectifier circuit.

### 2.4 Release sub-wave B
- [ ] 2.4.1 Bump PulsimGui `0.10.x → 0.11.0`.
- [ ] 2.4.2 Tag `v0.11.0`, push, monitor.

## 3. Sub-wave C — palette + magnetics + Pulsim pybind (ship as v0.12.0 + Pulsim v0.10.0)

### 3.1 Pulsim pybind11 bindings (Pulsim repo)
- [ ] 3.1.1 Expose `motors::pmsm` + `pmsm_foc` + `dc_motor` + `mechanical` in `python/bindings.cpp`.
- [ ] 3.1.2 Expose `grid::three_phase_source` (balanced + unbalanced phase config).
- [ ] 3.1.3 Expose `magnetic::saturable_transformer` + `hysteresis_inductor` + `bh_curve` +
      `core_catalog`.
- [ ] 3.1.4 Update `python/pulsim/__init__.py` `__all__` and add module-level type hints.
- [ ] 3.1.5 Backend smoke tests (one transient per new component).
- [ ] 3.1.6 Tag Pulsim `v0.10.0`, publish to PyPI.

### 3.2 PulsimGui — Three-phase grid source
- [ ] 3.2.1 Add `ComponentType.THREE_PHASE_SOURCE` (in "Sources" category).
- [ ] 3.2.2 Properties dialog: line-to-line voltage, frequency, phase rotation, unbalance %,
      THD injection.
- [ ] 3.2.3 Wire `simulation_service` instantiation through the new pybind class.
- [ ] 3.2.4 Tests: schematic drop, params persist, simulation produces three phase-shifted waveforms.

### 3.3 PulsimGui — Motors & Drives palette category
- [ ] 3.3.1 New palette category "Motors & Drives".
- [ ] 3.3.2 Add ComponentTypes: `PMSM`, `PMSM_FOC`, `DC_MOTOR`, `MECHANICAL_LOAD`.
- [ ] 3.3.3 Each with a parameter form (pole pairs, Ld/Lq, flux linkage, inertia, friction).
- [ ] 3.3.4 Wire to the new pybind bindings.
- [ ] 3.3.5 Tests: drop each, simulate a no-load spin-up to steady-state.

### 3.4 PulsimGui — Advanced magnetics + BH-curve editor
- [ ] 3.4.1 Add `ComponentType.SATURABLE_TRANSFORMER` and `HYSTERESIS_INDUCTOR`.
- [ ] 3.4.2 BH-curve editor widget: plot, drag-to-edit anchor points, import from
      `core_catalog`, normalize/export.
- [ ] 3.4.3 Properties dialog launches the BH editor when applicable.
- [ ] 3.4.4 Tests: editor preserves curve through save/load.

### 3.5 Release sub-wave C
- [ ] 3.5.1 Bump PulsimGui `0.11.x → 0.12.0`, pin `pulsim>=0.10.0` in `pyproject.toml`.
- [ ] 3.5.2 Tag `v0.12.0`, push, monitor.

## 4. Docs and announcement (post sub-wave C)
- [ ] 4.1 Update `docs/user-manual.md` with the new export / analysis / motors workflows.
- [ ] 4.2 Add 3 example projects (FMU export demo, PMSM-FOC spin-up, MC sweep on a buck).
- [ ] 4.3 Archive this OpenSpec change.
