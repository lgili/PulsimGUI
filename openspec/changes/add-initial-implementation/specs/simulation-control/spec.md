## ADDED Requirements

### Requirement: Simulation Configuration Dialog

The application SHALL provide a dialog for configuring simulation parameters.

#### Scenario: Open simulation settings
- **GIVEN** a circuit is loaded
- **WHEN** the user selects Simulation > Settings
- **THEN** the simulation settings dialog SHALL open with tabs for Transient, DC, AC, and Solver settings

### Requirement: Run Simulation

The application SHALL provide intuitive simulation execution controls.

#### Scenario: Start simulation via button
- **GIVEN** a valid circuit is loaded
- **WHEN** the user clicks the Run button or presses F5
- **THEN** the simulation SHALL start and progress indicator SHALL appear

### Requirement: Progress Feedback

The application SHALL provide real-time feedback during simulation.

#### Scenario: Progress bar
- **GIVEN** a simulation is running
- **THEN** a progress bar SHALL show current time, percentage, and estimated time remaining

### Requirement: Stop and Pause Simulation

The application SHALL allow interrupting running simulations.

#### Scenario: Stop simulation
- **GIVEN** a simulation is running
- **WHEN** the user clicks Stop
- **THEN** the simulation SHALL stop and partial results SHALL be available

### Requirement: DC Operating Point

The application SHALL support standalone DC analysis.

#### Scenario: Run DC analysis
- **GIVEN** a circuit is loaded
- **WHEN** the user selects DC Operating Point
- **THEN** DC analysis SHALL run and show node voltages and branch currents

### Requirement: AC Analysis

The application SHALL support frequency-domain analysis.

#### Scenario: Run AC analysis
- **GIVEN** a circuit with an AC source is loaded
- **WHEN** the user selects AC Analysis
- **THEN** Bode plots SHALL be displayed with magnitude and phase

### Requirement: Parameter Sweep

The application SHALL support sweeping parameters to analyze circuit behavior.

#### Scenario: Configure parameter sweep
- **GIVEN** the user selects Parameter Sweep
- **THEN** a dialog SHALL allow selecting parameter, range, and output signal

### Requirement: Multiple Sweep Parameters

The application SHALL support sweeping multiple parameters.

#### Scenario: Two-parameter sweep
- **GIVEN** two sweep parameters are defined
- **THEN** the sweep SHALL run as a grid (N1 x N2 points)

### Requirement: Simulation Presets

The application SHALL support saving and loading simulation configurations.

#### Scenario: Save preset
- **GIVEN** simulation parameters are configured
- **WHEN** the user clicks "Save as Preset"
- **THEN** the configuration SHALL be saved for reuse

### Requirement: Output Signal Selection

The application SHALL allow selecting which signals to record.

#### Scenario: Signal selection dialog
- **GIVEN** simulation settings dialog is open
- **THEN** an "Outputs" tab SHALL allow selecting node voltages and branch currents to record

### Requirement: Convergence Assistance

The application SHALL help resolve convergence issues.

#### Scenario: Convergence failure notification
- **GIVEN** the Newton solver fails to converge
- **THEN** the application SHALL report the time of failure and suggest troubleshooting steps

### Requirement: Power Loss Calculation

The application SHALL calculate power losses in switching devices.

#### Scenario: Enable loss calculation
- **GIVEN** simulation settings dialog is open
- **THEN** a "Loss Calculation" option SHALL be available with breakdown by device and loss type

### Requirement: Efficiency Calculation

The application SHALL calculate converter efficiency.

#### Scenario: Efficiency display
- **GIVEN** power ports are defined and simulation completes
- **THEN** efficiency SHALL be calculated as output power divided by input power
