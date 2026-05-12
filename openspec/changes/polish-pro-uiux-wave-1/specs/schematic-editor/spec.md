## ADDED Requirements

### Requirement: Auto-fit on Project Open
When the user opens a project file, the schematic view SHALL animate to fit the loaded content.

#### Scenario: First open
- **GIVEN** the canvas is empty and the user opens `.pulsim` file with at least one component
- **WHEN** the parsed circuit is loaded into the scene
- **THEN** the view SHALL animate (≤ 300 ms ease-out) to a fit-to-content zoom level where every component is fully visible with 5 % padding on each side

#### Scenario: Reopening into a non-empty view
- **GIVEN** the user already has a circuit open and opens another file (replacing the current scene)
- **THEN** the auto-fit animation SHALL still play after the new content loads

### Requirement: Inline Diagnostics Overlay
Components that fail YAML emission validation SHALL render with a visible diagnostic badge so the user can locate and fix errors without leaving the schematic.

#### Scenario: Badge appears on validation failure
- **GIVEN** a `pi_controller` component is missing its required `kp` parameter
- **WHEN** the runtime validation runs
- **THEN** the component item SHALL render a small red badge with a "!" glyph in its top-right corner

#### Scenario: Tooltip describes the problem
- **GIVEN** a diagnostic badge is visible on a component
- **WHEN** the user hovers the badge
- **THEN** a tooltip SHALL show the human-readable validation error message

#### Scenario: Click jumps to the offending field
- **GIVEN** a diagnostic badge is visible on a component
- **WHEN** the user clicks the badge
- **THEN** the application SHALL focus the properties panel on the failing parameter field with a red outline around it

#### Scenario: Badge clears on fix
- **GIVEN** the user has fixed the failing parameter
- **WHEN** validation re-runs
- **THEN** the badge SHALL disappear

### Requirement: Stale-Component Indicator
Components whose parameters have changed since the last successful simulation run SHALL display a stale indicator so the user knows the current waveforms no longer reflect the schematic.

#### Scenario: Indicator appears after edit
- **GIVEN** a simulation has run successfully and the user edits a component parameter
- **WHEN** the parameter change is committed
- **THEN** the edited component SHALL display a small amber dot in the bottom-right corner of its bounding rect

#### Scenario: Indicator clears after re-run
- **GIVEN** stale indicators are visible
- **WHEN** the user runs the simulation again and it completes successfully
- **THEN** every stale indicator SHALL be cleared
