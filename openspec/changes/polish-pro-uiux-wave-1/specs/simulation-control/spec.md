## ADDED Requirements

### Requirement: Simulation Progress Signal
The simulation service SHALL emit a progress signal at least 10 times per second while a simulation is running so visual indicators can update smoothly.

#### Scenario: Progress fires during transient
- **GIVEN** a transient simulation is running
- **WHEN** the runtime advances through timesteps
- **THEN** the service SHALL emit a `progress` signal with `(t_current, t_stop, wall_elapsed_s)` at a minimum rate of 10 Hz

#### Scenario: Progress fires once on completion
- **GIVEN** a simulation reaches `t_stop` successfully
- **THEN** the service SHALL emit one final `progress` signal with `t_current == t_stop` before emitting the `completed` signal

### Requirement: Run Bar Bound to Simulation Service
The Run Bar widget SHALL bind to the simulation service's `progress`, `started`, `completed`, and `failed` signals and update its visible state accordingly.

#### Scenario: Started → progress → completed
- **GIVEN** the user clicks the Run button on the Run Bar
- **WHEN** the service emits the `started` signal
- **THEN** the Run Bar SHALL switch to the "running" visual state (progress bar visible, Run button → Pause)
- **AND** subsequent `progress` ticks SHALL animate the progress bar smoothly
- **AND** the final `completed` signal SHALL switch the bar to the "completed" state (progress = 100 %)

#### Scenario: Failed run
- **GIVEN** a simulation is running
- **WHEN** the service emits the `failed` signal
- **THEN** the Run Bar SHALL switch to the "failed" state (progress = current %, red accent) and display the failure reason in the Run Bar's status segment

### Requirement: Stale-Waveform Indicator
The scope window SHALL display a "stale" indicator when its current data set no longer reflects the schematic state.

#### Scenario: Stale flag set on schematic edit
- **GIVEN** a scope window shows the results of a completed simulation
- **WHEN** the user edits any component parameter
- **THEN** the scope window's header SHALL show a "stale" badge with a "Re-run" button

#### Scenario: Stale flag clears on new run
- **GIVEN** the stale badge is visible
- **WHEN** the user starts a new simulation and it completes successfully
- **THEN** the badge SHALL clear and the scope window SHALL display the fresh data
