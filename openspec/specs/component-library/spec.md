# Component Library

## Purpose

A hierarchical, searchable library of circuit components with visual previews and categorized organization.

## Requirements

### Requirement: Library Panel Structure

The component library SHALL be displayed as a dockable panel with hierarchical categories.

#### Scenario: Default panel position
- **GIVEN** the application launches with default layout
- **THEN** the component library SHALL appear as a docked panel on the left side

#### Scenario: Category tree structure
- **GIVEN** the library panel is visible
- **THEN** components SHALL be organized in a tree with these categories:
  - **Sources**
    - Voltage Sources
    - Current Sources
  - **Passive Components**
    - Resistors
    - Capacitors
    - Inductors
  - **Semiconductors**
    - Diodes
    - MOSFETs
    - IGBTs
  - **Switches**
    - Ideal Switch
    - Controlled Switch
  - **Transformers**
    - Ideal Transformer
    - Real Transformer
  - **Control Blocks**
    - Math Operations
    - Signal Sources
    - PI/PID Controllers
    - PWM Generators
  - **Probes & Meters**
    - Voltage Probe
    - Current Probe
    - Power Meter
  - **Connectors**
    - Ground
    - Node Label
    - Subcircuit Port

#### Scenario: Category expand/collapse
- **GIVEN** a category is in the tree
- **WHEN** the user clicks the expand arrow or double-clicks the category name
- **THEN** the category SHALL expand to show its components

### Requirement: Component Display

Each component in the library SHALL show relevant information for identification.

#### Scenario: Component item display
- **GIVEN** a category is expanded
- **THEN** each component item SHALL show:
  - Component icon (schematic symbol preview)
  - Component name
  - Brief description (tooltip on hover)

#### Scenario: Icon preview
- **GIVEN** a component is visible in the library
- **THEN** its icon SHALL be a miniature version of its schematic symbol

#### Scenario: Hover tooltip
- **GIVEN** the user hovers over a component
- **THEN** a tooltip SHALL appear showing:
  - Full component name
  - Description
  - Number of pins
  - Keyboard shortcut (if assigned)

### Requirement: Search Functionality

The library SHALL provide fast search to find components.

#### Scenario: Search box location
- **GIVEN** the library panel is visible
- **THEN** a search box SHALL be at the top of the panel

#### Scenario: Incremental search
- **GIVEN** the user types in the search box
- **WHEN** text is entered
- **THEN** the library SHALL filter to show only matching components in real-time

#### Scenario: Search matching
- **GIVEN** the user searches for "cap"
- **THEN** the results SHALL include:
  - "Capacitor" (name match)
  - Any component with "cap" in description
  - Categories are hidden if they have no matches

#### Scenario: Clear search
- **GIVEN** text is in the search box
- **WHEN** the user clicks the X button or presses Escape
- **THEN** the search SHALL clear and full library SHALL be restored

### Requirement: Drag and Drop

Components SHALL be placeable via drag and drop from the library.

#### Scenario: Drag start
- **GIVEN** a component is in the library
- **WHEN** the user starts dragging it
- **THEN**:
  - A drag preview (ghost image) SHALL appear
  - The cursor SHALL change to indicate dragging

#### Scenario: Drag over schematic
- **GIVEN** a component is being dragged
- **WHEN** the cursor is over the schematic canvas
- **THEN**:
  - A placement preview SHALL show where the component will be placed
  - The preview SHALL snap to grid if snap is enabled

#### Scenario: Drop to place
- **GIVEN** a component is being dragged over the canvas
- **WHEN** the user releases the mouse button
- **THEN**:
  - The component SHALL be placed at that position
  - The component SHALL receive a unique name
  - The action SHALL be undoable

#### Scenario: Drag outside valid area
- **GIVEN** a component is being dragged
- **WHEN** the cursor is outside the schematic canvas
- **THEN** the cursor SHALL indicate placement is not possible

### Requirement: Quick Placement Shortcuts

Power users SHALL be able to place components via keyboard.

#### Scenario: Single-key shortcuts
- **GIVEN** the schematic editor has focus
- **WHEN** the user presses a component shortcut key
- **THEN** that component SHALL begin placement at the cursor

#### Scenario: Default shortcuts
- **GIVEN** default keyboard settings
- **THEN** the following shortcuts SHALL be assigned:
  - R - Resistor
  - C - Capacitor
  - L - Inductor
  - D - Diode
  - V - Voltage Source
  - I - Current Source
  - G - Ground
  - W - Wire tool
  - M - MOSFET
  - S - Switch
  - P - Probe

#### Scenario: Shortcut customization
- **GIVEN** the user opens Preferences > Keyboard Shortcuts
- **THEN** the user SHALL be able to reassign component shortcuts

### Requirement: Favorites

Users SHALL be able to mark frequently used components as favorites.

#### Scenario: Add to favorites
- **GIVEN** a component is in the library
- **WHEN** the user right-clicks and selects "Add to Favorites"
- **THEN** the component SHALL appear in a "Favorites" category at the top

#### Scenario: Favorites category
- **GIVEN** favorites have been added
- **THEN** the "Favorites" category SHALL:
  - Appear at the top of the library tree
  - Be expanded by default
  - Allow reordering via drag

#### Scenario: Remove from favorites
- **GIVEN** a component is in favorites
- **WHEN** the user right-clicks and selects "Remove from Favorites"
- **THEN** the component SHALL be removed from the favorites list

### Requirement: Recent Components

The library SHALL track recently used components.

#### Scenario: Recent category
- **GIVEN** components have been placed
- **THEN** a "Recent" category SHALL show the last 10 unique components used

#### Scenario: Recent ordering
- **GIVEN** the Recent category exists
- **THEN** components SHALL be ordered by last use time, most recent first

### Requirement: Component Variants

Some components SHALL offer multiple variants or models.

#### Scenario: Expand variants
- **GIVEN** a component has variants (e.g., MOSFET has NMOS, PMOS)
- **WHEN** the user expands the component
- **THEN** the variants SHALL be shown as sub-items

#### Scenario: Device library access
- **GIVEN** a component category is expanded
- **WHEN** the user sees a "Device Library" item
- **THEN** clicking it SHALL open a dialog with pre-configured devices (e.g., IRF540N, 1N4007)

### Requirement: Custom Components

Users SHALL be able to add custom components from subcircuits.

#### Scenario: Add subcircuit to library
- **GIVEN** a subcircuit has been created
- **WHEN** the user right-clicks and selects "Add to Library"
- **THEN** a dialog SHALL prompt for:
  - Category placement
  - Display name
  - Icon (auto-generated or custom)

#### Scenario: Custom category
- **GIVEN** custom components exist
- **THEN** a "Custom" category SHALL contain user-added components

#### Scenario: Import component library
- **GIVEN** the user selects File > Import Component Library
- **WHEN** a valid library file is selected
- **THEN** the components SHALL be added to a new category

### Requirement: Component Information

Users SHALL be able to view detailed component information.

#### Scenario: Component info panel
- **GIVEN** a component is selected in the library
- **WHEN** the user presses F1 or right-clicks and selects "Component Info"
- **THEN** an info panel SHALL show:
  - Full description
  - Available parameters with defaults
  - Schematic symbol (larger view)
  - SPICE model information
  - Usage notes

#### Scenario: Parameter preview
- **GIVEN** a component is hovered in the library
- **THEN** the properties panel MAY show a preview of the component's parameters

### Requirement: Visual Consistency

Component symbols SHALL follow consistent visual standards.

#### Scenario: Symbol standards
- **GIVEN** any component symbol
- **THEN** the symbol SHALL:
  - Use consistent line weights
  - Use standard schematic conventions (IEEE/IEC)
  - Have clearly marked pins
  - Scale appropriately with zoom

#### Scenario: Dark mode symbols
- **GIVEN** dark mode is active
- **THEN** component symbols SHALL use appropriate colors for visibility

### Requirement: Power Electronics Focus

The library SHALL emphasize power electronics components.

#### Scenario: Power device prominence
- **GIVEN** the default library view
- **THEN** power electronics components (MOSFETs, IGBTs, diodes, transformers) SHALL be easily accessible

#### Scenario: Loss model indication
- **GIVEN** a component supports loss calculation
- **THEN** an indicator (icon or badge) SHALL show this capability

#### Scenario: Thermal model indication
- **GIVEN** a component supports thermal modeling
- **THEN** an indicator SHALL show this capability
