## ADDED Requirements

### Requirement: Theme-Integrated Plot Surfaces

The waveform viewer SHALL apply active theme tokens to plot surfaces and surrounding controls.

#### Scenario: Runtime theme update for waveform viewer
- **GIVEN** waveform data is visible
- **WHEN** the user switches theme
- **THEN** plot background, axes, legend, grid, control bar, and measurement panel SHALL update in-place
- **AND** existing traces SHALL remain visible and readable

#### Scenario: Theme-coherent measurement panel
- **GIVEN** cursor and statistics readouts are visible
- **WHEN** theme changes
- **THEN** readout cards, labels, separators, and emphasis colors SHALL follow waveform theme tokens

### Requirement: Accessible Trace and Cursor Palette

The waveform viewer SHALL provide theme-specific trace and cursor palettes that remain distinguishable and readable.

#### Scenario: Multi-signal readability
- **GIVEN** five or more traces are visible
- **WHEN** rendered in light or dark mode
- **THEN** traces SHALL remain visually distinguishable without relying on a single hue family

#### Scenario: Cursor/readout contrast
- **GIVEN** measurement cursors are enabled
- **WHEN** displayed over active plot background
- **THEN** cursor lines and corresponding readouts SHALL maintain sufficient visual contrast for reliable measurement use
