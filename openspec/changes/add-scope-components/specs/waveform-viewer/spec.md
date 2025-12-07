## ADDED Requirements
### Requirement: Scope Component Windows
Scope components SHALL open dedicated waveform viewer windows that inherit all oscilloscope capabilities.

#### Scenario: Open electrical scope window
- **GIVEN** an electrical scope component exists on the schematic
- **WHEN** the user double-clicks the scope body or selects "Open Scope" from its context menu
- **THEN** a floating waveform viewer window SHALL open that is bound to that component and only shows the signals wired into its inputs

#### Scenario: One window per scope
- **GIVEN** multiple electrical scopes exist
- **THEN** each scope SHALL own an independent window with its own plot areas, cursors, and measurements while still sharing the global waveform viewer toolset

### Requirement: Scope Signal Configuration
Electrical scope windows SHALL respect the configuration defined on their schematic component.

#### Scenario: Input-to-plot mapping
- **GIVEN** a scope component exposes N inputs (1–8)
- **WHEN** the user opens the corresponding scope window
- **THEN** the viewer SHALL render N plot areas stacked vertically, one per input, unless the input is marked as "overlay" to combine traces

#### Scenario: Multiple traces per input
- **GIVEN** more than one wire is connected to the same scope input and the component is configured for overlay mode
- **THEN** all connected signals SHALL be drawn within that input's plot area and share the same time axis

#### Scenario: Custom trace names
- **GIVEN** a wire feeding a scope input has a user-defined alias
- **WHEN** the scope window displays that trace
- **THEN** the legend and measurement readouts SHALL use the alias instead of the raw node label

#### Scenario: Persist scope settings
- **GIVEN** the user adjusts cursor positions, axis settings, or overlay flags inside a scope window
- **THEN** those settings SHALL be saved with the project and restored with the same scope component on reload
