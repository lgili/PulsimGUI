# Simulation Control

## Purpose

Control interface for configuring and running simulations with real-time feedback and parameter sweeps.
## Requirements
### Requirement: Simulation Configuration Dialog
The application SHALL provide a dialog for configuring simulation parameters.

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
- **AND** control scheduling SHALL NOT be configured globally in this dialog

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

### Requirement: Per-block control scheduling
The application SHALL determine control-block scheduling from each block's `sample_time` (`Ts`) parameter instead of global control scheduling settings.

#### Scenario: `Ts = 0` behaves as auto/continuous
- **GIVEN** a control block with `sample_time = 0`
- **WHEN** transient simulation runs
- **THEN** the block SHALL run in auto/continuous mode (updated each control evaluation step)

#### Scenario: `Ts > 0` behaves as discrete
- **GIVEN** a control block with `sample_time = 50e-6`
- **WHEN** transient simulation runs
- **THEN** the block SHALL update every `50e-6 s` and hold its output between updates

#### Scenario: Mixed-rate control blocks
- **GIVEN** one control block with `sample_time = 10e-6` and another with `sample_time = 100e-6`
- **WHEN** transient simulation runs
- **THEN** each block SHALL be evaluated at its own sampling period

### Requirement: FMU 2.0 Export
The application SHALL allow users to export the current circuit as a Functional Mock-up Unit
(FMU) compliant with the FMI 2.0 co-simulation standard, wrapping `pulsim.fmu.export`.

#### Scenario: Successful FMU export
- **GIVEN** a circuit is loaded and validated
- **WHEN** the user invokes `File ▸ Export ▸ FMU 2.0…`, fills in model name, output directory,
  and FMU model type (co-simulation or model-exchange), and confirms
- **THEN** the backend SHALL produce a `.fmu` archive at the target path
- **AND** a success toast SHALL show the absolute path with an "Open output folder" affordance

#### Scenario: Export failure surfaces clearly
- **GIVEN** the backend export raises an exception
- **THEN** the dialog SHALL display the error text verbatim and SHALL NOT silently dismiss

### Requirement: C99 Controller Codegen Export
The application SHALL allow users to generate deployable C99 real-time controller code for
the current circuit, wrapping `pulsim.codegen.generate`.

#### Scenario: Successful C99 export
- **GIVEN** a circuit with at least one control block is loaded
- **WHEN** the user invokes `File ▸ Export ▸ C99 controller…`, chooses an output directory,
  target prefix, discretization scheme, and sample rate, and confirms
- **THEN** the backend SHALL emit C99 source / header files at the target path

#### Scenario: Sample rate validation
- **GIVEN** the user enters a non-positive sample rate
- **THEN** the dialog SHALL block the export and explain the constraint inline

### Requirement: Monte-Carlo Parameter Sweep
The parameter sweep dialog SHALL support multi-parameter Monte-Carlo sweeps with
non-uniform distributions in addition to the existing linear/log range mode.

#### Scenario: Monte-Carlo run with multiple parameters
- **GIVEN** the user opens the sweep dialog and switches to the "Monte-Carlo" page
- **WHEN** the user adds two rows, each pointing at a different component+parameter and
  configured with a `Distribution` (uniform / log-uniform / normal / cartesian) plus per-row
  bounds, and picks a metric from `pulsim.sweep.metrics` (`steady_state` / `peak` / `rms` /
  `settling_time` / `custom`)
- **AND** confirms the run
- **THEN** the backend SHALL execute the sweep using `pulsim.sweep.run`
- **AND** the result viewer SHALL render a histogram + scatter on the selected metric

#### Scenario: Sweep results export to CSV
- **GIVEN** a Monte-Carlo result is present
- **THEN** the result viewer SHALL provide a CSV export button that writes one row per sample

### Requirement: Frequency Response Analysis (FRA)
The application SHALL provide a Frequency Response Analysis action wrapping
`Simulator.run_fra`, producing magnitude/phase plots for a configurable frequency sweep.

#### Scenario: Closed-loop FRA
- **GIVEN** a closed-loop converter circuit
- **WHEN** the user invokes `Simulation ▸ FRA…`, sets start/stop frequency, points-per-decade,
  perturbation amplitude, and probe selection, and confirms
- **THEN** the backend SHALL run the FRA sweep
- **AND** the result view SHALL render the Bode plot using the existing `BodePlotDialog`
  axes overlaid via `fra_overlay`
- **AND** the user SHALL be able to export the result through `export_fra_csv` and
  `export_fra_json`

### Requirement: Periodic Steady-State (Shooting) Analysis
The application SHALL provide a Periodic Steady-State action wrapping
`PeriodicSteadyStateOptions/Result`.

#### Scenario: Buck steady-state in one period
- **GIVEN** a switching converter with a known fundamental period
- **WHEN** the user invokes `Simulation ▸ Periodic Steady-State…`, enters the period guess,
  Newton tolerance, and maximum shooting iterations, and confirms
- **THEN** the backend SHALL converge on the periodic orbit
- **AND** the result view SHALL show a single-period waveform inset plus ripple metrics

#### Scenario: Divergence is surfaced
- **GIVEN** the shooting iteration fails to converge within the iteration cap
- **THEN** the dialog SHALL surface the residual history and suggest "use IC" or larger tol

### Requirement: Harmonic Balance Analysis
The application SHALL provide a Harmonic Balance action wrapping
`HarmonicBalanceOptions/Result`.

#### Scenario: HB on a rectifier
- **GIVEN** a rectifier circuit driven by a sinusoidal source
- **WHEN** the user invokes `Simulation ▸ Harmonic Balance…`, enters the fundamental
  frequency, harmonic count, and balancing tolerance, and confirms
- **THEN** the backend SHALL solve for the spectrum
- **AND** the result view SHALL render magnitude and phase per harmonic

### Requirement: Loss and Efficiency Dashboard
The scope workbench SHALL include a "Losses" tab populated from `LossAccumulator`,
`EfficiencyCalculator`, and `SystemLossSummary`.

#### Scenario: Per-device loss breakdown
- **GIVEN** a simulation result includes loss telemetry
- **THEN** the Losses tab SHALL render a per-device table with conduction loss, switching
  loss, total loss, and share-of-system percentage
- **AND** the table SHALL be sortable by any numeric column

#### Scenario: System efficiency readout
- **GIVEN** the simulation result includes input and output power telemetry
- **THEN** the Losses tab SHALL show a stacked-bar chart of system loss components
- **AND** a single efficiency readout in percent

#### Scenario: Empty state when telemetry is absent
- **GIVEN** the active simulation has no loss telemetry
- **THEN** the Losses tab SHALL show a helpful empty-state card rather than an error

### Requirement: Advanced Convergence Diagnostics
The convergence diagnostics dialog SHALL expose per-iteration, per-variable, and
linear-solver-fallback views populated from `ConvergenceHistory`, `IterationRecord`,
`PerVariableConvergence`, `FallbackTraceEntry`, and `LinearSolverTelemetry`.

#### Scenario: Per-iteration residual chart
- **GIVEN** a simulation has run with telemetry capture enabled
- **THEN** the dialog SHALL plot the residual vs. iteration for each timestep block

#### Scenario: Per-variable convergence table
- **GIVEN** the telemetry includes per-variable records
- **THEN** the dialog SHALL list each variable's worst-iteration residual and final value

#### Scenario: Linear solver fallback chain
- **GIVEN** the linear solver fell back during the run
- **THEN** the dialog SHALL list every `FallbackTraceEntry` with reason and recovery solver

### Requirement: Advanced Solver Knobs
The simulation settings dialog SHALL provide an "Advanced" tab exposing the full suite of
solver configuration structures: `GminConfig`, `SourceSteppingConfig`,
`PseudoTransientConfig`, `InitializationConfig`, `DCConvergenceConfig`, `BDFOrderConfig`,
`RichardsonLTEConfig`, `AdvancedTimestepConfig`, `LinearSolverStackConfig`, and
`IterativeSolverConfig`.

#### Scenario: Settings round-trip
- **GIVEN** the user opens the Advanced tab and edits at least one knob in each structure
- **WHEN** the user confirms and reopens the dialog
- **THEN** all knobs SHALL display the persisted values
- **AND** the backend SHALL receive the same values when the next simulation runs

#### Scenario: Linear solver stack selection
- **WHEN** the user picks a different linear solver stack (KLU / EnhancedSparseLU / GMRES /
  BiCGSTAB)
- **THEN** the next simulation SHALL use that stack
- **AND** convergence diagnostics SHALL report the active stack in its summary

