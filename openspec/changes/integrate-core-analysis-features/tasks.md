## 1. Backend types (`backend_types.py`)
- [x] 1.1 Add `PostProcessingJobResult` dataclass mirroring pulsim fields:
      `job_id`, `kind`, `success`, `diagnostic`, `diagnostic_message`,
      `scalar_metrics` (dict[str, ScalarMetric]), `spectrum_bins`, `harmonics`,
      `undefined_metrics`, `thd_pct`, `fundamental_hz`, `average_input_power`,
      `average_output_power`, `efficiency`, `power_factor`, `signal_names`.
- [x] 1.2 Add `PostProcessingResult` dataclass: `jobs: list[PostProcessingJobResult]`,
      `success: bool`, `error_message: str`, and compatibility `is_valid` property.
- [x] 1.3 Add `FrequencyAnalysisResult` dataclass: `frequencies`, `magnitude_db`,
      `phase_deg` (dicts by signal/transfer-function key), `gain_margin_db`,
      `phase_margin_deg`, `gain_crossover_hz`, `phase_crossover_hz`, `success`,
      `diagnostic_code`, `diagnostic_message`, `is_valid`.
- [x] 1.4 Add `averaged_options: dict | None` field to `TransientSettings`
      (serialisable; holds topology, mode, envelope policy strings).
- [x] 1.5 Bump `MIN_BACKEND_API` to `BackendVersion(0, 7, 0)`.

## 2. Backend adapter (`backend_adapter.py`)
- [x] 2.1 Add `run_post_processing(transient_result, options)` to `SimulationBackend`
      Protocol.
- [x] 2.2 Add `run_frequency_analysis(circuit_data, fa_options)` to Protocol.
- [x] 2.3 Implement `PulsimBackend.run_post_processing`:
      - Build `ps.SimulationResult` from `TransientResult`.
      - Call `ps.run_post_processing(sr, options)`.
      - Map result to `PostProcessingResult` wrapper.
- [x] 2.4 Implement `PulsimBackend.run_frequency_analysis`:
      - Build pulsim `Circuit` (reuse `CircuitConverter`).
      - Call `ps.run_frequency_analysis(circuit, fa_options)`.
      - Use native field names (`f_start_hz`, `f_stop_hz`, `points`, `perturbation_port`, `output_port`).
      - Map `FrequencyAnalysisResult` from pulsim result (`frequency_hz`, diagnostics, margins/reasons).
- [x] 2.5 Add `averaged` support in `PulsimBackend.run_transient`:
      - If `settings.averaged_options` is set, populate the pulsim
        `SimulationOptions.averaged_converter` field accordingly.
- [x] 2.6 Implement `PlaceholderBackend.run_post_processing` (synthetic scalar
      metrics and a 3-harmonic spectrum).
- [x] 2.7 Implement `PlaceholderBackend.run_frequency_analysis` (synthetic low-pass
      Bode data with gain/phase margins).
- [x] 2.8 Add `"post_processing"`, `"frequency_analysis"`, `"averaged"` to
      `all_features` set in `BackendInfo.check_compatibility`.
- [x] 2.9 Feature-detect capabilities in `PulsimBackend`: use `hasattr(ps, 'run_post_processing')` etc.

## 3. Post-processing service (`post_processing_service.py`)
- [x] 3.1 Create `PostProcessingService(QObject)` with:
      - `run_jobs(transient_result, jobs: list[PostProcessingJob])` method.
      - Runs in `QThreadPool` worker.
      - Emits `analysis_completed(PostProcessingResult)` and `analysis_failed(str)`.
- [x] 3.2 Wire `PostProcessingService` into `SimulationService` (same lifecycle).

## 4. Simulation settings dialog (`simulation_settings_dialog.py`)
- [x] 4.1 **AC tab overhaul**: replace legacy `ACSettings` form with new fields:
      - Anchor mode combo: Auto / DC / Periodic / Averaged.
      - Sweep scale combo: Decade / Log / Linear.
      - Start freq, stop freq, points per decade (existing fields preserved).
      - Injection node + measurement node line edits.
      - Greyed-out with tooltip when `"frequency_analysis"` capability missing.
- [x] 4.2 **Transient tab**: add collapsible "Averaged Converter" group box:
      - Enable checkbox (disabled when capability missing).
      - Topology combo: Buck / Boost / BuckBoost / Flyback / Forward.
      - Operating mode combo: CCM / Auto.
      - Envelope policy combo: Strict / Lenient / Ignore.
      - On change → updates `SimulationSettings.averaged_options`.

## 5. Post-processing panel (`views/waveform/post_processing_panel.py`)
- [ ] 5.1 Create `PostProcessingPanel(QWidget)`:
      - Signal checklist populated from `TransientResult.signals` keys.
      - Job kind combo: TimeDomain / Spectral / PowerEfficiency.
      - Window group: mode (Time/Index/Cycle) + parameter fields that
        show/hide based on selected mode.
      - Optional: fundamental_hz line edit (for Spectral jobs).
      - "Run Analysis" button → disabled unless transient result available.
      - Results stack (one page per job kind):
        - TimeDomain: `QTableWidget` of metric name / value / unit.
        - Spectral: `pyqtgraph` bar chart of harmonics + THD label +
          bins scatter plot.
        - PowerEfficiency: numeric labels for P_in, P_out, η, PF.
      - Diagnostic banner (`StatusBanner`) when `PostProcessingJobResult.success == False`.
- [ ] 5.2 Embed `PostProcessingPanel` as a collapsible sidebar in
      `WaveformViewer` (add `QSplitter` + toggle button; does not change existing
      plot area layout).
- [ ] 5.3 Connect `PostProcessingService.analysis_completed` →
      `PostProcessingPanel._on_result`.

## 6. Bode plot dialog (`bode_plot_dialog.py`)
- [x] 6.1 Update `BodePlotDialog.__init__` to accept `FrequencyAnalysisResult`
      (from `backend_types`), keep `ACResult` as a deprecated fallback with
      automatic conversion.
- [x] 6.2 Populate magnitude/phase plots from `FrequencyAnalysisResult.magnitude_db`
      and `.phase_deg` (existing pyqtgraph layout preserved).
- [x] 6.3 Add stability margins panel: gain margin (dB), phase margin (°),
      crossover frequencies — values read directly from `FrequencyAnalysisResult`
      fields (no GUI-side calculation).
- [x] 6.4 Show diagnostic badge when `result.success == False` (reason code +
      message from `FrequencyAnalysisResult.diagnostic_message`).

## 7. Tests
- [x] 7.1 `tests/test_post_processing_service.py`:
      - Service emits `analysis_completed` for valid transient result + jobs.
      - Service emits `analysis_failed` for missing backend capability.
      - PlaceholderBackend returns `is_valid == True` result.
- [x] 7.2 `tests/test_frequency_analysis.py`:
      - `FrequencyAnalysisResult` wrapper has correct `is_valid` logic.
      - `BodePlotDialog` constructs without error from both `FrequencyAnalysisResult`
        and legacy `ACResult`.
      - Stability margin fields populated from result (not calculated).
- [x] 7.3 `tests/test_averaged_settings.py`:
      - `TransientSettings.averaged_options` round-trips through project save/load.
      - Averaged group box is disabled when backend lacks `"averaged"` capability.
      - `PulsimBackend.run_transient` passes `averaged_options` when set.

## 8. Quality gates
- [ ] 8.1 All new tests pass under `QT_QPA_PLATFORM=offscreen pytest tests/`.
- [ ] 8.2 No regressions in existing transient / DC / thermal tests.
- [ ] 8.3 `openspec validate integrate-core-analysis-features --strict` passes.
