## ADDED Requirements

### Requirement: Three-Phase Voltage Source
The component palette SHALL include a balanced/unbalanced three-phase voltage source
component, wrapping Pulsim's `grid::three_phase_source` C++ class through new pybind11
bindings.

#### Scenario: Drop and run
- **GIVEN** the user drags a Three-Phase Source from the Sources category onto the schematic
- **WHEN** the user sets line-to-line voltage, frequency, phase rotation, optional unbalance %,
  and optional THD injection, and runs the simulation
- **THEN** the result SHALL contain three voltage signals 120° apart at the requested
  fundamental frequency

#### Scenario: Feeds Clarke / Park downstream
- **GIVEN** a Three-Phase Source is connected to an existing Clarke transform block
- **THEN** the Clarke block SHALL produce stationary-frame α/β signals from the source's
  abc outputs without manual scaling

### Requirement: Motors and Drives Component Category
The component palette SHALL provide a "Motors & Drives" category exposing PMSM, PMSM with
FOC, DC motor, and mechanical-load components, wrapping Pulsim's `motors::pmsm`,
`motors::pmsm_foc`, `motors::dc_motor`, and `motors::mechanical` C++ classes via new
pybind11 bindings.

#### Scenario: PMSM available in the palette
- **GIVEN** the palette is open
- **THEN** the Motors & Drives category SHALL list at minimum: PMSM, PMSM (FOC), DC Motor,
  Mechanical Load

#### Scenario: PMSM-FOC spin-up
- **GIVEN** a PMSM-FOC block is dropped on the schematic with default parameters
- **WHEN** the user runs the simulation
- **THEN** the rotor speed signal SHALL settle to the commanded reference within the
  configured settling time

#### Scenario: Mechanical load coupling
- **GIVEN** a Mechanical Load is connected to a motor block
- **WHEN** the user configures inertia and friction
- **THEN** the motor's mechanical speed signal SHALL reflect the load dynamics

### Requirement: Saturable Transformer Component
The component palette SHALL include a saturable transformer component, wrapping Pulsim's
`magnetic::saturable_transformer` C++ class via new pybind11 bindings.

#### Scenario: Saturation visible in flux waveform
- **GIVEN** a saturable transformer is configured with a finite saturation point and excited
  beyond knee voltage
- **THEN** the magnetizing flux signal SHALL show the saturation flattening, distinguishable
  from the ideal transformer linear response

### Requirement: Hysteresis Inductor Component
The component palette SHALL include a hysteresis-inductor component, wrapping Pulsim's
`magnetic::hysteresis_inductor` C++ class via new pybind11 bindings.

#### Scenario: B-H loop visible in scope
- **GIVEN** a hysteresis inductor is driven by an AC source
- **THEN** an X-Y scope plot of B vs. H SHALL trace a closed hysteresis loop, not a single
  line

### Requirement: BH-Curve Editor Widget
The properties dialog SHALL launch a BH-curve editor for any component whose backend type
supports a `bh_curve` field, allowing import from `magnetic::core_catalog` entries and
direct anchor-point editing.

#### Scenario: Editor preserves anchors through save/load
- **GIVEN** the user edits a BH curve in a saturable component's properties
- **WHEN** the project is saved and reopened
- **THEN** the curve anchor points SHALL be identical to what was saved

#### Scenario: Import from core catalog
- **WHEN** the user picks a core material from the `magnetic::core_catalog` dropdown
- **THEN** the editor SHALL load that core's BH curve as the starting point
