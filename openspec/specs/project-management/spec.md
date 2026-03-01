# Project Management

## Purpose

File management, project structure, and data persistence for circuit designs and simulation results.

## Requirements

### Requirement: Project Structure

The application SHALL organize circuit designs in a project-based structure.

#### Scenario: New project creation
- **GIVEN** the user selects File > New Project
- **THEN** a dialog SHALL prompt for:
  - Project name
  - Project location
  - Optional template selection

#### Scenario: Project folder structure
- **GIVEN** a new project is created
- **THEN** the following structure SHALL be created:
  ```
  project_name/
  ├── project_name.pulsim       # Main project file (JSON)
  ├── schematics/               # Schematic files
  │   └── main.sch              # Default schematic
  ├── simulations/              # Simulation configurations
  ├── results/                  # Simulation results
  ├── library/                  # Custom components
  └── docs/                     # Documentation/notes
  ```

#### Scenario: Project file format
- **GIVEN** a project is saved
- **THEN** the `.pulsim` file SHALL contain:
  - Project metadata (name, version, created date)
  - List of schematics
  - Simulation configurations
  - UI state (layout, open files)

### Requirement: Schematic Files

The application SHALL save schematics in a readable format.

#### Scenario: Save schematic
- **GIVEN** a schematic is modified
- **WHEN** the user saves (Ctrl+S)
- **THEN** the schematic SHALL be saved to a `.sch` file

#### Scenario: Schematic file format
- **GIVEN** a schematic is saved
- **THEN** the file SHALL be JSON with:
  - Format version number
  - Components with positions, orientations, and parameters
  - Wires with connection points
  - Node names and probe positions
  - Viewport state (zoom, pan)

#### Scenario: Human-readable format
- **GIVEN** a schematic file
- **THEN** the JSON SHALL be:
  - Pretty-printed with indentation
  - Use meaningful key names
  - Include comments where helpful

### Requirement: Auto-Save

The application SHALL protect against data loss.

#### Scenario: Auto-save interval
- **GIVEN** auto-save is enabled in preferences
- **THEN** the project SHALL be auto-saved every N minutes (configurable)

#### Scenario: Auto-save location
- **GIVEN** auto-save triggers
- **THEN** the backup SHALL be saved to:
  - `.pulsim_backup/` folder within the project
  - Named with timestamp: `schematic_20231215_143022.sch.bak`

#### Scenario: Auto-save indicator
- **GIVEN** auto-save occurs
- **THEN** a subtle indicator SHALL show in the status bar

### Requirement: File Operations

The application SHALL support standard file operations.

#### Scenario: Open project
- **GIVEN** the user selects File > Open Project
- **WHEN** a `.pulsim` file is selected
- **THEN**:
  - The project SHALL load
  - Recent projects list SHALL update
  - Last opened schematics SHALL restore

#### Scenario: Recent projects
- **GIVEN** projects have been opened
- **WHEN** the user opens File > Open Recent
- **THEN** the last 10 projects SHALL be listed with full paths

#### Scenario: Save As
- **GIVEN** a project is open
- **WHEN** the user selects File > Save As
- **THEN** a new project folder SHALL be created as a copy

#### Scenario: Close project
- **GIVEN** a project is open with unsaved changes
- **WHEN** the user closes the project
- **THEN** a dialog SHALL prompt to save changes

### Requirement: Import/Export

The application SHALL support interoperability with other formats.

#### Scenario: Export to SPICE netlist
- **GIVEN** a schematic is open
- **WHEN** the user selects File > Export > SPICE Netlist
- **THEN** a `.cir` or `.sp` file SHALL be generated with:
  - Component instantiations
  - Node names
  - Model definitions
  - Simulation commands (optional)

#### Scenario: Import SPICE netlist
- **GIVEN** the user selects File > Import > SPICE Netlist
- **WHEN** a valid SPICE file is selected
- **THEN**:
  - Components SHALL be created from the netlist
  - Auto-layout SHALL position components
  - A review dialog SHALL allow adjustments

#### Scenario: Export to JSON netlist
- **GIVEN** a schematic is open
- **WHEN** the user exports to JSON
- **THEN** a Pulsim-compatible JSON netlist SHALL be generated

#### Scenario: Export schematic image
- **GIVEN** a schematic is open
- **WHEN** the user selects File > Export > Image
- **THEN** options SHALL include:
  - PNG (with resolution selection)
  - SVG (vector format)
  - PDF (with page size options)

### Requirement: Template System

The application SHALL provide starter templates for common circuits.

#### Scenario: New from template
- **GIVEN** the user selects File > New from Template
- **THEN** available templates SHALL include:
  - Empty schematic
  - Buck converter
  - Boost converter
  - Full-bridge inverter
  - Three-phase inverter
  - LLC resonant converter
  - Active PFC

#### Scenario: Custom template creation
- **GIVEN** a circuit is designed
- **WHEN** the user selects File > Save as Template
- **THEN**:
  - A dialog SHALL prompt for template name and category
  - The template SHALL appear in the template list

### Requirement: Version Control Integration

The application SHALL support Git integration for project versioning.

#### Scenario: Git status display
- **GIVEN** a project is in a Git repository
- **THEN** the application SHALL:
  - Show modified files indicator
  - Display current branch name
  - Indicate uncommitted changes

#### Scenario: Diff-friendly format
- **GIVEN** schematics are saved
- **THEN** the file format SHALL:
  - Use consistent key ordering
  - Avoid unnecessary changes between saves
  - Support meaningful diffs

### Requirement: Search Across Project

The application SHALL support searching within the project.

#### Scenario: Find component in project
- **GIVEN** the user presses Ctrl+Shift+F
- **THEN** a project-wide search SHALL:
  - Search component names across all schematics
  - Search component values
  - Show results with file and location

#### Scenario: Navigate to search result
- **GIVEN** search results are displayed
- **WHEN** the user clicks a result
- **THEN** the schematic SHALL open and center on that component

### Requirement: Project Explorer Panel

The application SHALL provide a project explorer for navigation.

#### Scenario: Project tree view
- **GIVEN** a project is open
- **THEN** the project explorer SHALL show:
  - Project name as root
  - Schematics folder
  - Simulation configurations
  - Results folder
  - Custom library items

#### Scenario: Open schematic from explorer
- **GIVEN** the project explorer is visible
- **WHEN** the user double-clicks a schematic
- **THEN** the schematic SHALL open in the editor

#### Scenario: Context menu operations
- **GIVEN** an item in the project explorer
- **WHEN** the user right-clicks
- **THEN** context-appropriate options SHALL appear:
  - Rename
  - Delete
  - Duplicate
  - Properties

### Requirement: Multiple Schematics

The application SHALL support multiple schematics per project.

#### Scenario: Create new schematic
- **GIVEN** a project is open
- **WHEN** the user selects File > New Schematic
- **THEN** a new schematic SHALL be created in the project

#### Scenario: Tabbed schematic editing
- **GIVEN** multiple schematics are open
- **THEN** tabs SHALL allow switching between schematics

#### Scenario: Schematic cross-reference
- **GIVEN** schematics share subcircuits
- **THEN** navigating to a subcircuit SHALL open the relevant schematic

### Requirement: Simulation Results Management

The application SHALL manage simulation result files.

#### Scenario: Save results with project
- **GIVEN** a simulation completes
- **THEN** results MAY be saved to the `results/` folder

#### Scenario: Results file format
- **GIVEN** results are saved
- **THEN** options SHALL include:
  - Internal binary format (fast load)
  - HDF5 (large data, compression)
  - CSV (interoperability)

#### Scenario: Clear old results
- **GIVEN** many result files exist
- **WHEN** the user selects Project > Clean Results
- **THEN** old result files SHALL be deleted (with confirmation)

### Requirement: Project Settings

Each project SHALL have configurable settings.

#### Scenario: Project settings dialog
- **GIVEN** the user selects Project > Settings
- **THEN** options SHALL include:
  - Default simulation parameters
  - Default output directory
  - Unit system preferences
  - Component naming prefix

#### Scenario: Default component library
- **GIVEN** project settings are open
- **THEN** the user SHALL be able to specify:
  - Additional component library paths
  - Default device models

### Requirement: Backup and Recovery

The application SHALL provide robust data protection.

#### Scenario: Backup on save
- **GIVEN** a file is saved
- **THEN** the previous version SHALL be backed up to `.pulsim_backup/`

#### Scenario: Backup retention
- **GIVEN** backups exist
- **THEN** the last N backups per file SHALL be retained (configurable)

#### Scenario: Recovery from backup
- **GIVEN** the user selects File > Restore from Backup
- **THEN** a dialog SHALL list available backups with timestamps

#### Scenario: Crash recovery
- **GIVEN** the application crashed with unsaved changes
- **WHEN** the application restarts
- **THEN** a recovery dialog SHALL offer to restore the session
