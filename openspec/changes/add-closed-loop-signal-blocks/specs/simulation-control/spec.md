## ADDED Requirements

### Requirement: Signal-flow evaluator runs each simulation step
The simulation backend SHALL evaluate all signal-domain blocks (Constant, Probe,
Gain, Sum, Subtractor, Limiter, PI) in **topological order** every simulation
step, after the electrical solver snapshot and before gate signals are applied
to switches.

#### Scenario: Correct evaluation order for closed-loop chain
- **GIVEN** a schematic with: Constant → Subtractor IN_0; V Probe → Gain → Subtractor IN_1; Subtractor → Limiter → PI → PWM DUTY_IN
- **WHEN** simulation starts
- **THEN** the backend SHALL determine and log the evaluation order as:
  Constant, V Probe, Gain, Subtractor, Limiter, PI, PWM

#### Scenario: Algebraic loop is detected and rejected
- **GIVEN** a schematic where block A's output is wired to block B's input AND
  block B's output is wired back to block A's input (circular dependency)
- **WHEN** the user clicks Run
- **THEN** simulation SHALL NOT start; the GUI SHALL display an error message
  identifying the blocks that form the loop

### Requirement: Constant block outputs fixed value every step
The simulation backend SHALL evaluate `CONSTANT` blocks by returning the value
set in the `value` parameter on every simulation step.

#### Scenario: Constant as voltage reference in closed-loop buck
- **GIVEN** a Constant block with `value = 12.0` wired to a Subtractor's `IN_0`
- **WHEN** simulation runs for 1 ms
- **THEN** the Subtractor shall receive `12.0` as its first operand every step

### Requirement: Limiter block clamps signal between lower and upper bounds
The simulation backend SHALL clamp the input signal of a `LIMITER` block to the
range [`lower`, `upper`] and pass the result to the output wire.

#### Scenario: Signal within bounds passes through unchanged
- **GIVEN** a Limiter with `lower = -5.0`, `upper = 5.0` and an input signal of `3.2`
- **WHEN** the step is evaluated
- **THEN** the output SHALL be `3.2`

#### Scenario: Signal above upper is clamped
- **GIVEN** a Limiter with `upper = 1.0` and an input signal of `1.8`
- **WHEN** the step is evaluated
- **THEN** the output SHALL be `1.0`

#### Scenario: Signal below lower is clamped
- **GIVEN** a Limiter with `lower = 0.0` and an input signal of `-0.3`
- **WHEN** the step is evaluated
- **THEN** the output SHALL be `0.0`

### Requirement: PWM duty cycle overridden by DUTY_IN signal when connected
The simulation SHALL use the value on the `DUTY_IN` signal wire as the duty cycle
for the current step when that pin is connected, ignoring the static `duty_cycle`
parameter. The duty cycle SHALL be clamped to [0, 1] before being applied.

#### Scenario: Dynamic duty cycle from PI output
- **GIVEN** a PI Controller with output wired to PWM `DUTY_IN`
- **WHEN** the PI output is `0.55` at step k
- **THEN** the PWM carrier shall use duty = 0.55 for that step's gate pulse

#### Scenario: Duty clamped to valid range [0, 1]
- **GIVEN** a PI Controller output that momentarily exceeds 1.0 (e.g. `1.15`)
  wired to PWM `DUTY_IN`
- **WHEN** the step is evaluated
- **THEN** the PWM SHALL clamp duty to `1.0` (100 %) and not produce undefined
  gate behaviour
