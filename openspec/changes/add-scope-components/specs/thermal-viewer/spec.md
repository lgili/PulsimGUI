## ADDED Requirements
### Requirement: Thermal Scope Windows
Thermal scope components SHALL open dedicated thermal viewer windows with device temperature and loss plots.

#### Scenario: Open thermal scope window
- **GIVEN** a thermal scope component is placed and connected to device thermal pins or loss signals
- **WHEN** the user double-clicks the component
- **THEN** a floating thermal viewer window SHALL open showing temperature and loss traces for the connected signals only

#### Scenario: Matching input layout
- **GIVEN** the thermal scope is configured for N inputs
- **THEN** the thermal scope window SHALL create N plot tabs/areas with the same grouping (separate vs overlay) configured on the component

#### Scenario: Alias-aware labels
- **GIVEN** a user-defined alias exists on a thermal wire feeding the scope
- **THEN** the thermal scope window SHALL display that alias in legends, tables, and exported data

#### Scenario: Independent persistence
- **GIVEN** multiple thermal scopes exist
- **THEN** each scope SHALL persist its window geometry, selected tabs, and axis ranges independently inside the project file
