# Simulation Control - Delta Specifications

## MODIFIED Requirements

### Requirement: DC Operating Point

The application SHALL support standalone DC analysis using the real simulation backend.

#### Scenario: Run DC analysis with real backend
- **GIVEN** PulsimCore backend is available with DC capability
- **WHEN** the user selects Simulation > DC Operating Point or presses F6
- **THEN** the backend's `run_dc()` method SHALL be called
- **AND** real node voltages and branch currents SHALL be displayed

#### Scenario: DC analysis with placeholder fallback
- **GIVEN** PulsimCore backend is unavailable or lacks DC capability
- **WHEN** the user attempts DC analysis
- **THEN** a warning SHALL be shown indicating demo mode
- **AND** placeholder results MAY be displayed

#### Scenario: DC convergence failure
- **GIVEN** DC analysis fails to converge
- **WHEN** the solver reports failure
- **THEN** the error dialog SHALL include a "Show Diagnostics" button
- **AND** clicking the button SHALL open the Convergence Diagnostics dialog

#### Scenario: DC strategy selection
- **GIVEN** the Solver settings tab is open
- **WHEN** the user selects a DC strategy
- **THEN** the strategy SHALL be passed to the backend
- **AND** options include: Auto, Direct, GMIN Stepping, Source Stepping, Pseudo-Transient

### Requirement: AC Analysis

The application SHALL support frequency-domain analysis using the real simulation backend.

#### Scenario: Run AC analysis with real backend
- **GIVEN** PulsimCore backend is available with AC capability
- **WHEN** the user selects Simulation > AC Analysis or presses F7
- **THEN** the backend's `run_ac()` method SHALL be called
- **AND** real Bode plot data SHALL be displayed

#### Scenario: AC analysis with placeholder fallback
- **GIVEN** PulsimCore backend lacks AC capability
- **WHEN** the user attempts AC analysis
- **THEN** a warning SHALL be shown
- **AND** the AC menu item SHALL be disabled with tooltip explaining why

### Requirement: Simulation Configuration Dialog

The application SHALL provide a dialog for configuring simulation parameters including solver options.

#### Scenario: Solver settings tab
- **GIVEN** the simulation settings dialog is open
- **THEN** the Solver tab SHALL include:
  - Integration method dropdown (Backward Euler, Trapezoidal, BDF2)
  - Maximum Newton iterations spinbox (default: 50)
  - Voltage limiting checkbox (default: enabled)
  - Maximum voltage step field (default: 5.0V)
  - Absolute tolerance field (default: 1e-6)
  - Relative tolerance field (default: 1e-4)

#### Scenario: DC strategy settings
- **GIVEN** the Solver tab is selected
- **THEN** a DC Strategy section SHALL include:
  - Strategy dropdown (Auto, Direct, GMIN Stepping, Source Stepping, Pseudo-Transient)
  - GMIN initial value field (visible when GMIN selected)
  - GMIN final value field (visible when GMIN selected)

#### Scenario: Settings persistence
- **GIVEN** solver settings have been modified
- **WHEN** the user clicks OK
- **THEN** settings SHALL be saved to the project file
- **AND** settings SHALL be restored when the dialog is reopened

### Requirement: Convergence Assistance

The application SHALL help resolve convergence issues with detailed diagnostics.

#### Scenario: Convergence diagnostics dialog
- **GIVEN** a simulation has failed to converge
- **WHEN** the user clicks "Show Diagnostics"
- **THEN** a dialog SHALL display:
  - Summary of convergence status
  - Iteration history plot (residual vs iteration)
  - List of problematic nodes that didn't converge
  - Suggested fixes based on failure mode

#### Scenario: Automatic suggestions
- **GIVEN** the convergence diagnostics dialog is open
- **THEN** the Suggestions panel SHALL show context-aware advice:
  - "Increase max iterations" if near iteration limit
  - "Enable voltage limiting" if divergence detected
  - "Check for floating nodes" if singular matrix
  - "Try GMIN stepping" if DC analysis failed

## ADDED Requirements

### Requirement: Backend Capability Awareness

The application SHALL adapt its UI based on available backend capabilities.

#### Scenario: Feature detection on startup
- **GIVEN** the application starts
- **WHEN** the backend is loaded
- **THEN** the application SHALL detect available capabilities (dc, ac, thermal, transient)
- **AND** menu items for unavailable features SHALL be disabled

#### Scenario: Capability tooltip
- **GIVEN** a menu item is disabled due to missing capability
- **WHEN** the user hovers over it
- **THEN** a tooltip SHALL explain why and how to enable it

#### Scenario: Backend upgrade prompt
- **GIVEN** the backend version is below minimum required
- **WHEN** the user opens simulation settings
- **THEN** a warning banner SHALL appear with upgrade instructions
