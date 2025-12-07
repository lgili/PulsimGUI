## ADDED Requirements

### Requirement: Project Structure

The application SHALL organize circuit designs in a project-based structure.

#### Scenario: New project creation
- **GIVEN** the user selects File > New Project
- **THEN** a dialog SHALL prompt for project name and location

### Requirement: Schematic Files

The application SHALL save schematics in a readable format.

#### Scenario: Save schematic
- **GIVEN** a schematic is modified
- **WHEN** the user saves
- **THEN** the schematic SHALL be saved as JSON with components, wires, and probes

### Requirement: Auto-Save

The application SHALL protect against data loss.

#### Scenario: Auto-save interval
- **GIVEN** auto-save is enabled in preferences
- **THEN** the project SHALL be auto-saved every N minutes to a backup location

### Requirement: File Operations

The application SHALL support standard file operations.

#### Scenario: Open project
- **GIVEN** the user selects File > Open Project
- **WHEN** a .pulsim file is selected
- **THEN** the project SHALL load and recent projects list SHALL update

### Requirement: Import/Export

The application SHALL support interoperability with other formats.

#### Scenario: Export to SPICE netlist
- **GIVEN** a schematic is open
- **WHEN** the user selects Export > SPICE Netlist
- **THEN** a SPICE-compatible netlist file SHALL be generated

### Requirement: Template System

The application SHALL provide starter templates for common circuits.

#### Scenario: New from template
- **GIVEN** the user selects File > New from Template
- **THEN** available templates SHALL include buck, boost, full-bridge, and LLC converters

### Requirement: Version Control Integration

The application SHALL support Git integration for project versioning.

#### Scenario: Git status display
- **GIVEN** a project is in a Git repository
- **THEN** the application SHALL show modified files and current branch

### Requirement: Search Across Project

The application SHALL support searching within the project.

#### Scenario: Find component in project
- **GIVEN** the user presses Ctrl+Shift+F
- **THEN** a project-wide search SHALL search component names across all schematics

### Requirement: Project Explorer Panel

The application SHALL provide a project explorer for navigation.

#### Scenario: Project tree view
- **GIVEN** a project is open
- **THEN** the project explorer SHALL show schematics, simulations, and results folders

### Requirement: Multiple Schematics

The application SHALL support multiple schematics per project.

#### Scenario: Create new schematic
- **GIVEN** a project is open
- **WHEN** the user selects File > New Schematic
- **THEN** a new schematic SHALL be created in the project

### Requirement: Simulation Results Management

The application SHALL manage simulation result files.

#### Scenario: Save results with project
- **GIVEN** a simulation completes
- **THEN** results MAY be saved to the results folder in various formats

### Requirement: Project Settings

Each project SHALL have configurable settings.

#### Scenario: Project settings dialog
- **GIVEN** the user selects Project > Settings
- **THEN** options SHALL include default simulation parameters and component library paths

### Requirement: Backup and Recovery

The application SHALL provide robust data protection.

#### Scenario: Crash recovery
- **GIVEN** the application crashed with unsaved changes
- **WHEN** the application restarts
- **THEN** a recovery dialog SHALL offer to restore the session
