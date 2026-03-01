## ADDED Requirements

### Requirement: Main Window Layout

The application SHALL provide a main window with a dockable panel layout that allows users to customize their workspace.

#### Scenario: Default layout on first launch
- **GIVEN** the application is launched for the first time
- **WHEN** the main window appears
- **THEN** the default layout SHALL show:
  - Component Library panel on the left (250px width)
  - Schematic Editor in the center (expandable)
  - Properties Panel on the right (300px width)
  - Waveform Viewer at the bottom (300px height, collapsed by default)
  - Toolbar at the top
  - Status bar at the bottom

### Requirement: Menu Bar Structure

The application SHALL provide a comprehensive menu bar for all operations.

#### Scenario: File menu operations
- **GIVEN** the user opens the File menu
- **THEN** the following items SHALL be available:
  - New Project (Ctrl+N)
  - Open Project (Ctrl+O)
  - Open Recent (submenu with last 10 projects)
  - Save (Ctrl+S)
  - Save As (Ctrl+Shift+S)
  - Export Netlist (Ctrl+E)
  - Export Image (PNG, SVG, PDF)
  - Close Project
  - Exit (Ctrl+Q)

### Requirement: Toolbar

The application SHALL provide a toolbar with frequently used actions.

#### Scenario: Main toolbar contents
- **GIVEN** the application is running
- **THEN** the main toolbar SHALL contain:
  - New, Open, Save buttons
  - Undo, Redo buttons
  - Cut, Copy, Paste buttons
  - Zoom controls (in, out, fit)
  - Selection tool
  - Wire tool
  - Run/Stop simulation buttons
  - Simulation progress indicator

### Requirement: Status Bar

The application SHALL provide a status bar showing contextual information.

#### Scenario: Status bar content during editing
- **GIVEN** the user is editing a schematic
- **THEN** the status bar SHALL display:
  - Current mouse position (grid coordinates)
  - Zoom level percentage
  - Selected component count
  - Current tool name
  - Schematic modification status (saved/unsaved)

### Requirement: Keyboard Shortcuts

The application SHALL support comprehensive keyboard shortcuts for power users.

#### Scenario: Global shortcuts
- **GIVEN** the application has focus
- **WHEN** the user presses a registered shortcut
- **THEN** the corresponding action SHALL execute regardless of which panel has focus

### Requirement: Theme Support

The application SHALL support multiple color themes.

#### Scenario: Light and dark themes
- **GIVEN** the user selects a theme
- **THEN** the application SHALL switch between light and dark color schemes

### Requirement: Application Preferences

The application SHALL provide a preferences dialog for user settings.

#### Scenario: General preferences
- **GIVEN** the user opens Preferences
- **THEN** the General tab SHALL include configurable options for project location, auto-save, and language

### Requirement: Multi-Window Support

The application SHALL support multiple windows for comparing designs.

#### Scenario: Open project in new window
- **GIVEN** a project is already open
- **WHEN** the user selects File > Open in New Window
- **THEN** a new application window SHALL open with the selected project

### Requirement: Crash Recovery

The application SHALL protect user work from unexpected crashes.

#### Scenario: Auto-save backup
- **GIVEN** auto-save is enabled
- **WHEN** the auto-save interval elapses
- **THEN** the application SHALL save a backup copy without overwriting the original
