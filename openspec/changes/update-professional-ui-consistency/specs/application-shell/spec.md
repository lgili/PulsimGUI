## ADDED Requirements

### Requirement: Unified Theme Propagation

The application SHALL propagate the active theme to all shell-managed visual surfaces, including custom widgets and non-QSS renderers.

#### Scenario: Runtime theme switch updates all shell surfaces
- **GIVEN** the main window is open with library, properties, schematic, minimap, waveform, and thermal views available
- **WHEN** the user switches from one built-in theme to another
- **THEN** all visible shell-managed surfaces SHALL update in the same interaction without requiring restart
- **AND** no previously active theme colors SHALL remain visible in updated widgets

#### Scenario: Theme reapplication after layout restore
- **GIVEN** a saved dock layout is restored on application startup
- **WHEN** the current theme is applied
- **THEN** restored docks and their child widgets SHALL render using current theme tokens

### Requirement: Workflow-Centric Toolbar Layout

The main toolbar SHALL prioritize frequent simulation workflows while preserving access to all existing commands.

#### Scenario: Default toolbar grouping
- **GIVEN** the application starts with default layout
- **THEN** toolbar actions SHALL be grouped by workflow with simulation controls in a persistent, high-visibility group
- **AND** separators SHALL communicate group boundaries clearly

#### Scenario: Overflow behavior on narrow windows
- **GIVEN** the main window width is constrained
- **WHEN** toolbar space becomes insufficient
- **THEN** lower-frequency actions SHALL move into overflow first
- **AND** primary simulation controls SHALL remain directly accessible

### Requirement: Tokenized Visual Governance

Shell-level UI modules touched by this change SHALL source visual colors from centralized theme tokens.

#### Scenario: Shell widget styling source
- **GIVEN** shell widgets are updated or newly introduced under this change
- **WHEN** visual styling is applied
- **THEN** color decisions SHALL come from `ThemeService` tokens or theme adapters
- **AND** hardcoded local color literals SHALL NOT be introduced except for approved domain palettes
