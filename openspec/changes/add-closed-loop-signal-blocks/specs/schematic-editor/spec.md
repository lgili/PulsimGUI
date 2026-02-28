## ADDED Requirements

### Requirement: Constant block renders as labelled rectangle
The schematic editor SHALL render a `CONSTANT` block as a filled rectangle
containing the numeric value centred in the body, so users can read the
reference value directly on the canvas without opening the Properties panel.

#### Scenario: Constant block displays its value in the body
- **GIVEN** a Constant block placed on the schematic with `value = 48.0`
- **THEN** the schematic item SHALL display `48.0` (or `48 V` with unit suffix
  if a unit is set) centred inside the block rectangle

#### Scenario: Constant block value updates live when parameter changes
- **GIVEN** a Constant block on the schematic
- **WHEN** the user changes `value` to `24.0` in the Properties panel
- **THEN** the schematic item body text SHALL update to `24.0` without requiring
  deselect/reselect

## MODIFIED Requirements

### Requirement: Signal wires connect freely between all signal-domain blocks
The schematic editor SHALL allow wire connections between the output pin of any
signal-domain block (including `CONSTANT` and `LIMITER`) and the input pin of any
other signal-domain block, subject to the existing same-domain connection rule.

#### Scenario: Constant output wires to Sum input
- **GIVEN** a Constant block and a Sum block on the schematic
- **WHEN** the user draws a wire from Constant `OUT` to Sum `IN_0`
- **THEN** the wire SHALL be accepted and rendered as a signal wire (dashed/thin)
  with no error

#### Scenario: Limiter output wires to PI reference input
- **GIVEN** a Limiter block and a PI Controller block on the schematic
- **WHEN** the user draws a wire from Limiter `OUT` to PI `REF`
- **THEN** the wire SHALL be accepted with no error

#### Scenario: Signal wire to electrical pin is rejected
- **GIVEN** a Constant block on the schematic
- **WHEN** the user attempts to draw a wire from Constant `OUT` to the anode of
  a Diode
- **THEN** the connection SHALL be rejected and a tooltip SHALL explain the
  domain mismatch
