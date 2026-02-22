## ADDED Requirements

### Requirement: Backend Runtime Provisioning

The application SHALL provide a built-in way to configure and provision the Python simulation backend version.

#### Scenario: Configure target backend version
- **GIVEN** the user opens Preferences > Simulation
- **WHEN** the user sets a target backend version (for example `v0.3.0`)
- **THEN** the version preference SHALL be persisted
- **AND** the runtime manager SHALL normalize the version string for installation (`0.3.0`)

#### Scenario: Install backend from GUI
- **GIVEN** runtime backend settings are configured
- **WHEN** the user clicks install/update backend in Preferences
- **THEN** the application SHALL run backend installation using the active Python runtime
- **AND** report success/failure with a user-facing status message

#### Scenario: Startup backend synchronization
- **GIVEN** backend auto-sync is enabled
- **AND** a target backend version is configured
- **WHEN** the application starts
- **THEN** the runtime manager SHALL verify installed backend version
- **AND** install/update backend when it does not match the target version

#### Scenario: Local PulsimCore source support
- **GIVEN** backend source is configured as local checkout
- **WHEN** the user selects a local PulsimCore path and installs backend
- **THEN** the runtime manager SHALL install backend from the selected local path
- **AND** validate that the selected path exists before installation
