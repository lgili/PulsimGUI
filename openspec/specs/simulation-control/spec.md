# Simulation Control

## Purpose

Control interface for configuring and running simulations with real-time feedback and parameter sweeps.

## Requirements

### Requirement: Simulation Configuration Dialog

The application SHALL provide a dialog for configuring simulation parameters.

#### Scenario: Open simulation settings
- **GIVEN** a circuit is loaded
- **WHEN** the user selects Simulation > Settings or presses Ctrl+Shift+S
- **THEN** the simulation settings dialog SHALL open

#### Scenario: Transient simulation settings
- **GIVEN** the simulation settings dialog is open
- **THEN** the Transient tab SHALL include:
  - Start time (default: 0)
  - Stop time (required)
  - Maximum timestep (dt)
  - Minimum timestep (dtmin)
  - Output signals selection
  - Initial conditions option (use IC / calculate DC op point)

#### Scenario: DC analysis settings
- **GIVEN** the DC Analysis tab is selected
- **THEN** options SHALL include:
  - Enable/disable DC operating point calculation
  - Maximum Newton iterations
  - Tolerance settings

#### Scenario: AC analysis settings
- **GIVEN** the AC Analysis tab is selected
- **THEN** options SHALL include:
  - Start frequency
  - Stop frequency
  - Number of points
  - Scale (linear/logarithmic/decade)
  - Input source selection
  - Output node selection

#### Scenario: Solver settings
- **GIVEN** the Solver tab is selected
- **THEN** options SHALL include:
  - Integration method (Backward Euler, Trapezoidal, BDF2)
  - Absolute tolerance
  - Relative tolerance
  - Maximum Newton iterations
  - Damping factor
  - Adaptive timestep enable/disable
  - LTE tolerances (for adaptive)

### Requirement: Run Simulation

The application SHALL provide intuitive simulation execution controls.

#### Scenario: Start simulation via button
- **GIVEN** a valid circuit is loaded
- **WHEN** the user clicks the Run button or presses F5
- **THEN**:
  - The simulation SHALL start
  - The Run button SHALL change to a Stop button
  - The progress indicator SHALL appear

#### Scenario: Start simulation via menu
- **GIVEN** a valid circuit is loaded
- **WHEN** the user selects Simulation > Run
- **THEN** the simulation SHALL start

#### Scenario: Simulation with validation
- **GIVEN** the user attempts to run simulation
- **WHEN** the circuit has errors
- **THEN**:
  - The simulation SHALL NOT start
  - An error dialog SHALL show the validation issues
  - The problematic components SHALL be highlighted in the schematic

### Requirement: Progress Feedback

The application SHALL provide real-time feedback during simulation.

#### Scenario: Progress bar
- **GIVEN** a simulation is running
- **THEN** a progress bar SHALL show:
  - Current simulation time / total time
  - Percentage complete
  - Estimated time remaining

#### Scenario: Status text
- **GIVEN** a simulation is running
- **THEN** the status bar SHALL show:
  - "Simulating: 45.2ms / 100ms (45%)"
  - Current Newton iterations (if convergence is slow)

#### Scenario: Performance metrics
- **GIVEN** a simulation completes
- **THEN** the output panel SHALL show:
  - Total simulation wall-clock time
  - Total timesteps taken
  - Average Newton iterations per step
  - Convergence warnings (if any)

### Requirement: Stop and Pause Simulation

The application SHALL allow interrupting running simulations.

#### Scenario: Stop simulation
- **GIVEN** a simulation is running
- **WHEN** the user clicks Stop or presses Shift+F5
- **THEN**:
  - The simulation SHALL stop immediately
  - Partial results SHALL be available for viewing
  - The status SHALL indicate "Simulation stopped by user"

#### Scenario: Pause simulation
- **GIVEN** a simulation is running
- **WHEN** the user clicks Pause
- **THEN**:
  - The simulation SHALL pause at the current timestep
  - Results up to this point SHALL be viewable
  - The Pause button SHALL change to Resume

#### Scenario: Resume simulation
- **GIVEN** a simulation is paused
- **WHEN** the user clicks Resume
- **THEN** the simulation SHALL continue from where it paused

### Requirement: DC Operating Point

The application SHALL support standalone DC analysis.

#### Scenario: Run DC analysis
- **GIVEN** a circuit is loaded
- **WHEN** the user selects Simulation > DC Operating Point or presses F6
- **THEN**:
  - A DC analysis SHALL run
  - Results SHALL show node voltages and branch currents
  - Component operating points SHALL be available

#### Scenario: DC results display
- **GIVEN** DC analysis completes
- **THEN** a results panel SHALL show:
  - All node voltages in a table
  - All branch currents
  - Semiconductor operating points (Vds, Vgs, Id for MOSFETs)

#### Scenario: Show DC values on schematic
- **GIVEN** DC analysis has completed
- **WHEN** the user enables "Show DC Values"
- **THEN** node voltages and currents SHALL be displayed on the schematic

### Requirement: AC Analysis

The application SHALL support frequency-domain analysis.

#### Scenario: Run AC analysis
- **GIVEN** a circuit with an AC source is loaded
- **WHEN** the user selects Simulation > AC Analysis or presses F7
- **THEN**:
  - An AC sweep SHALL run over the specified frequency range
  - Bode plots SHALL be displayed (magnitude and phase)

#### Scenario: AC results display
- **GIVEN** AC analysis completes
- **THEN** the waveform viewer SHALL show:
  - Magnitude plot (dB vs frequency)
  - Phase plot (degrees vs frequency)
  - Gain and phase margins (if applicable)

### Requirement: Parameter Sweep

The application SHALL support sweeping parameters to analyze circuit behavior.

#### Scenario: Configure parameter sweep
- **GIVEN** the user selects Simulation > Parameter Sweep
- **THEN** a dialog SHALL allow:
  - Selecting parameter to sweep (component value)
  - Setting start value, end value, step (or number of points)
  - Choosing linear or logarithmic sweep
  - Selecting output signal to monitor
  - Enabling parallel execution

#### Scenario: Run parameter sweep
- **GIVEN** a parameter sweep is configured
- **WHEN** the user clicks Run
- **THEN**:
  - Multiple simulations SHALL run (optionally in parallel)
  - Progress SHALL show X of N sweeps complete
  - Results SHALL be collected for all sweep points

#### Scenario: Sweep results display
- **GIVEN** a parameter sweep completes
- **THEN** the results SHALL be displayable as:
  - Family of curves (waveforms for each parameter value)
  - XY plot (output vs parameter value)
  - Contour plot for 2D sweeps

### Requirement: Multiple Sweep Parameters

The application SHALL support sweeping multiple parameters.

#### Scenario: Two-parameter sweep
- **GIVEN** the sweep configuration dialog is open
- **WHEN** the user adds a second sweep parameter
- **THEN** the sweep SHALL run as a grid (N1 x N2 points)

#### Scenario: Nested vs parallel sweep
- **GIVEN** two sweep parameters are defined
- **THEN** the user SHALL be able to choose:
  - Nested sweep (full grid)
  - Parallel sweep (zip parameters together)

### Requirement: Simulation Presets

The application SHALL support saving and loading simulation configurations.

#### Scenario: Save preset
- **GIVEN** simulation parameters are configured
- **WHEN** the user clicks "Save as Preset"
- **THEN** a dialog SHALL prompt for preset name and the configuration SHALL be saved

#### Scenario: Load preset
- **GIVEN** presets exist
- **WHEN** the user opens Simulation > Presets
- **THEN** available presets SHALL be listed for selection

#### Scenario: Project-specific presets
- **GIVEN** a project is open
- **THEN** presets saved with that project SHALL be available

### Requirement: Output Signal Selection

The application SHALL allow selecting which signals to record.

#### Scenario: Signal selection dialog
- **GIVEN** simulation settings dialog is open
- **THEN** an "Outputs" tab SHALL allow:
  - Selecting node voltages to record
  - Selecting branch currents to record
  - Adding computed outputs (power, efficiency)

#### Scenario: All signals option
- **GIVEN** output selection is being configured
- **THEN** an "All Signals" option SHALL be available for recording everything

#### Scenario: Memory warning
- **GIVEN** many signals are selected with long simulation time
- **THEN** a warning SHALL show estimated memory usage

### Requirement: Convergence Assistance

The application SHALL help resolve convergence issues.

#### Scenario: Convergence failure notification
- **GIVEN** the Newton solver fails to converge
- **THEN** the application SHALL:
  - Stop simulation gracefully
  - Report the time of failure
  - Show last attempted solution
  - Suggest troubleshooting steps

#### Scenario: Auto gmin stepping
- **GIVEN** DC operating point fails to converge
- **WHEN** gmin stepping is enabled
- **THEN** the solver SHALL:
  - Try progressively smaller gmin values
  - Report if this helps convergence
  - Return to normal gmin for transient

#### Scenario: Source stepping
- **GIVEN** convergence fails
- **WHEN** source stepping is enabled
- **THEN** the solver SHALL:
  - Gradually ramp source values from zero
  - Find the DC operating point incrementally

### Requirement: Power Loss Calculation

The application SHALL calculate power losses in switching devices.

#### Scenario: Enable loss calculation
- **GIVEN** simulation settings dialog is open
- **THEN** a "Loss Calculation" option SHALL be available

#### Scenario: Loss results display
- **GIVEN** simulation with loss calculation completes
- **THEN** a loss summary SHALL show:
  - Total losses per device
  - Conduction losses
  - Switching losses (turn-on, turn-off)
  - Reverse recovery losses
  - Loss breakdown pie chart

#### Scenario: Loss waveforms
- **GIVEN** loss calculation is enabled
- **THEN** instantaneous power loss signals SHALL be available in the waveform viewer

### Requirement: Efficiency Calculation

The application SHALL calculate converter efficiency.

#### Scenario: Define power ports
- **GIVEN** the user opens Simulation > Efficiency Setup
- **THEN** the user SHALL be able to define:
  - Input power port (voltage × current)
  - Output power port (voltage × current)

#### Scenario: Efficiency display
- **GIVEN** power ports are defined and simulation completes
- **THEN** efficiency SHALL be calculated and displayed:
  - Average efficiency over simulation
  - Instantaneous efficiency waveform
  - Loss breakdown
