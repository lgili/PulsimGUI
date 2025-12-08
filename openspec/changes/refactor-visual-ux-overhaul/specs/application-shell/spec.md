## ADDED Requirements

### Requirement: Professional Toolbar Design

The application SHALL provide a modern, icon-based toolbar with professional visual design inspired by PLECS and Simulink.

#### Scenario: Icon-only toolbar mode
- **WHEN** the user views the main toolbar
- **THEN** the toolbar SHALL display:
  - Monochrome SVG icons with consistent sizing (20x20 or 24x24)
  - Subtle hover effect (background highlight, no border)
  - Visual grouping with thin separator lines
  - Tooltips with action name and keyboard shortcut

#### Scenario: Toolbar button states
- **GIVEN** any toolbar button
- **WHEN** the user interacts with it
- **THEN** the button SHALL show:
  - Hover state: subtle background highlight (8% opacity)
  - Pressed state: slightly darker background (12% opacity)
  - Disabled state: reduced opacity (40%)
  - Active/checked state: accent color background

### Requirement: Quick-Add Command Palette

The application SHALL provide a command palette for fast component insertion and action execution.

#### Scenario: Opening command palette
- **WHEN** the user presses Cmd+K (macOS) or Ctrl+K (Windows/Linux)
- **THEN** a command palette SHALL appear:
  - Centered modal overlay with search input
  - Dark semi-transparent backdrop
  - Smooth fade-in animation (150ms)

#### Scenario: Searching for components
- **GIVEN** the command palette is open
- **WHEN** the user types a search query
- **THEN** the palette SHALL:
  - Show matching components with symbol preview
  - Highlight matched characters in results
  - Allow arrow key navigation
  - Insert selected component at cursor position on Enter

#### Scenario: Searching for actions
- **GIVEN** the command palette is open
- **WHEN** the user types ">" followed by an action name
- **THEN** the palette SHALL show matching menu actions with their shortcuts

### Requirement: Enhanced Status Bar

The application SHALL provide a segmented status bar with visual indicators and interactive elements.

#### Scenario: Status bar layout
- **WHEN** the application is running
- **THEN** the status bar SHALL display:
  - Left section: coordinates, zoom level, selection count
  - Center section: simulation status with colored indicator
  - Right section: modification status, file name

#### Scenario: Simulation status indicator
- **GIVEN** the application is running
- **THEN** the simulation status indicator SHALL show:
  - Idle: gray circle
  - Running: pulsing green circle with animation
  - Paused: amber circle
  - Error: red circle with warning icon

#### Scenario: Interactive zoom control
- **WHEN** the user clicks on the zoom percentage in status bar
- **THEN** a zoom slider popup SHALL appear for precise zoom control

### Requirement: Refined Dock Panel Design

The application SHALL provide dock panels with modern, refined visual design.

#### Scenario: Panel header styling
- **WHEN** viewing any dock panel
- **THEN** the panel header SHALL have:
  - Subtle gradient background
  - Semi-bold title text
  - Hover-revealed close/float buttons
  - 1px bottom border in theme accent

#### Scenario: Panel resize handles
- **WHEN** the user hovers over a panel resize edge
- **THEN** the resize handle SHALL:
  - Show a visible grab indicator (3 dots or lines)
  - Change cursor to resize cursor
  - Highlight with subtle accent color

#### Scenario: Panel collapse animation
- **WHEN** the user collapses a dock panel
- **THEN** the panel SHALL animate smoothly (200ms ease-out)

## MODIFIED Requirements

### Requirement: Theme Support

The application SHALL support multiple color themes with refined, professional color palettes.

#### Scenario: Light theme
- **GIVEN** the user selects Light theme
- **THEN** the application SHALL use:
  - Clean white backgrounds (#FFFFFF)
  - Subtle gray borders (#E5E7EB)
  - High-contrast text (#1F2937)
  - Blue accent color (#2563EB)
  - Professional, minimalist appearance

#### Scenario: Dark theme
- **GIVEN** the user selects Dark theme
- **THEN** the application SHALL use:
  - Deep gray background (#18181B)
  - Subtle borders (#27272A)
  - Comfortable text contrast (#FAFAFA)
  - Blue accent color (#3B82F6)
  - Reduced eye strain for long sessions

#### Scenario: Modern Dark theme
- **GIVEN** the user selects Modern Dark theme
- **THEN** the application SHALL use:
  - GitHub-style deep blue-black (#0D1117)
  - Subtle purple-tinted grays
  - High readability text (#C9D1D9)
  - Cyan/blue accent colors (#58A6FF)
  - Premium, developer-focused aesthetic

#### Scenario: Smooth theme transitions
- **WHEN** the user switches themes
- **THEN** all UI elements SHALL transition smoothly (no visual glitches or artifacts)
