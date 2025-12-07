# Parameter Editor

## Purpose

Properties panel and dialogs for editing component parameters, model selection, and device configuration.

## Requirements

### Requirement: Properties Panel

The application SHALL provide a properties panel for editing selected components.

#### Scenario: Panel location
- **GIVEN** the default layout is active
- **THEN** the properties panel SHALL be docked on the right side

#### Scenario: Single selection display
- **GIVEN** a single component is selected
- **THEN** the properties panel SHALL show:
  - Component type and icon
  - Component name (editable)
  - All configurable parameters
  - Node connections

#### Scenario: Multi-selection display
- **GIVEN** multiple components of the same type are selected
- **THEN** the properties panel SHALL:
  - Show common parameters
  - Allow bulk editing
  - Indicate when values differ (mixed)

#### Scenario: No selection
- **GIVEN** nothing is selected
- **THEN** the properties panel SHALL show:
  - "No selection" message
  - Circuit-level properties option

### Requirement: Parameter Input

The properties panel SHALL provide appropriate input widgets for each parameter type.

#### Scenario: Numeric input
- **GIVEN** a numeric parameter is displayed
- **THEN** the input SHALL:
  - Accept numbers with SI prefixes (1k, 10u, 2.5m)
  - Show units label (ohms, farads, etc.)
  - Validate input range
  - Support spinner for increment/decrement

#### Scenario: SI prefix support
- **GIVEN** the user types "10k"
- **THEN** the value SHALL be interpreted as 10000
- **AND** displayed as "10k" not "10000"

#### Scenario: Available SI prefixes
- **GIVEN** numeric input is available
- **THEN** supported prefixes SHALL include:
  - f (femto, 10^-15)
  - p (pico, 10^-12)
  - n (nano, 10^-9)
  - u (micro, 10^-6)
  - m (milli, 10^-3)
  - k (kilo, 10^3)
  - meg (mega, 10^6)
  - g (giga, 10^9)
  - t (tera, 10^12)

#### Scenario: Dropdown selection
- **GIVEN** a parameter has enumerated values (e.g., MOSFET type)
- **THEN** a dropdown SHALL show available options

#### Scenario: Boolean toggle
- **GIVEN** a boolean parameter exists
- **THEN** a checkbox or toggle switch SHALL be displayed

### Requirement: Component-Specific Editors

Different component types SHALL have appropriate parameter editors.

#### Scenario: Resistor parameters
- **GIVEN** a resistor is selected
- **THEN** editable parameters SHALL include:
  - Resistance value
  - Temperature coefficient 1 (TC1)
  - Temperature coefficient 2 (TC2)

#### Scenario: Capacitor parameters
- **GIVEN** a capacitor is selected
- **THEN** editable parameters SHALL include:
  - Capacitance value
  - Initial voltage (IC)
  - ESR (optional)

#### Scenario: Inductor parameters
- **GIVEN** an inductor is selected
- **THEN** editable parameters SHALL include:
  - Inductance value
  - Initial current (IC)
  - DCR (optional)

#### Scenario: Diode parameters
- **GIVEN** a diode is selected
- **THEN** editable parameters SHALL include:
  - Saturation current (Is)
  - Emission coefficient (n)
  - Series resistance (Rs)
  - Junction capacitance (Cjo)
  - Transit time (Tt)
  - Reverse recovery parameters

#### Scenario: MOSFET parameters
- **GIVEN** a MOSFET is selected
- **THEN** editable parameters SHALL include:
  - Type (NMOS/PMOS)
  - Model level (1, 2, 3, BSIM3)
  - Threshold voltage (Vth)
  - Transconductance parameter (Kp)
  - Channel length modulation (lambda)
  - Channel width (W) and length (L)
  - Body diode parameters
  - Gate capacitances

#### Scenario: IGBT parameters
- **GIVEN** an IGBT is selected
- **THEN** editable parameters SHALL include:
  - Threshold voltage (Vth)
  - Saturation voltage (Vce_sat)
  - Turn-on time
  - Turn-off time
  - Tail current parameters
  - Body diode parameters

#### Scenario: Switch parameters
- **GIVEN** a switch is selected
- **THEN** editable parameters SHALL include:
  - On resistance (Ron)
  - Off resistance (Roff)
  - Threshold voltage
  - Initial state (open/closed)

#### Scenario: Transformer parameters
- **GIVEN** a transformer is selected
- **THEN** editable parameters SHALL include:
  - Turns ratio
  - Magnetizing inductance (Lm)
  - Leakage inductance (primary/secondary)
  - Winding resistance

### Requirement: Source Waveform Editor

Voltage and current sources SHALL have specialized waveform editors.

#### Scenario: DC source
- **GIVEN** a DC source is selected
- **THEN** a single value input SHALL be shown

#### Scenario: Pulse waveform editor
- **GIVEN** a pulse source is selected
- **THEN** the editor SHALL show:
  - Initial value (V1)
  - Pulse value (V2)
  - Delay time
  - Rise time
  - Fall time
  - Pulse width
  - Period
  - Visual preview of waveform

#### Scenario: Sine waveform editor
- **GIVEN** a sine source is selected
- **THEN** the editor SHALL show:
  - DC offset
  - Amplitude
  - Frequency
  - Phase
  - Damping factor (optional)
  - Visual preview of waveform

#### Scenario: PWL waveform editor
- **GIVEN** a PWL (piecewise linear) source is selected
- **THEN** the editor SHALL provide:
  - Table of time/value pairs
  - Add/remove points
  - Import from CSV
  - Visual preview with editable points

#### Scenario: PWM waveform editor
- **GIVEN** a PWM source is selected
- **THEN** the editor SHALL show:
  - Carrier frequency
  - Duty cycle (or modulation input)
  - Dead time (if complementary)
  - Phase offset
  - Visual preview

### Requirement: Device Library Selection

Components SHALL support selection from pre-defined device libraries.

#### Scenario: Select from library
- **GIVEN** a component supports device selection
- **THEN** a "Select Device" button SHALL open the device library

#### Scenario: Device library dialog
- **GIVEN** the device library dialog opens
- **THEN** it SHALL show:
  - Categorized list of available devices
  - Search/filter functionality
  - Device specifications preview
  - Recently used devices

#### Scenario: Apply device parameters
- **GIVEN** a device is selected from the library
- **WHEN** the user clicks "Apply"
- **THEN** all device parameters SHALL be populated

#### Scenario: Available device types
- **GIVEN** the device library
- **THEN** pre-configured devices SHALL include:
  - Diodes: 1N4007, 1N4148, 1N5819, MUR860, SiC diodes
  - MOSFETs: IRF540N, IRFZ44N, IPB65R045C7, GaN devices
  - IGBTs: Common industrial IGBTs

### Requirement: Parameter Expressions

Parameters SHALL support expressions for related values.

#### Scenario: Expression input
- **GIVEN** a parameter field
- **WHEN** the user types an expression like "2*pi*1000"
- **THEN** the value SHALL be calculated and stored

#### Scenario: Parameter references
- **GIVEN** parameters can reference others
- **WHEN** the user types "{R1.resistance}/2"
- **THEN** the value SHALL update when R1 changes

#### Scenario: Global parameters
- **GIVEN** global parameters are defined
- **THEN** components SHALL be able to reference them: "{Fsw}", "{Vin}"

### Requirement: Parameter Validation

The editor SHALL validate parameter values.

#### Scenario: Range validation
- **GIVEN** a parameter has valid range (e.g., resistance > 0)
- **WHEN** the user enters an invalid value
- **THEN**:
  - The field SHALL show error indication (red border)
  - A tooltip SHALL explain the valid range
  - The simulation SHALL not start with invalid values

#### Scenario: Type validation
- **GIVEN** a numeric parameter
- **WHEN** the user enters non-numeric text
- **THEN** the input SHALL be rejected or marked invalid

#### Scenario: Dependency validation
- **GIVEN** parameters have dependencies
- **WHEN** a combination is invalid
- **THEN** a warning SHALL be shown

### Requirement: Parameter Sweep Configuration

Parameters SHALL be configurable for sweeping.

#### Scenario: Mark parameter for sweep
- **GIVEN** a parameter is displayed
- **WHEN** the user right-clicks and selects "Add to Sweep"
- **THEN** the parameter SHALL be added to the sweep configuration

#### Scenario: Sweep indicator
- **GIVEN** a parameter is in a sweep
- **THEN** a sweep icon SHALL appear next to the parameter

### Requirement: Copy/Paste Parameters

Users SHALL be able to copy parameters between components.

#### Scenario: Copy parameters
- **GIVEN** a component is selected
- **WHEN** the user selects Edit > Copy Parameters
- **THEN** all parameter values SHALL be copied

#### Scenario: Paste parameters
- **GIVEN** parameters are copied and a compatible component is selected
- **WHEN** the user selects Edit > Paste Parameters
- **THEN** matching parameters SHALL be updated

### Requirement: Parameter Presets

Users SHALL be able to save and load parameter presets.

#### Scenario: Save preset
- **GIVEN** a component has configured parameters
- **WHEN** the user clicks "Save as Preset"
- **THEN** a named preset SHALL be saved for that component type

#### Scenario: Load preset
- **GIVEN** presets exist for a component type
- **WHEN** the user clicks "Load Preset"
- **THEN** a list of available presets SHALL appear

### Requirement: Thermal Parameters

Components with thermal models SHALL have thermal parameter editing.

#### Scenario: Thermal model selection
- **GIVEN** a semiconductor device is selected
- **THEN** a thermal model section SHALL allow:
  - Enable/disable thermal modeling
  - Select thermal model type (Foster, Cauer)
  - Enter thermal resistances (Rth_jc, Rth_cs, Rth_sa)
  - Enter thermal capacitances

#### Scenario: Loss model configuration
- **GIVEN** a switching device is selected
- **THEN** loss model parameters SHALL include:
  - Conduction loss model
  - Switching loss lookup table (or simplified model)
  - Temperature dependence

### Requirement: Help and Documentation

The properties panel SHALL provide inline help.

#### Scenario: Parameter help tooltip
- **GIVEN** a parameter field is hovered
- **THEN** a tooltip SHALL show:
  - Parameter description
  - Valid range
  - Default value
  - Units

#### Scenario: Open documentation
- **GIVEN** a component is selected
- **WHEN** the user presses F1 or clicks the help icon
- **THEN** documentation for that component type SHALL open
