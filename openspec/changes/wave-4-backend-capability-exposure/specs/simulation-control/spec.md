## ADDED Requirements

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
