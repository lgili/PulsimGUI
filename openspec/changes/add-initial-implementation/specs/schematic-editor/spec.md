## ADDED Requirements

### Requirement: Canvas and Viewport

The schematic editor SHALL provide an infinite canvas with smooth pan and zoom capabilities.

#### Scenario: Pan navigation
- **GIVEN** the user is viewing a schematic
- **WHEN** the user holds middle mouse button and drags
- **THEN** the viewport SHALL pan smoothly following the mouse movement

### Requirement: Grid System

The editor SHALL provide a configurable grid for precise component placement.

#### Scenario: Snap to grid
- **GIVEN** snap-to-grid is enabled
- **WHEN** placing or moving a component
- **THEN** the component SHALL snap to the nearest grid intersection

### Requirement: Component Placement

The editor SHALL allow intuitive placement of circuit components.

#### Scenario: Drag from library
- **GIVEN** the component library is visible
- **WHEN** the user drags a component from the library onto the canvas
- **THEN** a ghost preview SHALL follow the cursor and release places the component

### Requirement: Component Selection

The editor SHALL provide flexible selection mechanisms.

#### Scenario: Single click selection
- **GIVEN** the selection tool is active
- **WHEN** the user clicks on a component
- **THEN** that component SHALL be selected and all others deselected

### Requirement: Wire Routing

The editor SHALL provide intuitive wire drawing and automatic routing.

#### Scenario: Start wire from pin
- **GIVEN** the wire tool is active
- **WHEN** the user clicks on a component pin
- **THEN** a wire SHALL start from that pin with orthogonal routing

### Requirement: Component Editing

The editor SHALL allow in-place editing of component properties.

#### Scenario: Double-click to edit
- **GIVEN** a component is in the schematic
- **WHEN** the user double-clicks on it
- **THEN** the properties panel SHALL open with that component's parameters

### Requirement: Copy, Cut, Paste

The editor SHALL support clipboard operations with full fidelity.

#### Scenario: Copy selection
- **GIVEN** components and wires are selected
- **WHEN** the user presses Ctrl+C
- **THEN** the selection SHALL be copied to clipboard

### Requirement: Undo/Redo

The editor SHALL support unlimited undo/redo with descriptive action names.

#### Scenario: Undo action
- **GIVEN** actions have been performed
- **WHEN** the user presses Ctrl+Z
- **THEN** the last action SHALL be undone

### Requirement: Component Labels and Annotations

The editor SHALL display component information clearly.

#### Scenario: Component name display
- **GIVEN** a component is placed
- **THEN** the component name SHALL be displayed near the component

### Requirement: Node Voltage Probes

The editor SHALL allow placing voltage probes on nodes.

#### Scenario: Place voltage probe
- **GIVEN** the probe tool is active
- **WHEN** the user clicks on a wire or node
- **THEN** a probe marker SHALL appear and the voltage added to simulation outputs

### Requirement: Current Measurement

The editor SHALL allow measuring current through components.

#### Scenario: Add current measurement
- **GIVEN** a component is selected
- **WHEN** the user right-clicks and selects "Measure Current"
- **THEN** the current SHALL be added to simulation outputs

### Requirement: Hierarchical Schematics

The editor SHALL support subcircuits for design hierarchy.

#### Scenario: Create subcircuit from selection
- **GIVEN** components are selected
- **WHEN** the user selects "Create Subcircuit"
- **THEN** the selection SHALL be replaced by a subcircuit block

### Requirement: Design Rule Checking

The editor SHALL validate schematic correctness.

#### Scenario: Floating node warning
- **GIVEN** a node has only one connection
- **THEN** the editor SHALL display a warning indicator

### Requirement: Find and Navigate

The editor SHALL provide search functionality.

#### Scenario: Find component by name
- **GIVEN** the user presses Ctrl+F
- **WHEN** the user types a component name
- **THEN** matching components SHALL be highlighted
