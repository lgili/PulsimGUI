## MODIFIED Requirements

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

## ADDED Requirements

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
