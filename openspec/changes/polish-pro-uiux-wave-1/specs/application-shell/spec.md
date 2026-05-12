## ADDED Requirements

### Requirement: Backend Version Visibility
The application SHALL display the active Pulsim backend version in the status bar at all times.

#### Scenario: Backend version surfaced after install
- **GIVEN** the user has Pulsim installed (any importable version)
- **WHEN** the application launches
- **THEN** the status bar's backend segment SHALL render `Pulsim <version>` where `<version>` is the value of `pulsim.__version__`

#### Scenario: Backend missing — graceful fallback
- **GIVEN** Pulsim is not importable from the current Python environment
- **WHEN** the application launches
- **THEN** the status bar's backend segment SHALL render `Pulsim unknown` rather than a hardcoded version literal

### Requirement: Solver Pill
The status bar SHALL contain a clickable solver pill widget that shows the current integrator, timestep, and linear solver, color-coded by last-run convergence health.

#### Scenario: Idle state
- **GIVEN** no simulation has run since the application launched
- **WHEN** the user looks at the status bar
- **THEN** the pill SHALL render the configured integrator, dt, and linear solver in a neutral (gray) state

#### Scenario: Success state
- **GIVEN** the most recent simulation completed without retries or fallbacks
- **THEN** the pill background SHALL be tinted green

#### Scenario: Recovered state
- **GIVEN** the most recent simulation completed but with retries / fallbacks
- **THEN** the pill background SHALL be tinted amber

#### Scenario: Failed state
- **GIVEN** the most recent simulation did not converge
- **THEN** the pill background SHALL be tinted red

#### Scenario: Click opens settings
- **GIVEN** the pill is visible
- **WHEN** the user clicks it
- **THEN** the application SHALL open the Simulation Settings dialog focused on the Solver tab

### Requirement: Run Bar
The application SHALL provide a horizontal Run Bar above the status bar that contains the primary simulation controls and live progress.

#### Scenario: Idle state visibility
- **GIVEN** no simulation is running
- **THEN** the Run Bar SHALL be visible with Run / Pause / Stop buttons enabled / disabled appropriately, and no progress

#### Scenario: Running state
- **GIVEN** a simulation has started
- **WHEN** the runtime publishes progress
- **THEN** the Run Bar progress segment SHALL update at ≥ 10 Hz, the elapsed-time readout SHALL update each tick, and the realtime factor SHALL show `(t_sim_elapsed / t_wall_elapsed)×`

#### Scenario: Completed state
- **GIVEN** a simulation finished successfully
- **THEN** the progress segment SHALL show 100 % and the elapsed-time readout SHALL persist until the user starts a new run or presses Stop

## MODIFIED Requirements

### Requirement: Status Bar Layout
The status bar SHALL be segmented into discrete sections with one piece of information per segment.

The required segments are: coordinate readout, selection count, simulation state indicator, solver pill, backend version. Each segment SHALL have a visible left-border separator and consistent vertical padding.

#### Scenario: Five-segment layout
- **GIVEN** the application is running
- **THEN** the status bar SHALL render exactly five segments in left-to-right order: coordinates, selection count, simulation state, solver pill, backend version

### Requirement: Toolbar History Controls
The toolbar SHALL expose exactly one undo control and one redo control.

#### Scenario: No duplicates
- **GIVEN** the main toolbar is visible
- **WHEN** the user counts undo / redo buttons
- **THEN** there SHALL be exactly one undo and exactly one redo button

#### Scenario: Standard placement
- **GIVEN** the toolbar shows file actions (new / open / save)
- **THEN** the undo / redo cluster SHALL appear immediately after the file actions and before the zoom cluster
