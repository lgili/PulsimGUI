## ADDED Requirements
### Requirement: Backend Adapter Discovery
The simulation control stack SHALL detect and load a compatible Pulsim backend implementation provided via pip.

#### Scenario: Automatic backend detection
- **WHEN** the GUI starts or the user opens Simulation Settings
- **THEN** the application SHALL scan installed `pulsimcore` distributions via `importlib.metadata` and select the newest compatible version
- **AND** the selected version SHALL be displayed in the settings/status UI

#### Scenario: Manual backend selection
- **GIVEN** multiple compatible backend builds are installed (e.g., stable + nightly)
- **WHEN** the user opens the backend selector in Simulation Settings
- **THEN** the user SHALL be able to choose which version to use and the choice SHALL persist per project/profile

#### Scenario: Missing or incompatible backend
- **GIVEN** no compatible backend is found or the adapter initialization fails
- **THEN** the Run/DC/AC controls SHALL be disabled and a warning SHALL explain how to install a supported backend

### Requirement: Backend-Driven Simulation Execution
The GUI SHALL execute all simulations through the selected backend adapter rather than synthetic placeholders.

#### Scenario: Transient simulation delegation
- **WHEN** the user runs a transient simulation
- **THEN** the simulation worker SHALL call the adapter's transient API with the converted circuit + settings, stream progress to the UI, and surface any backend exception via the existing error banner

#### Scenario: DC/AC analysis delegation
- **WHEN** the user runs DC or AC analysis
- **THEN** the adapter SHALL be invoked for the respective analysis and the GUI SHALL display the returned results (node voltages, frequency response) without additional mocking

#### Scenario: Parameter sweep delegation
- **WHEN** the user runs a parameter sweep with parallel workers enabled
- **THEN** the sweep manager SHALL reuse the adapter for every sweep point, propagating cancellation/pause/resume signals so backend threads stop promptly

#### Scenario: Version-aware feature gating
- **GIVEN** the selected backend lacks a required feature (e.g., AC analysis)
- **WHEN** the user attempts to start that analysis
- **THEN** the GUI SHALL block the action and present a message indicating which backend version introduces the missing API
