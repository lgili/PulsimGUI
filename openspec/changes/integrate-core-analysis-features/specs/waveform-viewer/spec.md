# spec delta — waveform-viewer

change: integrate-core-analysis-features
base: openspec/specs/waveform-viewer/spec.md

---

## ADDED Requirements

### Requirement: Post-Processing Sidebar Panel

The `WaveformViewer` SHALL provide a collapsible `PostProcessingPanel` as a
right-side panel embedded via a `QSplitter`. The panel SHALL be hidden by
default; a toolbar toggle button SHALL expand/collapse it. Panel width SHALL
be persisted in `QSettings`.

#### Scenario: Panel disabled without transient result
- **GIVEN** no transient simulation has been run
- **WHEN** the user opens the Post-Processing panel
- **THEN** the "Run Analysis" button SHALL be disabled
- **THEN** a message "Run a transient simulation first" SHALL be shown

#### Scenario: Job configuration and execution
- **GIVEN** a transient result is available
- **WHEN** the user selects signals, chooses job kind "Spectral", sets window parameters, and clicks "Run Analysis"
- **THEN** the backend's run_post_processing SHALL be called with the configured PostProcessingJob
- **THEN** a progress indicator SHALL be shown while analysis runs
- **THEN** on completion the results stack SHALL switch to the Spectral view

#### Scenario: TimeDomain results
- **GIVEN** a TimeDomain job completed successfully
- **THEN** a table SHALL list each ScalarMetric: name, value, unit, signal
- **THEN** the table SHALL be sortable by name and by value

#### Scenario: Spectral results
- **GIVEN** a Spectral job completed successfully
- **THEN** a bar chart SHALL show harmonics (frequency vs. amplitude)
- **THEN** THD% SHALL be shown as a numeric label above the chart

#### Scenario: PowerEfficiency results
- **GIVEN** a PowerEfficiency job completed successfully
- **THEN** numeric labels SHALL show P_in (W), P_out (W), efficiency (%), power factor

#### Scenario: Job failure banner
- **GIVEN** a job returns success == False
- **THEN** a StatusBanner SHALL show diagnostic_message at the top of the results area
- **THEN** the results stack SHALL NOT be shown

#### Scenario: Capability missing
- **GIVEN** the connected backend does not have "post_processing" capability
- **THEN** the Post-Processing panel toggle button SHALL be disabled
- **THEN** the tooltip SHALL read "Post-processing requires backend ≥ 0.7.0"
