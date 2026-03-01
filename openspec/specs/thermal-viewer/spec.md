# Thermal Viewer

## Purpose

Visualization and analysis of thermal simulation results including junction temperatures, thermal impedance, and loss distribution.

## Requirements

### Requirement: Thermal Results Panel

The application SHALL provide a panel for viewing thermal simulation results.

#### Scenario: Panel display
- **GIVEN** thermal simulation is enabled and completes
- **THEN** a thermal results panel SHALL be available showing:
  - Device temperatures over time
  - Thermal network visualization
  - Loss distribution

#### Scenario: Temperature waveforms
- **GIVEN** thermal results are available
- **THEN** junction temperature vs. time SHALL be displayable in the waveform viewer

### Requirement: Device Temperature Display

The application SHALL show device temperatures on the schematic.

#### Scenario: Temperature overlay
- **GIVEN** thermal simulation has completed
- **WHEN** the user enables "Show Temperatures"
- **THEN** each device with thermal model SHALL show:
  - Current/final junction temperature
  - Color coding (green → yellow → red based on temperature)

#### Scenario: Temperature animation
- **GIVEN** transient thermal results exist
- **WHEN** the user plays the temperature animation
- **THEN** the schematic SHALL show temperature evolution over time

### Requirement: Thermal Network Visualization

The application SHALL visualize the thermal equivalent circuit.

#### Scenario: Thermal network diagram
- **GIVEN** thermal models are configured
- **WHEN** the user opens the thermal network view
- **THEN** a diagram SHALL show:
  - RC stages (Foster or Cauer network)
  - Heat flow direction
  - Temperature at each node
  - Thermal resistances and capacitances

#### Scenario: Interactive thermal schematic
- **GIVEN** the thermal network is displayed
- **THEN** clicking on a stage SHALL show detailed parameters

### Requirement: Loss Distribution Display

The application SHALL visualize power loss distribution.

#### Scenario: Loss summary table
- **GIVEN** loss calculation is enabled
- **WHEN** the simulation completes
- **THEN** a table SHALL show for each device:
  - Device name
  - Conduction losses (W)
  - Switching losses (W)
  - Total losses (W)
  - Percentage of total

#### Scenario: Loss pie chart
- **GIVEN** loss data is available
- **THEN** a pie chart SHALL show loss distribution:
  - By device
  - By loss type (conduction vs switching)

#### Scenario: Loss bar chart
- **GIVEN** multiple devices have losses
- **THEN** a bar chart SHALL compare:
  - Losses per device
  - Stacked bars showing loss breakdown

### Requirement: Efficiency Display

The application SHALL calculate and display converter efficiency.

#### Scenario: Efficiency summary
- **GIVEN** input/output power ports are defined
- **WHEN** simulation completes
- **THEN** efficiency SHALL be displayed:
  - Average efficiency (%)
  - Input power (W)
  - Output power (W)
  - Total losses (W)

#### Scenario: Efficiency vs load curve
- **GIVEN** a load sweep has been performed
- **THEN** efficiency vs. load power SHALL be plottable

### Requirement: Thermal Impedance Curves

The application SHALL display thermal impedance characteristics.

#### Scenario: Zth curve display
- **GIVEN** a thermal model is configured
- **WHEN** the user requests Zth curve
- **THEN** a plot SHALL show thermal impedance vs. time (log scale)

#### Scenario: Compare to datasheet
- **GIVEN** Zth curves are displayed
- **THEN** the user SHALL be able to overlay datasheet curves for comparison

### Requirement: Safe Operating Area (SOA)

The application SHALL help verify safe operating conditions.

#### Scenario: SOA plot
- **GIVEN** a MOSFET or IGBT is in the circuit
- **WHEN** the user opens SOA view
- **THEN** a plot SHALL show:
  - Device operating points (Vds vs Id)
  - SOA boundary from device data
  - Warning indicators if outside SOA

#### Scenario: Thermal derating
- **GIVEN** junction temperature is simulated
- **THEN** SOA boundaries SHALL adjust for temperature

### Requirement: Heat Flow Animation

The application SHALL animate heat flow through the thermal network.

#### Scenario: Animate heating
- **GIVEN** transient thermal simulation exists
- **WHEN** the user plays the animation
- **THEN** heat flow SHALL be visualized as:
  - Color intensity changes
  - Animated flow indicators
  - Temperature readings updating

### Requirement: Export Thermal Results

The application SHALL support exporting thermal data.

#### Scenario: Export to CSV
- **GIVEN** thermal results exist
- **WHEN** the user exports to CSV
- **THEN** the file SHALL contain:
  - Time column
  - Temperature columns for each device
  - Power loss columns

#### Scenario: Export thermal report
- **GIVEN** thermal simulation is complete
- **WHEN** the user generates a report
- **THEN** a PDF/HTML report SHALL include:
  - Configuration summary
  - Temperature waveforms
  - Loss breakdown
  - Efficiency summary
  - Thermal margin analysis
