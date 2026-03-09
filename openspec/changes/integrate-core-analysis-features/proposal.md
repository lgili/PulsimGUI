## Why

PulsimCore v0.7.0 shipped three new backend-owned analysis capabilities:

1. **Waveform post-processing** (`run_post_processing`) — canonical TimeDomain,
   Spectral (FFT/THD/harmonics) and PowerEfficiency metric pipeline.
2. **Frequency-domain AC sweep** (`run_frequency_analysis`) — Bode plots,
   stability margins, impedance sweeps with anchor modes (DC/periodic/averaged/auto).
3. **Averaged converter modeling** (`AveragedConverterOptions`) — faster transient
   simulations using CCM averaged models for plant/loop design iteration.

The GUI currently:
- Has no entry point for post-processing; users must write ad-hoc Python scripts.
- Has a stub Bode plot dialog (`BodePlotDialog`) that is disconnected from the new
  `run_frequency_analysis` API (it consumed the legacy `ACResult` synthetic dict).
- Has no averaged-mode toggle or topology selector in the simulation settings.
- Does not feature-detect the new capabilities and cannot degrade gracefully.

This change closes all three gaps with a minimal, well-scoped integration.

## What Changes

### 1. Backend types and adapter
- Add `PostProcessingResult`, `FrequencyAnalysisResult` GUI wrapper types to
  `backend_types.py` (thin mirrors of pulsim structs with `is_valid` helpers).
- Extend `SimulationBackend` protocol with:
  - `run_post_processing(transient_result, options)` → `PostProcessingResult`
  - `run_frequency_analysis(circuit_data, options)` → `FrequencyAnalysisResult`
- Implement both in `PulsimBackend` (calling `ps.run_post_processing` /
  `ps.run_frequency_analysis`).
- Add `PlaceholderBackend` stub implementations (return synthetic demo data).
- Add `"post_processing"` and `"frequency_analysis"` to the capability set.
- Add `averaged_options: AveragedConverterOptions | None` field to
  `TransientSettings`.
- Bump `_SIMULATION_OPTIONS_MIN_BACKEND` to `BackendVersion(0, 7, 0)`.

### 2. Post-processing service layer
- Add `post_processing_service.py` wrapping `SimulationBackend.run_post_processing`.
- Exposes `run_jobs(result, jobs)` → `PostProcessingResult` (thread-safe, runs in
  worker thread, emits Qt signals on completion/error).

### 3. Post-processing panel in waveform viewer
- Add `PostProcessingPanel` widget inside `views/waveform/`:
  - Signal selector (checkboxes from current `TransientResult`).
  - Job kind selector: TimeDomain / Spectral / PowerEfficiency.
  - Window mode selector: Time / Index / Cycle (with parameter fields).
  - "Run Analysis" button → calls service, renders results.
  - Results section: metrics table (TimeDomain), spectrum + harmonics plot (Spectral),
    efficiency numbers (PowerEfficiency).
  - Diagnostic banner when any job fails or produces undefined metrics.
- Panel is shown as a collapsible sidebar tab inside the existing
  `WaveformViewer` widget (does not require a new window).

### 4. Frequency analysis dialog (Bode plot)
- Refactor `BodePlotDialog` to consume `FrequencyAnalysisResult` directly from
  `run_frequency_analysis`.
- Add `FrequencyAnalysisOptions` form inside `SimulationSettingsDialog` (AC tab):
  - Anchor mode (Auto / DC / Periodic / Averaged).
  - Sweep scale (Log / Decade / Linear).
  - Start / stop frequency, points per decade.
  - Port definition (injection node, measurement node).
- `BodePlotDialog` now shows:
  - Magnitude (dB) and phase (°) vs frequency (existing layout preserved).
  - Stability margins panel (gain margin, phase margin, crossover frequencies)
    sourced directly from `FrequencyAnalysisResult` — no GUI-side calculation.
  - Diagnostic badge when analysis failed (reason code + message).

### 5. Averaged mode in simulation settings
- Add "Averaged Converter" checkbox + topology dropdown to the Transient tab of
  `SimulationSettingsDialog`:
  - Enabled only when backend has `"averaged"` capability.
  - Topology: Buck / Boost / BuckBoost / Flyback / Forward (enum).
  - Operating mode: CCM / Auto.
  - Envelope policy: Strict / Lenient / Ignore.
- When enabled, `TransientSettings.averaged_options` is populated and forwarded
  through `PulsimBackend.run_transient` → pulsim `SimulationOptions`.

### 6. Capability detection and graceful degradation
- `BackendInfo.check_compatibility()` adds `"post_processing"`,
  `"frequency_analysis"`, and `"averaged"` to `unavailable_features` when the
  backend version is < 0.7.0.
- UI elements for each feature are disabled (greyed out) when capability is missing.
- A user-visible tooltip explains the minimum backend version required.

## Non-Goals
- GUI-side metric calculation (all metrics come from the backend pipeline).
- New waveform viewer layout or scope panel restructuring.
- Controller auto-design UI (covered by a future change).
- Parametric sweep / Monte Carlo UI.

## Implementation Gates (Definition of Done)
- G1: `run_post_processing` and `run_frequency_analysis` are callable from GUI
  with a real backend (pulsim ≥ 0.7.0) and return structured results.
- G2: Post-processing panel renders TimeDomain metrics table, Spectral
  (bins + harmonics chart), and PowerEfficiency numbers without UI-side math.
- G3: `BodePlotDialog` consumes `FrequencyAnalysisResult`; stability margins are
  backend-sourced.
- G4: Averaged mode toggle persists in project settings and is forwarded to the
  transient backend call.
- G5: All three features degrade gracefully when backend < 0.7.0.
- G6: Placeholder backend provides synthetic demo data for all three features.
- G7: Tests cover service layer, type wrappers, and dialog construction.

## Impact

### Affected GUI specs
- `simulation-control` — MODIFIED: AC tab options, Transient averaged toggle
- `waveform-viewer` — MODIFIED: post-processing sidebar panel
- `frequency-analysis` — NEW: Bode plot and stability margins capability

### Affected code
- `src/pulsimgui/services/backend_types.py`
- `src/pulsimgui/services/backend_adapter.py`
- `src/pulsimgui/services/simulation_service.py`
- `src/pulsimgui/services/post_processing_service.py` (NEW)
- `src/pulsimgui/views/waveform/waveform_viewer.py`
- `src/pulsimgui/views/waveform/post_processing_panel.py` (NEW)
- `src/pulsimgui/views/dialogs/bode_plot_dialog.py`
- `src/pulsimgui/views/dialogs/simulation_settings_dialog.py`
- `tests/test_post_processing_service.py` (NEW)
- `tests/test_frequency_analysis.py` (NEW)
- `tests/test_averaged_settings.py` (NEW)

## Risks and Mitigations
- Risk: pulsim backend < 0.7.0 installed → UI broken.
  - Mitigation: capability gates + graceful degradation.
- Risk: `FrequencyAnalysisResult` field names differ from current `ACResult`.
  - Mitigation: `FrequencyAnalysisResult` wrapper in `backend_types.py` normalises
    the surface; `BodePlotDialog` updated once.
- Risk: Post-processing panel adds layout complexity to waveform viewer.
  - Mitigation: collapsible tab, no structural changes to existing plot areas.
