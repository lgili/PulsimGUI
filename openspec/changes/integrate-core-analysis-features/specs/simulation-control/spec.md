# spec delta — simulation-control

change: integrate-core-analysis-features
base: openspec/specs/simulation-control/spec.md

---

## MODIFIED Requirements

### Requirement: AC Analysis Settings — Extended

The AC settings tab SHALL be extended with advanced frequency analysis controls.
Existing fields (start freq, stop freq, points) SHALL remain unchanged.
New fields (anchor mode, sweep scale, injection node, measurement node) SHALL
be placed inside a collapsed `QGroupBox("Advanced")`.

#### Scenario: Advanced fields collapsed by default
- **GIVEN** the user opens Simulation Settings for the first time
- **WHEN** the AC tab is shown
- **THEN** the "Advanced" group box SHALL be collapsed
- **THEN** only the existing frequency-range fields SHALL be visible

#### Scenario: Anchor mode and sweep scale persist
- **GIVEN** the user expands "Advanced" and sets anchor mode to "Averaged" and sweep scale to "Decade"
- **WHEN** the user clicks OK and reopens settings
- **THEN** the same anchor mode and sweep scale SHALL be shown

#### Scenario: AC tab disabled when capability missing
- **GIVEN** the connected backend does not have "frequency_analysis" capability
- **WHEN** the user opens the AC tab
- **THEN** a StatusBanner SHALL read "Requires backend ≥ 0.7.0"
- **THEN** all AC controls SHALL be disabled

## ADDED Requirements

### Requirement: Averaged Converter Mode

The Transient tab SHALL provide a checkable `QGroupBox("Averaged Converter Mode")`
below the existing fields. Its controls SHALL configure `TransientSettings.averaged_options`.
When unchecked (default), `averaged_options` SHALL be None (switching-mode simulation).

#### Scenario: Default off
- **GIVEN** a new project is created
- **THEN** the "Averaged Converter Mode" group box SHALL be unchecked
- **THEN** TransientSettings.averaged_options SHALL be None

#### Scenario: Enable and configure averaged mode
- **GIVEN** the user checks "Averaged Converter Mode"
- **WHEN** the user selects topology "Boost" and operating mode "CCM"
- **THEN** TransientSettings.averaged_options SHALL contain topology "boost", mode "ccm", envelope "strict"

#### Scenario: Round-trip persistence
- **GIVEN** a project is saved with averaged_options set
- **WHEN** the project is reopened
- **THEN** the dialog SHALL show the same topology, mode, and envelope values
- **THEN** the group box SHALL be checked

#### Scenario: Averaged group disabled when capability missing
- **GIVEN** the connected backend does not have "averaged" capability
- **THEN** the "Averaged Converter Mode" group box SHALL be disabled (uncheckable)
- **THEN** the tooltip SHALL read "Averaged mode requires backend ≥ 0.7.0"
