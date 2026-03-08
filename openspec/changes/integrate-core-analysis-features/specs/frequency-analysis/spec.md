# spec — frequency-analysis (new capability)

change: integrate-core-analysis-features

---

## Purpose

Display frequency-domain analysis results (Bode plots, stability margins) produced
by the backend's `run_frequency_analysis` API. This replaces the legacy AC analysis
path that computed Bode plots from node-voltage sweeps via `run_ac`.

---

## ADDED Requirements

### Requirement: Bode Plot Display

`BodePlotDialog` SHALL accept `FrequencyAnalysisResult` from `backend_types`.
Magnitude and phase SHALL be plotted on stacked pyqtgraph `PlotWidget`s sharing
a logarithmic frequency axis. Grid lines SHALL appear at -180° and 0 dB.

#### Scenario: Basic Bode plot render
- **GIVEN** a FrequencyAnalysisResult with success == True
- **WHEN** BodePlotDialog is opened
- **THEN** two aligned plots SHALL render magnitude and phase vs. frequency
- **THEN** the frequency axis SHALL be logarithmic
- **THEN** grid lines SHALL appear at -180° and 0 dB

#### Scenario: Multi-signal result
- **GIVEN** a FrequencyAnalysisResult with multiple transfer functions
- **THEN** each transfer function SHALL be shown as a separate coloured curve
- **THEN** a legend with signal names SHALL be shown

#### Scenario: Legacy ACResult compatibility
- **GIVEN** a legacy ACResult is passed to BodePlotDialog
- **THEN** the shim SHALL convert it to a FrequencyAnalysisResult
- **THEN** the dialog SHALL render correctly
- **THEN** no stability margins SHALL be shown (shim sets them to None)

### Requirement: Stability Margins

A collapsible `QGroupBox("Stability Margins")` SHALL be shown below the plots.
It SHALL display gain margin (dB), phase margin (°), gain crossover frequency
(Hz), and phase crossover frequency (Hz). Values SHALL come directly from
`FrequencyAnalysisResult` fields — no GUI-side calculation is permitted.
Margin lines SHALL be drawn on the plots at crossover frequencies.

#### Scenario: Margins available
- **GIVEN** FrequencyAnalysisResult has non-None gain_margin_db and phase_margin_deg
- **THEN** the stability margins group box SHALL show all four values
- **THEN** vertical lines SHALL mark crossover frequencies on both subplots

#### Scenario: Margins not available
- **GIVEN** FrequencyAnalysisResult.gain_margin_db is None
- **THEN** the affected label SHALL show "N/A"
- **THEN** no crossover line SHALL be drawn for that margin

### Requirement: Failure Diagnostics

When frequency analysis fails, the dialog SHALL show a diagnostic banner instead
of (or above) the plots.

#### Scenario: Analysis failed
- **GIVEN** FrequencyAnalysisResult.success == False
- **WHEN** BodePlotDialog is opened
- **THEN** a StatusBanner SHALL show diagnostic_code and diagnostic_message
- **THEN** plot widgets SHALL be hidden
- **THEN** the dialog title SHALL include "[Analysis Failed]"

#### Scenario: Partial failure with NaN points
- **GIVEN** FrequencyAnalysisResult.success == True but some data points are NaN
- **THEN** the Bode plot SHALL render available points
- **THEN** a warning banner SHALL indicate "Some frequency points could not be computed"
