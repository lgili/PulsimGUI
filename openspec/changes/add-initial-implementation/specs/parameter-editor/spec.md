## ADDED Requirements

### Requirement: Properties Panel

The application SHALL provide a properties panel for editing selected components.

#### Scenario: Single selection display
- **GIVEN** a single component is selected
- **THEN** the properties panel SHALL show component type, name, and all configurable parameters

### Requirement: Parameter Input

The properties panel SHALL provide appropriate input widgets for each parameter type.

#### Scenario: Numeric input with SI prefixes
- **GIVEN** the user types "10k"
- **THEN** the value SHALL be interpreted as 10000 and displayed as "10k"

### Requirement: Component-Specific Editors

Different component types SHALL have appropriate parameter editors.

#### Scenario: Resistor parameters
- **GIVEN** a resistor is selected
- **THEN** editable parameters SHALL include resistance value and temperature coefficients

### Requirement: Source Waveform Editor

Voltage and current sources SHALL have specialized waveform editors.

#### Scenario: Pulse waveform editor
- **GIVEN** a pulse source is selected
- **THEN** the editor SHALL show initial value, pulse value, timing parameters, and visual preview

### Requirement: Device Library Selection

Components SHALL support selection from pre-defined device libraries.

#### Scenario: Select from library
- **GIVEN** a component supports device selection
- **WHEN** the user clicks "Select Device"
- **THEN** the device library dialog SHALL show categorized devices with specifications

### Requirement: Parameter Expressions

Parameters SHALL support expressions for related values.

#### Scenario: Expression input
- **GIVEN** a parameter field
- **WHEN** the user types an expression like "2*pi*1000"
- **THEN** the value SHALL be calculated and stored

### Requirement: Parameter Validation

The editor SHALL validate parameter values.

#### Scenario: Range validation
- **GIVEN** a parameter has valid range
- **WHEN** the user enters an invalid value
- **THEN** the field SHALL show error indication and simulation SHALL not start

### Requirement: Parameter Sweep Configuration

Parameters SHALL be configurable for sweeping.

#### Scenario: Mark parameter for sweep
- **GIVEN** a parameter is displayed
- **WHEN** the user right-clicks and selects "Add to Sweep"
- **THEN** the parameter SHALL be added to the sweep configuration

### Requirement: Copy/Paste Parameters

Users SHALL be able to copy parameters between components.

#### Scenario: Copy parameters
- **GIVEN** a component is selected
- **WHEN** the user selects Edit > Copy Parameters
- **THEN** all parameter values SHALL be copied for pasting

### Requirement: Parameter Presets

Users SHALL be able to save and load parameter presets.

#### Scenario: Save preset
- **GIVEN** a component has configured parameters
- **WHEN** the user clicks "Save as Preset"
- **THEN** a named preset SHALL be saved for that component type

### Requirement: Thermal Parameters

Components with thermal models SHALL have thermal parameter editing.

#### Scenario: Thermal model selection
- **GIVEN** a semiconductor device is selected
- **THEN** a thermal section SHALL allow enabling thermal modeling and setting thermal resistances

### Requirement: Help and Documentation

The properties panel SHALL provide inline help.

#### Scenario: Parameter help tooltip
- **GIVEN** a parameter field is hovered
- **THEN** a tooltip SHALL show parameter description, valid range, default value, and units
