# Thermal Integration

## Purpose

Integrate the real PulsimCore thermal simulation engine while maintaining fallback to synthetic data when unavailable.

## ADDED Requirements

### Requirement: Real Thermal Simulation

The application SHALL use the real PulsimCore thermal simulator when available.

#### Scenario: Run thermal with backend
- **GIVEN** PulsimCore backend with thermal capability is available
- **AND** a transient simulation has completed
- **WHEN** the user opens Thermal Viewer
- **THEN** the backend's `run_thermal()` method SHALL be called
- **AND** real junction temperatures and losses SHALL be displayed

#### Scenario: Thermal after transient
- **GIVEN** a transient simulation result exists
- **WHEN** thermal analysis is requested
- **THEN** the electrical waveforms SHALL be used for loss calculation
- **AND** switching times SHALL be extracted for switching loss computation

#### Scenario: Standalone thermal
- **GIVEN** no transient result exists
- **WHEN** thermal analysis is requested
- **THEN** a quick transient SHALL be run first
- **OR** the user SHALL be prompted to run transient

### Requirement: Thermal Capability Detection

The application SHALL detect thermal capability from the backend.

#### Scenario: Thermal available
- **GIVEN** the backend has `ThermalSimulator` class
- **WHEN** `backend.has_capability("thermal")` is called
- **THEN** it SHALL return True

#### Scenario: Thermal unavailable
- **GIVEN** the backend lacks `ThermalSimulator`
- **WHEN** `backend.has_capability("thermal")` is called
- **THEN** it SHALL return False
- **AND** thermal menu items SHALL show "(Synthetic)" suffix

### Requirement: Synthetic Fallback

The application SHALL fall back to synthetic thermal data when backend unavailable.

#### Scenario: Fallback activation
- **GIVEN** real thermal simulation is unavailable
- **WHEN** thermal viewer is opened
- **THEN** synthetic thermal data SHALL be generated
- **AND** a banner SHALL indicate "(Synthetic Data)"

#### Scenario: Fallback indication
- **GIVEN** thermal results are synthetic
- **THEN** `ThermalResult.is_synthetic` SHALL be True
- **AND** the UI SHALL visually indicate synthetic mode

#### Scenario: Fallback quality
- **GIVEN** synthetic mode is active
- **THEN** generated data SHALL be:
  - Deterministic (same circuit = same data)
  - Plausible (reasonable temperature ranges)
  - Useful for UI development and testing

### Requirement: Foster Network Display

The application SHALL display Foster thermal network parameters.

#### Scenario: Foster stages from backend
- **GIVEN** thermal analysis completes with real backend
- **THEN** the thermal viewer SHALL display:
  - Number of Foster stages per device
  - R and C values for each stage
  - Time constants (tau = R * C)

#### Scenario: Foster network visualization
- **GIVEN** Foster network data is available
- **THEN** the viewer SHALL provide:
  - RC ladder diagram
  - Impedance vs frequency plot (optional)
  - Cumulative thermal resistance

### Requirement: Loss Breakdown

The application SHALL display detailed power loss breakdown.

#### Scenario: Loss calculation from backend
- **GIVEN** thermal analysis with real backend
- **THEN** the loss summary SHALL show per device:
  - Conduction losses (W)
  - Switching losses - turn-on (W)
  - Switching losses - turn-off (W)
  - Reverse recovery losses (W)
  - Total losses (W)

#### Scenario: Loss percentage breakdown
- **GIVEN** loss data is available
- **THEN** a pie chart SHALL show:
  - Percentage of total losses per device
  - Percentage by loss type (conduction vs switching)

#### Scenario: Instantaneous loss waveforms
- **GIVEN** thermal analysis is complete
- **WHEN** the user selects "Show Loss Waveforms"
- **THEN** instantaneous power loss signals SHALL be available
- **AND** they can be plotted in the waveform viewer

### Requirement: Temperature Traces

The application SHALL display temperature evolution over time.

#### Scenario: Junction temperature plot
- **GIVEN** thermal analysis is complete
- **THEN** the thermal viewer SHALL show:
  - Junction temperature vs time for each device
  - Peak temperature annotation
  - Steady-state temperature annotation

#### Scenario: Temperature limits
- **GIVEN** device thermal limits are specified
- **WHEN** temperature exceeds limit
- **THEN** the plot SHALL highlight the violation
- **AND** a warning SHALL be shown

### Requirement: Thermal Settings

The application SHALL allow configuring thermal analysis.

#### Scenario: Thermal settings dialog
- **GIVEN** the user opens Thermal > Settings
- **THEN** options SHALL include:
  - Ambient temperature (default: 25°C)
  - Include switching losses (default: Yes)
  - Include conduction losses (default: Yes)
  - Thermal network type (Foster/Cauer)

#### Scenario: Per-device thermal parameters
- **GIVEN** a semiconductor device is selected
- **WHEN** the user opens its properties
- **THEN** thermal parameters SHALL be editable:
  - Rth_jc (junction to case)
  - Rth_ch (case to heatsink)
  - Rth_ha (heatsink to ambient)
  - Thermal capacitances

### Requirement: Thermal Export

The application SHALL allow exporting thermal results.

#### Scenario: Export thermal summary
- **GIVEN** thermal analysis is complete
- **WHEN** the user clicks Export
- **THEN** a CSV SHALL be generated with:
  - Device names
  - Peak temperatures
  - Average temperatures
  - Loss breakdown

#### Scenario: Export temperature traces
- **GIVEN** thermal analysis is complete
- **WHEN** the user exports waveforms
- **THEN** temperature vs time data SHALL be exportable
- **AND** format options include CSV and NumPy
