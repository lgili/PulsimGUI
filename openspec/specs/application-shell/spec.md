# Application Shell

## Purpose

The main application window that hosts all other components and provides the overall user interface structure.

## Requirements

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

#### Scenario: Panel docking and floating
- **GIVEN** the user is in the main window
- **WHEN** the user drags a panel by its title bar
- **THEN** the panel SHALL:
  - Show docking guides when near edges
  - Snap to valid dock positions
  - Float as a separate window if dropped outside dock areas
  - Remember its position on application restart

#### Scenario: Panel visibility toggle
- **GIVEN** any panel is visible
- **WHEN** the user clicks the panel's close button or uses View menu
- **THEN** the panel SHALL hide and be restorable from the View menu

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

#### Scenario: Edit menu operations
- **GIVEN** the user opens the Edit menu
- **THEN** the following items SHALL be available:
  - Undo (Ctrl+Z) with action description
  - Redo (Ctrl+Y / Ctrl+Shift+Z)
  - Cut (Ctrl+X)
  - Copy (Ctrl+C)
  - Paste (Ctrl+V)
  - Delete (Del)
  - Select All (Ctrl+A)
  - Find Component (Ctrl+F)
  - Preferences (Ctrl+,)

#### Scenario: View menu operations
- **GIVEN** the user opens the View menu
- **THEN** the following items SHALL be available:
  - Zoom In (Ctrl++)
  - Zoom Out (Ctrl+-)
  - Zoom to Fit (Ctrl+0)
  - Zoom to Selection
  - Toggle Grid (G)
  - Toggle Snap to Grid
  - Panel visibility toggles for each panel
  - Theme selection (Light, Dark, System)

#### Scenario: Simulation menu operations
- **GIVEN** the user opens the Simulation menu
- **THEN** the following items SHALL be available:
  - Run Simulation (F5)
  - Stop Simulation (Shift+F5)
  - Pause/Resume Simulation
  - DC Operating Point (F6)
  - AC Analysis (F7)
  - Parameter Sweep
  - Simulation Settings

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

#### Scenario: Toolbar customization
- **GIVEN** the user right-clicks on the toolbar
- **WHEN** the context menu appears
- **THEN** the user SHALL be able to:
  - Show/hide individual toolbars
  - Reset to default layout

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

#### Scenario: Status bar content during simulation
- **GIVEN** a simulation is running
- **THEN** the status bar SHALL display:
  - Simulation progress (time / total time)
  - Progress bar
  - Estimated time remaining
  - Current Newton iterations per step

### Requirement: Keyboard Shortcuts

The application SHALL support comprehensive keyboard shortcuts for power users.

#### Scenario: Global shortcuts
- **GIVEN** the application has focus
- **WHEN** the user presses a registered shortcut
- **THEN** the corresponding action SHALL execute regardless of which panel has focus

#### Scenario: Shortcut customization
- **GIVEN** the user opens Preferences > Keyboard Shortcuts
- **THEN** the user SHALL be able to:
  - View all shortcuts grouped by category
  - Search for shortcuts by action name
  - Modify any shortcut
  - Reset to defaults
  - Detect conflicts

### Requirement: Theme Support

The application SHALL support multiple color themes.

#### Scenario: Light theme
- **GIVEN** the user selects Light theme
- **THEN** the application SHALL use:
  - Light background colors
  - Dark text
  - High contrast component symbols
  - Eye-friendly color palette

#### Scenario: Dark theme
- **GIVEN** the user selects Dark theme
- **THEN** the application SHALL use:
  - Dark background colors (#1e1e1e or similar)
  - Light text
  - Adjusted component colors for visibility
  - Reduced eye strain for long sessions

#### Scenario: System theme following
- **GIVEN** the user selects "Follow System" theme option
- **WHEN** the operating system theme changes
- **THEN** the application SHALL automatically switch themes

### Requirement: Application Preferences

The application SHALL provide a preferences dialog for user settings.

#### Scenario: General preferences
- **GIVEN** the user opens Preferences
- **THEN** the General tab SHALL include:
  - Default project location
  - Auto-save interval (1-60 minutes, or disabled)
  - Language selection
  - Check for updates option
  - Recent files count (5-20)

#### Scenario: Editor preferences
- **GIVEN** the user opens Preferences > Editor
- **THEN** the tab SHALL include:
  - Grid size (1mm, 2.5mm, 5mm, 10mm)
  - Snap to grid enabled/disabled
  - Default wire style (orthogonal, diagonal, free)
  - Component label visibility
  - Pin name visibility

#### Scenario: Simulation preferences
- **GIVEN** the user opens Preferences > Simulation
- **THEN** the tab SHALL include:
  - Default simulation time
  - Default timestep
  - Solver tolerances
  - Maximum Newton iterations
  - Integration method selection

### Requirement: Multi-Window Support

The application SHALL support multiple windows for comparing designs.

#### Scenario: Open project in new window
- **GIVEN** a project is already open
- **WHEN** the user selects File > Open in New Window
- **THEN** a new application window SHALL open with the selected project

#### Scenario: Window management
- **GIVEN** multiple windows are open
- **THEN** the Window menu SHALL list all open windows and allow switching between them

### Requirement: Crash Recovery

The application SHALL protect user work from unexpected crashes.

#### Scenario: Auto-save backup
- **GIVEN** auto-save is enabled
- **WHEN** the auto-save interval elapses
- **THEN** the application SHALL:
  - Save a backup copy without overwriting the original
  - Store backups in a dedicated recovery folder
  - Keep the last 3 backups per project

#### Scenario: Recovery on restart
- **GIVEN** the application crashed with unsaved changes
- **WHEN** the application restarts
- **THEN** a recovery dialog SHALL:
  - List recoverable projects
  - Show last modification time
  - Allow user to restore or discard each backup
