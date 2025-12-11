# Spec Delta: component-library

## ADDED Requirements

### Requirement: Power Semiconductor Components
The library SHALL include additional power semiconductor components.

#### Scenario: BJT NPN transistor
- Given the component library is open
- When the user expands the Semiconductors category
- Then BJT_NPN is available with pins: C (collector), B (base), E (emitter)
- And parameters include: beta (current gain), vbe_sat, vce_sat, is_ (saturation current)
- And the symbol shows standard NPN transistor with arrow out from emitter

#### Scenario: BJT PNP transistor
- Given the component library is open
- When the user expands the Semiconductors category
- Then BJT_PNP is available with pins: C, B, E
- And parameters match BJT_NPN
- And the symbol shows standard PNP transistor with arrow into emitter

#### Scenario: Thyristor (SCR)
- Given the component library is open
- When the user expands the Semiconductors category
- Then THYRISTOR is available with pins: A (anode), K (cathode), G (gate)
- And parameters include: vgt (gate trigger voltage), igt (gate trigger current), holding_current
- And the symbol shows standard SCR symbol

#### Scenario: TRIAC
- Given the component library is open
- When the user expands the Semiconductors category
- Then TRIAC is available with pins: MT1, MT2, G (gate)
- And parameters include: vgt, igt, holding_current
- And the symbol shows standard TRIAC symbol (bidirectional)

#### Scenario: Zener diode
- Given the component library is open
- When the user expands the Semiconductors category
- Then ZENER_DIODE is available with pins: A (anode), K (cathode)
- And parameters include: vz (zener voltage), iz_test, zz (zener impedance)
- And the symbol shows diode with bent cathode line

#### Scenario: LED
- Given the component library is open
- When the user expands the Semiconductors category
- Then LED is available with pins: A (anode), K (cathode)
- And parameters include: vf (forward voltage), color, wavelength
- And the symbol shows diode with light emission arrows

---

### Requirement: Analog Components
The library SHALL include operational amplifiers and comparators.

#### Scenario: Operational amplifier
- Given the component library is open
- When the user expands the Analog category
- Then OP_AMP is available with pins: IN+ (non-inverting), IN- (inverting), OUT, V+, V-
- And parameters include: gain (open-loop), gbw (gain-bandwidth), slew_rate, vos (offset voltage)
- And the symbol shows standard triangle op-amp symbol

#### Scenario: Comparator
- Given the component library is open
- When the user expands the Analog category
- Then COMPARATOR is available with pins: IN+, IN-, OUT, V+, V-
- And parameters include: vos, hysteresis, response_time
- And the symbol shows op-amp style with digital output indicator

---

### Requirement: Protection Components
The library SHALL include circuit protection components.

#### Scenario: Relay
- Given the component library is open
- When the user expands the Protection category
- Then RELAY is available with pins: COIL+, COIL-, COM, NO (normally open), NC (normally closed)
- And parameters include: coil_voltage, coil_resistance, contact_rating
- And the symbol shows coil and switch contacts

#### Scenario: Fuse
- Given the component library is open
- When the user expands the Protection category
- Then FUSE is available with pins: 1, 2
- And parameters include: rating (current), blow_time_curve
- And the symbol shows standard fuse (rectangle with S-curve wire)

#### Scenario: Circuit breaker
- Given the component library is open
- When the user expands the Protection category
- Then CIRCUIT_BREAKER is available with pins: LINE, LOAD
- And parameters include: trip_current, trip_time
- And the symbol shows breaker switch symbol

---

### Requirement: Control Block Components
The library SHALL include signal processing and control blocks.

#### Scenario: Integrator block
- Given the component library is open
- When the user expands the Control category
- Then INTEGRATOR is available with pins: IN, OUT
- And parameters include: gain, initial_value, saturation_limits
- And the symbol shows block with "∫" label

#### Scenario: Differentiator block
- Given the component library is open
- When the user expands the Control category
- Then DIFFERENTIATOR is available with pins: IN, OUT
- And parameters include: gain, filter_time_constant
- And the symbol shows block with "d/dt" label

#### Scenario: Limiter block
- Given the component library is open
- When the user expands the Control category
- Then LIMITER is available with pins: IN, OUT
- And parameters include: upper_limit, lower_limit
- And the symbol shows block with saturation curve icon

#### Scenario: Rate limiter block
- Given the component library is open
- When the user expands the Control category
- Then RATE_LIMITER is available with pins: IN, OUT
- And parameters include: rising_rate, falling_rate
- And the symbol shows block with ramp icon

#### Scenario: Hysteresis block
- Given the component library is open
- When the user expands the Control category
- Then HYSTERESIS is available with pins: IN, OUT
- And parameters include: upper_threshold, lower_threshold, output_high, output_low
- And the symbol shows block with hysteresis curve icon

#### Scenario: Lookup table
- Given the component library is open
- When the user expands the Control category
- Then LOOKUP_TABLE is available with pins: IN, OUT
- And parameters include: table_data (x,y pairs), interpolation_method
- And the symbol shows block with "f(x)" label

#### Scenario: Transfer function
- Given the component library is open
- When the user expands the Control category
- Then TRANSFER_FUNCTION is available with pins: IN, OUT
- And parameters include: numerator_coefficients, denominator_coefficients
- And the symbol shows block with "H(s)" label

#### Scenario: Delay block
- Given the component library is open
- When the user expands the Control category
- Then DELAY_BLOCK is available with pins: IN, OUT
- And parameters include: delay_time
- And the symbol shows block with "T" or clock icon

#### Scenario: Sample and hold
- Given the component library is open
- When the user expands the Control category
- Then SAMPLE_HOLD is available with pins: IN, TRIGGER, OUT
- And parameters include: sample_time
- And the symbol shows block with "S/H" label

#### Scenario: State machine
- Given the component library is open
- When the user expands the Control category
- Then STATE_MACHINE is available with pins: inputs (configurable), outputs (configurable)
- And parameters include: states, transitions, initial_state
- And the symbol shows block with state diagram icon

---

### Requirement: Measurement Components
The library SHALL include measurement probes.

#### Scenario: Voltage probe
- Given the component library is open
- When the user expands the Measurement category
- Then VOLTAGE_PROBE is available with pins: + (positive), - (negative/reference)
- And the measured value is available to waveform viewer
- And the symbol shows voltmeter circle with "V"

#### Scenario: Current probe
- Given the component library is open
- When the user expands the Measurement category
- Then CURRENT_PROBE is available with pin: through (inserted in wire)
- And the measured value is available to waveform viewer
- And the symbol shows ammeter circle with "A" and current arrow

#### Scenario: Power probe
- Given the component library is open
- When the user expands the Measurement category
- Then POWER_PROBE is available with pins: V+, V-, I (current path)
- And the measured value shows instantaneous power
- And the symbol shows wattmeter with "W"

---

### Requirement: Magnetic Components
The library SHALL include advanced magnetic components.

#### Scenario: Saturable inductor
- Given the component library is open
- When the user expands the Magnetic category
- Then SATURABLE_INDUCTOR is available with pins: 1, 2
- And parameters include: inductance, saturation_current, saturation_inductance
- And the symbol shows inductor with saturation indicator (filled core)

#### Scenario: Coupled inductor
- Given the component library is open
- When the user expands the Magnetic category
- Then COUPLED_INDUCTOR is available with pins: L1_1, L1_2, L2_1, L2_2
- And parameters include: l1, l2, mutual_inductance, coupling_coefficient
- And the symbol shows two coupled coils with dot notation

---

### Requirement: Pre-configured Networks
The library SHALL include commonly used component networks.

#### Scenario: RC snubber
- Given the component library is open
- When the user expands the Networks category
- Then SNUBBER_RC is available with pins: 1, 2
- And parameters include: resistance, capacitance
- And the symbol shows R and C in series as single block
- And the component behaves as series RC circuit

---

### Requirement: New Library Categories
The library SHALL have additional categories for new components.

#### Scenario: Analog category
- Given the component library is open
- Then an "Analog" category exists
- And it contains: OP_AMP, COMPARATOR
- And the category has a distinctive color/icon

#### Scenario: Protection category
- Given the component library is open
- Then a "Protection" category exists
- And it contains: RELAY, FUSE, CIRCUIT_BREAKER
- And the category has a distinctive color/icon

#### Scenario: Measurement category
- Given the component library is open
- Then a "Measurement" category exists
- And it contains: VOLTAGE_PROBE, CURRENT_PROBE, POWER_PROBE
- And the category has a distinctive color/icon

#### Scenario: Magnetic category
- Given the component library is open
- Then a "Magnetic" category exists
- And it contains: SATURABLE_INDUCTOR, COUPLED_INDUCTOR
- And the category has a distinctive color/icon

#### Scenario: Networks category
- Given the component library is open
- Then a "Networks" category exists
- And it contains: SNUBBER_RC
- And the category has a distinctive color/icon
