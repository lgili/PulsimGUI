## ADDED Requirements

### Requirement: Theme-Integrated Thermal Visualization

The thermal viewer SHALL apply active theme tokens across its plot, table, and caption surfaces.

#### Scenario: Runtime theme update for thermal viewer
- **GIVEN** thermal results are displayed
- **WHEN** the user changes theme
- **THEN** temperature plot, loss plot, table surfaces, and textual captions SHALL update in-place without requiring dialog reopen

#### Scenario: Consistent table/plot legibility
- **GIVEN** thermal viewer is shown in any built-in theme
- **THEN** headers, row text, grid lines, and chart axes SHALL remain legible and visually coherent with the rest of the shell

### Requirement: Thermal Palette Consistency with Analysis Views

Thermal traces and loss colors SHALL follow a palette strategy compatible with waveform viewer semantics.

#### Scenario: Cross-view color behavior
- **GIVEN** user alternates between waveform and thermal analysis views
- **WHEN** comparing multiple series
- **THEN** both views SHALL use harmonized palette rules for distinguishability and emphasis

#### Scenario: Loss breakdown readability
- **GIVEN** conduction and switching bars are shown together
- **WHEN** any built-in theme is active
- **THEN** stacked/adjacent categories SHALL remain clearly separable and readable in legends
