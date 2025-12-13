# Backend Abstraction

## Purpose

Provide a stable abstraction layer between the GUI and simulation backends, enabling backend versioning, hot-swapping, and graceful degradation.

## ADDED Requirements

### Requirement: Backend Capabilities Protocol

The application SHALL define a `BackendCapabilities` protocol that all simulation backends MUST implement.

#### Scenario: Protocol definition
- **GIVEN** a class implements `BackendCapabilities`
- **THEN** it MUST provide:
  - `info` property returning `BackendInfo`
  - `capabilities` property returning `set[str]`
  - `run_transient()` method for time-domain simulation
  - `run_dc()` method for DC operating point
  - `run_ac()` method for frequency analysis
  - `run_thermal()` method for thermal simulation
  - `has_capability()` method for feature detection

#### Scenario: Protocol compliance check
- **GIVEN** a backend instance
- **WHEN** `isinstance(backend, BackendCapabilities)` is called
- **THEN** it SHALL return True only if all required methods exist

#### Scenario: Missing capability handling
- **GIVEN** a backend that doesn't implement `run_ac()`
- **WHEN** `backend.has_capability("ac")` is called
- **THEN** it SHALL return False
- **AND** calling `run_ac()` SHALL raise `NotImplementedError`

### Requirement: Backend Version Management

The application SHALL track backend versions and ensure compatibility.

#### Scenario: Version parsing
- **GIVEN** a version string "0.2.1"
- **WHEN** `BackendVersion.from_string()` is called
- **THEN** it SHALL return a `BackendVersion` with major=0, minor=2, patch=1

#### Scenario: Compatibility check
- **GIVEN** current backend version 0.2.0 and minimum required 0.1.5
- **WHEN** `current.is_compatible_with(minimum)` is called
- **THEN** it SHALL return True

#### Scenario: Incompatibility detection
- **GIVEN** current backend version 0.1.0 and minimum required 0.2.0
- **WHEN** `current.is_compatible_with(minimum)` is called
- **THEN** it SHALL return False

#### Scenario: API version tracking
- **GIVEN** backends may have same version but different API
- **WHEN** a backend reports api_version=2
- **THEN** compatibility SHALL be checked against api_version, not just version string

### Requirement: Backend Registry

The application SHALL maintain a registry of available backends.

#### Scenario: Automatic discovery
- **GIVEN** the application starts
- **WHEN** the backend registry initializes
- **THEN** it SHALL discover:
  - Installed `pulsim` package (if available)
  - Entry points registered under `pulsimgui.backends`
  - Built-in `PlaceholderBackend`

#### Scenario: List available backends
- **GIVEN** the registry has discovered backends
- **WHEN** `registry.available_backends()` is called
- **THEN** it SHALL return a list of `BackendInfo` objects

#### Scenario: Activate backend
- **GIVEN** multiple backends are available
- **WHEN** `registry.activate("pulsim")` is called
- **THEN** the pulsim backend SHALL become active
- **AND** subsequent simulation calls SHALL use that backend

#### Scenario: Unknown backend error
- **GIVEN** no backend named "xyce" is registered
- **WHEN** `registry.activate("xyce")` is called
- **THEN** it SHALL raise `ValueError` with descriptive message

### Requirement: Backend Information Display

The application SHALL display information about the active backend.

#### Scenario: Backend info in status bar
- **GIVEN** the application is running
- **THEN** the status bar SHALL show the active backend name and version

#### Scenario: Backend info in About dialog
- **GIVEN** the user opens Help > About
- **THEN** the dialog SHALL display:
  - Backend name
  - Backend version
  - Backend location (path)
  - List of capabilities

#### Scenario: Backend selection in preferences
- **GIVEN** multiple backends are available
- **WHEN** the user opens Preferences > Backend
- **THEN** a dropdown SHALL list available backends
- **AND** the user SHALL be able to select a different backend

### Requirement: Result Type Abstraction

The application SHALL use backend-agnostic result types.

#### Scenario: DCResult structure
- **GIVEN** a DC analysis completes
- **WHEN** the backend returns results
- **THEN** they SHALL be converted to `DCResult` containing:
  - `node_voltages: dict[str, float]`
  - `branch_currents: dict[str, float]`
  - `power_dissipation: dict[str, float]`
  - `convergence_info: ConvergenceInfo`
  - `error_message: str`

#### Scenario: ACResult structure
- **GIVEN** an AC analysis completes
- **WHEN** the backend returns results
- **THEN** they SHALL be converted to `ACResult` containing:
  - `frequencies: list[float]`
  - `magnitude: dict[str, list[float]]`
  - `phase: dict[str, list[float]]`
  - `error_message: str`

#### Scenario: ThermalResult structure
- **GIVEN** a thermal analysis completes
- **WHEN** the backend returns results
- **THEN** they SHALL be converted to `ThermalResult` containing:
  - `time: list[float]`
  - `devices: list[ThermalDeviceResult]`
  - `ambient_temperature: float`
  - `is_synthetic: bool` (True if using placeholder)

### Requirement: Settings Type Abstraction

The application SHALL use backend-agnostic settings types.

#### Scenario: DCSettings structure
- **GIVEN** the user configures DC analysis
- **THEN** settings SHALL be stored in `DCSettings` containing:
  - `strategy: str` (auto, direct, gmin, source, pseudo)
  - `max_iterations: int`
  - `tolerance: float`
  - `enable_limiting: bool`
  - `max_voltage_step: float`

#### Scenario: Settings to backend conversion
- **GIVEN** `DCSettings` with strategy="gmin"
- **WHEN** passed to `PulsimBackend.run_dc()`
- **THEN** it SHALL be converted to `pulsim.v2.NewtonOptions`
- **AND** the correct GMIN stepping parameters SHALL be set

### Requirement: Graceful Degradation

The application SHALL degrade gracefully when backend features are unavailable.

#### Scenario: Missing DC capability
- **GIVEN** the backend doesn't support DC analysis
- **WHEN** the user tries to run DC analysis
- **THEN** an informative error SHALL be shown
- **AND** the menu item SHALL be disabled with tooltip

#### Scenario: Placeholder fallback
- **GIVEN** no real backend is installed
- **WHEN** the application starts
- **THEN** `PlaceholderBackend` SHALL be activated
- **AND** a banner SHALL indicate demo mode
- **AND** transient simulation SHALL work with synthetic data

#### Scenario: Partial capability
- **GIVEN** the backend supports transient but not AC
- **THEN** transient menu items SHALL be enabled
- **AND** AC menu items SHALL be disabled
- **AND** tooltip SHALL explain "AC analysis requires PulsimCore 0.3.0+"
