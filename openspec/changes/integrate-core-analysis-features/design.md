# Design Document — integrate-core-analysis-features

## Scope

This document records all significant design decisions for the GUI
integration of the three new PulsimCore features:
- Post-processing tools (`run_post_processing`)
- Frequency-domain AC sweep analysis (`run_frequency_analysis`)
- Averaged converter modelling (`AveragedConverterOptions`)

---

## 1. Backend abstraction strategy

### 1.1 Type wrappers instead of direct pulsim imports in the view layer

**Decision:** `backend_types.py` defines GUI-owned dataclasses that mirror
the pulsim structs. The view layer **never** imports from `pulsim` directly.

**Rationale:**
- Keeps the `PlaceholderBackend` fully functional without pulsim installed.
- Isolates breakage when pulsim changes internal types.
- Existing `TransientResult`, `ACResult`, etc. follow the same pattern.

**Consequences:**
- Two mapping functions needed in `backend_adapter.py`:
  `_map_pp_result(pulsim_result) → PostProcessingResult`
  `_map_fa_result(pulsim_result) → FrequencyAnalysisResult`

### 1.2 Capability-gated Protocol extension

`run_post_processing` and `run_frequency_analysis` are added to the
`SimulationBackend` Protocol.  Both implementations (`PulsimBackend`,
`PlaceholderBackend`) must satisfy the Protocol.

`has_capability(name)` is the single gating mechanism for enabling/disabling
UI controls. New capability strings: `"post_processing"`, `"frequency_analysis"`,
`"averaged"`.

### 1.3 Averaged options as passthrough dict

`TransientSettings.averaged_options: dict | None = None`

Stored as a plain dict `{"topology": "buck", "mode": "auto", "envelope": "strict"}`
for JSON round-trip compatibility.  `PulsimBackend.run_transient` converts this
to `ps.AveragedConverterOptions` at call time.  A `None` value means "use switching
mode" (existing default unchanged).

---

## 2. Post-processing data flow

```
WaveformViewer
  └─ PostProcessingPanel (QWidget, collapsible sidebar)
       ├─ job_form → builds PostProcessingJob list
       ├─ "Run Analysis" button
       │    └─ PostProcessingService.run_jobs(transient_result, jobs)
       │         └─ QThreadPool worker → backend.run_post_processing()
       │              └─ PulsimBackend → ps.run_post_processing()
       └─ _on_result(PostProcessingResult) → shows results stack
```

`PostProcessingService` is constructed once and held by `SimulationService`
(same pattern as `SimulationWorker`).  It **does not** re-run transient; it
only processes an existing result.

### 2.1 Results rendering

| Job kind          | Widget                                         |
|-------------------|------------------------------------------------|
| `TimeDomain`      | `QTableWidget`: metric / value / unit / signal |
| `Spectral`        | pyqtgraph bar chart (harmonics) + THD label    |
| `PowerEfficiency` | Fixed-form numeric labels: P_in, P_out, η%, PF |

A single `StatusBanner` at the top of the results area shows `diagnostic_message`
when `PostProcessingJobResult.success == False`.

### 2.2 Panel placement

`PostProcessingPanel` is added as a right-side collapsible panel in
`WaveformViewer` using a `QSplitter`.  A toggle button (≡) in the toolbar
expands/collapses it.  The existing plot area width is not changed when the
panel is hidden (splitter sizes stored in `QSettings`).

---

## 3. Frequency analysis data flow

```
SimulationSettingsDialog (AC tab, extended)
  └─ FrequencyAnalysisOptions (anchor, scale, ports, freq range)
       └─ saved in SimulationSettings.ac_options

MainWindow "Run AC" action
  └─ SimulationService.run_frequency_analysis(circuit, ac_options)
       └─ PulsimBackend.run_frequency_analysis()
            └─ ps.run_frequency_analysis(circuit, fa_options)
                 └─ FrequencyAnalysisResult (GUI wrapper)

BodePlotDialog.show(result: FrequencyAnalysisResult)
```

### 3.1 Legacy ACResult migration

`ACResult` is kept for now.  `BodePlotDialog` accepts `FrequencyAnalysisResult`
as primary type; if a legacy `ACResult` is passed, an automatic shim converts it:

```python
def _compat_from_ac_result(r: ACResult) -> FrequencyAnalysisResult:
    # wrap dicts; margins = None; success = True; diagnostic_code = ""
```

This shim is private to `BodePlotDialog` and will be removed when all callers
migrate.

### 3.2 Stability margin display

Stability margins (gain margin, phase margin, crossover frequencies) are
displayed as read-only `QLabel`s inside a collapsible `QGroupBox` titled
"Stability Margins".  Values come directly from `FrequencyAnalysisResult`
fields — **no GUI-side calculation**.  When `result.success == False`, the
group box shows the diagnostic message and crossover labels read "N/A".

---

## 4. Simulation settings dialog changes

### 4.1 AC tab

New fields added below the existing frequency range:

| Field             | Widget           | Maps to                              |
|-------------------|------------------|--------------------------------------|
| Anchor mode       | `QComboBox`      | `FrequencyAnalysisMode`              |
| Sweep scale       | `QComboBox`      | `FrequencySweepScale`                |
| Injection node    | `QLineEdit`      | `FrequencyAnalysisPort.injection`    |
| Measurement node  | `QLineEdit`      | `FrequencyAnalysisPort.measurement`  |

All new controls are wrapped in a `QGroupBox("Advanced")` collapsed by default.
When `"frequency_analysis"` capability is missing, the entire tab shows a
`StatusBanner("Feature not available — backend ≥ 0.7.0 required")` and all
controls are disabled.

### 4.2 Transient tab — averaged group box

`QGroupBox("Averaged Converter Mode", checkable=True)` is added below the
existing Transient fields.  Default: unchecked (switching mode).

Fields exposed:
- Topology: `QComboBox` (Buck / Boost / BuckBoost / Flyback / Forward)
- Operating mode: `QComboBox` (CCM / Auto)
- Envelope policy: `QComboBox` (Strict / Lenient / Ignore)

When unchecked, `TransientSettings.averaged_options = None`.
When capability `"averaged"` is missing, group box is disabled with tooltip
"Requires backend ≥ 0.7.0".

---

## 5. What is NOT changing

- Existing `run_ac()` / `run_transient()` / `run_dc()` / `run_thermal()` call
  paths and return types are preserved.
- `WaveformViewer` plot area layout (pyqtgraph `PlotWidget` arrangement)
  is unchanged.
- `PlaceholderBackend.run_transient()` returning synthetic waveforms is
  unchanged.
- Project file format is backward-compatible: `averaged_options: null`
  is the default for all existing projects.
