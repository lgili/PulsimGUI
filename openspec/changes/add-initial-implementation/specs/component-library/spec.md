## ADDED Requirements

### Requirement: Library Panel Structure

The component library SHALL be displayed as a dockable panel with hierarchical categories.

#### Scenario: Category tree structure
- **GIVEN** the library panel is visible
- **THEN** components SHALL be organized in a tree with categories for Sources, Passive Components, Semiconductors, Switches, Transformers, Control Blocks, Probes, and Connectors

### Requirement: Component Display

Each component in the library SHALL show relevant information for identification.

#### Scenario: Component item display
- **GIVEN** a category is expanded
- **THEN** each component item SHALL show component icon, name, and description tooltip

### Requirement: Search Functionality

The library SHALL provide fast search to find components.

#### Scenario: Incremental search
- **GIVEN** the user types in the search box
- **WHEN** text is entered
- **THEN** the library SHALL filter to show only matching components in real-time

### Requirement: Drag and Drop

Components SHALL be placeable via drag and drop from the library.

#### Scenario: Drop to place
- **GIVEN** a component is being dragged over the canvas
- **WHEN** the user releases the mouse button
- **THEN** the component SHALL be placed at that position

### Requirement: Quick Placement Shortcuts

Power users SHALL be able to place components via keyboard.

#### Scenario: Single-key shortcuts
- **GIVEN** the schematic editor has focus
- **WHEN** the user presses a component shortcut key (R, C, L, etc.)
- **THEN** that component SHALL begin placement at the cursor

### Requirement: Favorites

Users SHALL be able to mark frequently used components as favorites.

#### Scenario: Add to favorites
- **GIVEN** a component is in the library
- **WHEN** the user right-clicks and selects "Add to Favorites"
- **THEN** the component SHALL appear in a "Favorites" category at the top

### Requirement: Recent Components

The library SHALL track recently used components.

#### Scenario: Recent category
- **GIVEN** components have been placed
- **THEN** a "Recent" category SHALL show the last 10 unique components used

### Requirement: Component Variants

Some components SHALL offer multiple variants or models.

#### Scenario: Expand variants
- **GIVEN** a component has variants (e.g., MOSFET has NMOS, PMOS)
- **WHEN** the user expands the component
- **THEN** the variants SHALL be shown as sub-items

### Requirement: Custom Components

Users SHALL be able to add custom components from subcircuits.

#### Scenario: Add subcircuit to library
- **GIVEN** a subcircuit has been created
- **WHEN** the user right-clicks and selects "Add to Library"
- **THEN** the subcircuit SHALL be added to a Custom category

### Requirement: Component Information

Users SHALL be able to view detailed component information.

#### Scenario: Component info panel
- **GIVEN** a component is selected in the library
- **WHEN** the user presses F1
- **THEN** an info panel SHALL show full description and parameters

### Requirement: Visual Consistency

Component symbols SHALL follow consistent visual standards.

#### Scenario: Symbol standards
- **GIVEN** any component symbol
- **THEN** the symbol SHALL use consistent line weights and standard schematic conventions

### Requirement: Power Electronics Focus

The library SHALL emphasize power electronics components.

#### Scenario: Power device prominence
- **GIVEN** the default library view
- **THEN** power electronics components (MOSFETs, IGBTs, diodes, transformers) SHALL be easily accessible
