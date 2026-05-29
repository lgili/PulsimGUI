## ADDED Requirements

### Requirement: Wall-time progress estimator
The simulation service SHALL emit `progress(percent, message)` at least every 100 ms during a running transient even when the backend itself does not publish progress, by sampling the partial-result trajectory length against the expected total.

#### Scenario: Long run without backend progress shows motion
- **GIVEN** the backend is a build that does not call the progress callback
- **WHEN** a transient runs for at least 500 ms wall-clock time
- **THEN** the simulation service SHALL emit at least four `progress` signals within that window
- **AND** each signal's `percent` SHALL be a monotonically non-decreasing estimate based on `len(streamed_time) / expected_total_samples`
- **AND** the Run Bar's progress segment SHALL advance accordingly

#### Scenario: Progress clamps at 99 % until completion
- **GIVEN** the wall-time estimator is the only source of progress
- **WHEN** the streamed-time count reaches or exceeds `expected_total_samples`
- **THEN** the emitted percent SHALL be clamped to 99 % until the official `simulation_finished` signal fires, at which point the Run Bar transitions to the "completed" state at 100 %
