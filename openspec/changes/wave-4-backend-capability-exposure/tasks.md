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
- [x] 1.2.1 Add `File ▸ Export ▸ C99 controller…` action.
- [x] 1.2.2 Create `c99_export_dialog.py` (output dir, discretization step, operating-point
      time, target combobox seeded with `c99` only — ARM/Zynq targets are deferred per the
      runtime docstring).
- [x] 1.2.3 Wire to `pulsim.codegen.generate` via `PulsimBackend.export_c99` +
      `SimulationService.export_c99`.
- [x] 1.2.4 Tests: 5 unit tests (button gating, browse, settings roundtrip, capability
      gate, backend-error path).

### 1.3 Monte-Carlo sweep upgrade
- [x] 1.3.1 Extend `parameter_sweep_dialog.py` with a QTabWidget hosting "Range" (preserves
      the prior single-parameter behaviour byte-for-byte) and "Monte Carlo" tabs.
- [x] 1.3.2 Multi-row component+parameter table; each row picks a distribution name
      (uniform / log-uniform / normal / cartesian) plus low/high (or μ/σ for normal) editors.
- [x] 1.3.3 Metric selector wired to `pulsim.sweep.metrics` (`steady_state` / `peak` /
      `rms` / `settling_time`). Custom metrics are accepted at the service layer; the
      dialog limits to the four canonical kinds for clarity.
- [ ] 1.3.4 Results viewer: histogram + scatter on metric axes, CSV export.
      **Deferred** to a follow-up commit — the main_window handler currently shows a
      "queued" toast so the dialog ships with end-to-end settings collection without a
      half-broken pipeline.
- [x] 1.3.5 Tests: 21 service unit tests cover the distribution factories, runtime-spec
      dispatch, settings validation, offline synthesizer, and runtime-result adapter;
      6 dialog unit tests cover mode toggle, row add/remove, normal-distribution param
      mapping, seed handling, and range/MC mutual exclusivity.

### 1.4 Losses & efficiency dashboard
- [x] 1.4.1 New `LossesDashboardDialog` reachable from Simulation ▸ Losses & Efficiency…
      (Promotion to a permanent tab inside the scope workbench is queued as a follow-up;
      shipping it as a modal dialog first lets us iterate without restructuring the
      8000-line scope_window.py.)
- [x] 1.4.2 Reads loss breakdown from the existing `ThermalResult.devices[i].losses`
      (`LossBreakdown` dataclass already on the GUI side; the runtime already computes
      this through ThermalService).
- [x] 1.4.3 Per-device table: conduction / switching / reverse-recovery / total / share %.
      Sortable by any numeric column. Default sort is total-descending.
- [ ] 1.4.4 Stacked bar chart for system-level breakdown; efficiency readout vs.
      input/output power. **Deferred** — `ThermalResult` does not yet carry input/output
      power telemetry, so the dialog shows a `—` efficiency until that path lands.
- [x] 1.4.5 Tests: 6 dialog unit tests (empty state when no result, empty state when
      result has no devices, populates one row per device, share column sums to 1.0,
      `set_result` repopulates / clears, default sort is total descending).

### 1.5 Convergence diagnostics deep-dive
- [x] 1.5.1 Per-iteration residual chart + per-variable convergence table already shipped
      in the prior `convergence_diagnostics_dialog.py` (Iteration History + Problematic
      Variables tabs). Wave-4 adds a fifth tab — "Linear Solver" — listing the active
      strategy plus the catalog of known fallback strategies, with the active one
      highlighted by a green ● bullet.
- [~] 1.5.2 Reads `ConvergenceInfo.strategy_used` + `failure_reason` directly. The full
      per-iteration `FallbackTraceEntry` / `LinearSolverTelemetry` types are **deferred** —
      Pulsim does not yet expose them at the Python boundary; the new tab is structured
      so those records can be appended as a sub-table when the runtime ships them.
- [x] 1.5.3 Tests: extended the existing dialog suite to assert the new tab is present
      (test_dialog_has_five_tabs) and to verify the active-strategy bullet is correctly
      marked (test_linear_solver_tab_highlights_active_strategy). Existing 14 dialog
      tests still pass.

### 1.6 Advanced solver knobs
- [x] 1.6.1 Added a "Solver Stack" tab to the dialog's advanced section (alongside the
      existing Transient / DC Setup / Thermal & Losses / Frequency Analysis tabs).
- [~] 1.6.2 `GminConfig`, `SourceSteppingConfig`, `PseudoTransientConfig`,
      `InitializationConfig`, `DCConvergenceConfig`: **deferred** — most are exposed
      indirectly via the existing `dc_strategy` / `gmin_initial` / `gmin_final` /
      `dc_source_steps` fields on `SimulationSettings`. Native fine-grained configs land
      when the runtime adds them to the project schema.
- [~] 1.6.3 `BDFOrderConfig` exposed via the new `bdf_max_order` field (1..5);
      `RichardsonLTEConfig` and `AdvancedTimestepConfig` deferred (no runtime hooks yet).
- [x] 1.6.4 `LinearSolverStackConfig` exposed via the new `linear_solver_stack` field
      (auto / KLU / EnhancedSparseLU / GMRES / BiCGSTAB) and `IterativeSolverConfig`
      partial — surfaced `iterative_solver_max_iterations` and `iterative_solver_restart`
      (GMRES restart length). ILUT preconditioner + scaling toggles deferred.
- [x] 1.6.5 New fields persist through `_store_settings()` and load through the existing
      `_load_from_source()` path with `getattr` fallback for older project files.
- [x] 1.6.6 4 unit tests in `test_simulation_settings_advanced.py` cover: tab presence,
      five-stack combobox content + default 200/30/5 values, full roundtrip through
      `_store_settings`, and graceful fallback when older settings objects lack the new
      attributes.

### 1.7 Release sub-wave A
- [x] 1.7.1 Bump PulsimGui `0.9.2 → 0.10.0` (`src/pulsimgui/__init__.py` + `pyproject.toml`).
- [x] 1.7.2 Tag `v0.10.0`, push, monitor. Full suite green except the same pre-existing
      `test_ctrl_b_shortcut_toggles_left_panel` flake documented since v0.9.1.

## 2. Sub-wave B — new analysis modes (ship as v0.11.0)

### 2.1 FRA (Frequency Response Analysis)
- [x] 2.1.1 Added `Simulation ▸ FRA (Frequency Response)…` action.
- [x] 2.1.2 `FraDialog` in `views/dialogs/analysis_modes_dialogs.py` (start/stop freq,
      points/decade, scale, perturbation amplitude, source, measurement nodes).
- [x] 2.1.3 Wired to `Simulator.run_fra` via `PulsimBackend.run_fra` +
      `SimulationService.run_fra`. Capability gate (`"fra"`) introspects
      `Simulator.run_fra` on the active backend.
- [ ] 2.1.4 Result view: rich Bode-overlay viewer **deferred** — the dialog shows a text
      summary (first frequency point + total transient steps) so users can drive the
      sweep today. Follow-up commit will plug `FraResult` into the existing BodePlotDialog
      axes via the `fra_overlay` helper.
- [ ] 2.1.5 CSV/JSON export of FRA result **deferred** — needs an `export_fra_csv`
      wrapper next to the existing FRA service hook.
- [x] 2.1.6 3 unit tests in `test_analysis_modes_dialogs.py` (settings collection, capability
      gate, backend-failure surfacing as QMessageBox.warning).

### 2.2 Periodic Steady-State (shooting)
- [x] 2.2.1 Added `Simulation ▸ Periodic Steady-State…` action.
- [x] 2.2.2 `PeriodicSteadyStateDialog` (period, Newton tol, max iterations, relaxation,
      store-last-transient checkbox).
- [x] 2.2.3 Wired to `Simulator.run_periodic_shooting` via `PulsimBackend.run_periodic_steady_state`
      + `SimulationService.run_periodic_steady_state`.
- [ ] 2.2.4 Single-period waveform inset + ripple metrics summary **deferred** to a
      follow-up — the dialog reports iteration count + final residual today.
- [x] 2.2.5 2 unit tests (settings collection, convergence-failure warning).

### 2.3 Harmonic Balance
- [x] 2.3.1 Added `Simulation ▸ Harmonic Balance…` action.
- [x] 2.3.2 `HarmonicBalanceDialog` (period, samples per period, max iterations, balancing
      tolerance, relaxation, initialize-from-transient checkbox).
- [x] 2.3.3 Wired to `Simulator.run_harmonic_balance` via `PulsimBackend.run_harmonic_balance`
      + `SimulationService.run_harmonic_balance`.
- [ ] 2.3.4 Spectrum bar chart **deferred** — the dialog reports iteration count, final
      residual, and sample count today.
- [x] 2.3.5 2 unit tests (settings collection, backend-exception critical path).

### 2.4 Release sub-wave B
- [x] 2.4.1 Bump PulsimGui `0.10.0 → 0.11.0`.
- [x] 2.4.2 Tag `v0.11.0`, push, monitor. Full suite green except the same pre-existing
      `test_ctrl_b_shortcut_toggles_left_panel` flake documented since v0.9.1.

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
