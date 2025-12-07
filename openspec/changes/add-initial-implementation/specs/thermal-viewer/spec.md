## ADDED Requirements

### Requirement: Thermal Results Panel

The application SHALL provide a panel for viewing thermal simulation results.

#### Scenario: Panel display
- **GIVEN** thermal simulation is enabled and completes
- **THEN** a thermal results panel SHALL show device temperatures and loss distribution

### Requirement: Device Temperature Display

The application SHALL show device temperatures on the schematic.

#### Scenario: Temperature overlay
- **GIVEN** thermal simulation has completed
- **WHEN** the user enables "Show Temperatures"
- **THEN** each device with thermal model SHALL show temperature with color coding

### Requirement: Thermal Network Visualization

The application SHALL visualize the thermal equivalent circuit.

#### Scenario: Thermal network diagram
- **GIVEN** thermal models are configured
- **WHEN** the user opens the thermal network view
- **THEN** a diagram SHALL show RC stages and heat flow direction

### Requirement: Loss Distribution Display

The application SHALL visualize power loss distribution.

#### Scenario: Loss summary table
- **GIVEN** loss calculation is enabled
- **WHEN** the simulation completes
- **THEN** a table SHALL show conduction losses, switching losses, and total per device

### Requirement: Efficiency Display

The application SHALL calculate and display converter efficiency.

#### Scenario: Efficiency summary
- **GIVEN** input/output power ports are defined
- **WHEN** simulation completes
- **THEN** efficiency percentage, input power, and output power SHALL be displayed

### Requirement: Thermal Impedance Curves

The application SHALL display thermal impedance characteristics.

#### Scenario: Zth curve display
- **GIVEN** a thermal model is configured
- **WHEN** the user requests Zth curve
- **THEN** a plot SHALL show thermal impedance vs. time

### Requirement: Safe Operating Area (SOA)

The application SHALL help verify safe operating conditions.

#### Scenario: SOA plot
- **GIVEN** a MOSFET or IGBT is in the circuit
- **WHEN** the user opens SOA view
- **THEN** a plot SHALL show device operating points vs. SOA boundary

### Requirement: Heat Flow Animation

The application SHALL animate heat flow through the thermal network.

#### Scenario: Animate heating
- **GIVEN** transient thermal simulation exists
- **WHEN** the user plays the animation
- **THEN** heat flow SHALL be visualized with color intensity changes

### Requirement: Export Thermal Results

The application SHALL support exporting thermal data.

#### Scenario: Export to CSV
- **GIVEN** thermal results exist
- **WHEN** the user exports to CSV
- **THEN** the file SHALL contain time, temperature, and power loss columns
