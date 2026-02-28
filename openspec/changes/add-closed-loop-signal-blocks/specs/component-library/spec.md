## ADDED Requirements

### Requirement: Constant Block in Signal & Control catalog
The component library SHALL expose a **Constant** block under the
"Signal & Control" category to let users inject a fixed numeric reference value
into any signal-domain wire.

#### Scenario: Constant block appears in library panel
- **GIVEN** the "Signal & Control" category is expanded in the component library
- **THEN** a "Constant" entry SHALL appear with shortcut `Ctrl+K` and a tooltip
  describing it as a fixed-value signal source

#### Scenario: Constant block has one output pin
- **GIVEN** a Constant block is placed on the schematic
- **THEN** it SHALL render with exactly one pin labelled `OUT` on its right side
  and no input pins

#### Scenario: Constant value is editable
- **GIVEN** a Constant block is selected
- **THEN** the Properties panel SHALL show a numeric `value` field that accepts
  any floating-point number and defaults to `0.0`

### Requirement: Limiter Block in Signal & Control catalog
The component library SHALL expose a **Limiter** block under the
"Signal & Control" category so users can clamp a signal between a minimum and
maximum value before passing it to downstream blocks.

#### Scenario: Limiter block appears in library panel
- **GIVEN** the "Signal & Control" category is expanded
- **THEN** a "Limiter" entry SHALL appear with keywords `limit`, `clamp`, `sat`

#### Scenario: Limiter parameters are editable
- **GIVEN** a Limiter block is selected
- **THEN** the Properties panel SHALL show `lower` and `upper` float fields
  (defaulting to `-1e9` and `1e9` respectively)

## MODIFIED Requirements

### Requirement: PWM Generator gains optional duty-cycle signal input
The **PWM Generator** component SHALL accept an optional `DUTY_IN` signal input
pin so that external control blocks can override the static duty-cycle parameter
at run-time.

#### Scenario: DUTY_IN pin is visible but optional
- **GIVEN** a PWM Generator block is placed on the schematic
- **THEN** a `DUTY_IN` pin SHALL be visible on the block below the existing output
  pins, clearly labelled, and it SHALL be possible to leave it unconnected

#### Scenario: Backwards compatibility when DUTY_IN unconnected
- **GIVEN** an existing `.pulsim` file with a PWM Generator that has no
  `DUTY_IN` wire
- **WHEN** the file is loaded
- **THEN** the simulation SHALL use the static `duty_cycle` parameter as before
  with no errors or warnings
