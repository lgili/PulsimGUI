## ADDED Requirements

### Requirement: Control-block sample time parameter
The properties panel SHALL expose a `Ts` (`sample_time`) parameter for control blocks, with default value `0.0`.

#### Scenario: Default Ts on new control block
- **GIVEN** the user places a control block (for example PI, PWM, Gain, Sum, Integrator)
- **WHEN** the block is selected
- **THEN** the properties panel SHALL show `Ts` with default value `0`

#### Scenario: User sets discrete Ts
- **GIVEN** a control block is selected
- **WHEN** the user sets `Ts` to a positive value
- **THEN** the block SHALL be configured for discrete updates at that sampling period
- **AND** the value SHALL persist when the project is saved and loaded

#### Scenario: Scopes and probes do not expose Ts
- **GIVEN** the user selects an Electrical Scope, Thermal Scope, Voltage Probe, Current Probe, or Power Probe
- **THEN** the properties panel SHALL NOT expose `Ts`
