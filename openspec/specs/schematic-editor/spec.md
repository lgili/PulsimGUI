# Schematic Editor

## Purpose

The core canvas for creating and editing circuit schematics with drag-and-drop component placement, wire routing, and visual feedback.

## Requirements

### Requirement: Canvas and Viewport

The schematic editor SHALL provide an infinite canvas with smooth pan and zoom capabilities.

#### Scenario: Pan navigation
- **GIVEN** the user is viewing a schematic
- **WHEN** the user holds middle mouse button and drags, or holds Space and drags with left mouse
- **THEN** the viewport SHALL pan smoothly following the mouse movement

#### Scenario: Zoom with mouse wheel
- **GIVEN** the user is viewing a schematic
- **WHEN** the user scrolls the mouse wheel
- **THEN** the view SHALL:
  - Zoom in/out centered on the mouse cursor position
  - Support zoom levels from 10% to 1000%
  - Display zoom level in status bar

#### Scenario: Zoom to fit
- **GIVEN** the schematic contains components
- **WHEN** the user presses Ctrl+0 or clicks "Zoom to Fit"
- **THEN** the view SHALL adjust to show all components with 10% padding

#### Scenario: Zoom to selection
- **GIVEN** components are selected
- **WHEN** the user clicks "Zoom to Selection"
- **THEN** the view SHALL center and zoom to show selected components

### Requirement: Grid System

The editor SHALL provide a configurable grid for precise component placement.

#### Scenario: Grid display
- **GIVEN** grid is enabled
- **WHEN** viewing the schematic
- **THEN** the grid SHALL:
  - Display dots or lines at regular intervals
  - Scale appropriately with zoom level
  - Use subtle colors that don't distract from components

#### Scenario: Snap to grid
- **GIVEN** snap-to-grid is enabled
- **WHEN** placing or moving a component
- **THEN** the component SHALL snap to the nearest grid intersection

#### Scenario: Grid size configuration
- **GIVEN** the user opens grid settings
- **THEN** available grid sizes SHALL be: 1mm, 2.5mm, 5mm, 10mm
- **AND** the default SHALL be 2.5mm (matching PLECS)

### Requirement: Component Placement

The editor SHALL allow intuitive placement of circuit components.

#### Scenario: Drag from library
- **GIVEN** the component library is visible
- **WHEN** the user drags a component from the library onto the canvas
- **THEN**:
  - A ghost preview of the component SHALL follow the cursor
  - The component SHALL snap to grid if enabled
  - Releasing the mouse SHALL place the component
  - The component SHALL receive a unique default name (e.g., R1, R2, C1)

#### Scenario: Quick add with keyboard
- **GIVEN** the editor has focus
- **WHEN** the user types a component shortcut (e.g., "r" for resistor, "c" for capacitor)
- **THEN**:
  - The component SHALL appear at the cursor position
  - The user can immediately type a value
  - Enter confirms placement, Esc cancels

#### Scenario: Component rotation
- **GIVEN** a component is selected or being placed
- **WHEN** the user presses R key
- **THEN** the component SHALL rotate 90 degrees clockwise
- **AND** Shift+R SHALL rotate counter-clockwise

#### Scenario: Component mirroring
- **GIVEN** a component is selected
- **WHEN** the user presses H key (horizontal) or V key (vertical)
- **THEN** the component SHALL mirror about the corresponding axis

### Requirement: Component Selection

The editor SHALL provide flexible selection mechanisms.

#### Scenario: Single click selection
- **GIVEN** the selection tool is active
- **WHEN** the user clicks on a component
- **THEN** that component SHALL be selected and all others deselected

#### Scenario: Multi-selection with Ctrl
- **GIVEN** components are in the schematic
- **WHEN** the user Ctrl+clicks on components
- **THEN** each clicked component SHALL toggle its selection state

#### Scenario: Box selection
- **GIVEN** the selection tool is active
- **WHEN** the user drags a rectangle on empty canvas space
- **THEN** all components fully inside the rectangle SHALL be selected

#### Scenario: Crossing selection
- **GIVEN** the user holds Alt while box selecting
- **THEN** all components touched by the rectangle SHALL be selected

#### Scenario: Select all
- **WHEN** the user presses Ctrl+A
- **THEN** all components and wires SHALL be selected

### Requirement: Wire Routing

The editor SHALL provide intuitive wire drawing and automatic routing.

#### Scenario: Start wire from pin
- **GIVEN** the wire tool is active (W key or toolbar)
- **WHEN** the user clicks on a component pin
- **THEN**:
  - A wire SHALL start from that pin
  - The wire preview SHALL follow the cursor
  - The wire SHALL use orthogonal routing by default

#### Scenario: Orthogonal wire routing
- **GIVEN** a wire is being drawn
- **WHEN** the user moves the cursor
- **THEN** the wire preview SHALL:
  - Create horizontal and vertical segments only
  - Automatically insert corners as needed
  - Show the wire path clearly

#### Scenario: Wire completion
- **GIVEN** a wire is being drawn
- **WHEN** the user clicks on another pin
- **THEN**:
  - The wire SHALL complete and connect to that pin
  - Both pins SHALL show as connected (filled dots)
  - The wire SHALL be added to the netlist

#### Scenario: Wire junction creation
- **GIVEN** a wire is being drawn
- **WHEN** the user clicks on an existing wire segment
- **THEN**:
  - A junction dot SHALL be created
  - The new wire SHALL connect at that point
  - The electrical connection SHALL be established

#### Scenario: Wire cancellation
- **GIVEN** a wire is being drawn
- **WHEN** the user presses Escape or right-clicks
- **THEN** the wire-in-progress SHALL be cancelled

#### Scenario: Auto-wire on component drop
- **GIVEN** a component is being placed near existing pins
- **WHEN** the component pins align with unconnected pins
- **THEN** the editor MAY offer to auto-connect with wires

### Requirement: Component Editing

The editor SHALL allow in-place editing of component properties.

#### Scenario: Double-click to edit
- **GIVEN** a component is in the schematic
- **WHEN** the user double-clicks on it
- **THEN** the properties panel SHALL open with that component's parameters

#### Scenario: Quick value edit
- **GIVEN** a component is selected
- **WHEN** the user presses Enter or F2
- **THEN** an inline text field SHALL appear for editing the primary value

#### Scenario: Value with units
- **GIVEN** the user is editing a component value
- **WHEN** the user types "10k" or "100u" or "1meg"
- **THEN** the value SHALL be interpreted with SI prefixes (kilo, micro, mega)

#### Scenario: Rename component
- **GIVEN** a component is selected
- **WHEN** the user presses F2 while holding Ctrl
- **THEN** an inline field SHALL appear for editing the component name

### Requirement: Copy, Cut, Paste

The editor SHALL support clipboard operations with full fidelity.

#### Scenario: Copy selection
- **GIVEN** components and wires are selected
- **WHEN** the user presses Ctrl+C
- **THEN** the selection SHALL be copied to clipboard, including:
  - Component types and values
  - Relative positions
  - Wire connections between selected components

#### Scenario: Cut selection
- **GIVEN** components are selected
- **WHEN** the user presses Ctrl+X
- **THEN** the selection SHALL be:
  - Copied to clipboard
  - Removed from the schematic
  - Recorded as an undoable action

#### Scenario: Paste from clipboard
- **GIVEN** components are in the clipboard
- **WHEN** the user presses Ctrl+V
- **THEN**:
  - The components SHALL appear at the cursor position
  - Component names SHALL be made unique (R1 -> R2 if R1 exists)
  - The pasted components SHALL be selected
  - The user can immediately move to position them

#### Scenario: Duplicate in place
- **GIVEN** components are selected
- **WHEN** the user presses Ctrl+D
- **THEN** a copy SHALL be created offset by one grid unit

### Requirement: Undo/Redo

The editor SHALL support unlimited undo/redo with descriptive action names.

#### Scenario: Undo action
- **GIVEN** actions have been performed
- **WHEN** the user presses Ctrl+Z
- **THEN**:
  - The last action SHALL be undone
  - The Edit menu SHALL show "Undo [action name]"
  - The action SHALL be moved to the redo stack

#### Scenario: Redo action
- **GIVEN** actions have been undone
- **WHEN** the user presses Ctrl+Y or Ctrl+Shift+Z
- **THEN** the last undone action SHALL be reapplied

#### Scenario: Undo history
- **GIVEN** the user opens Edit > Undo History
- **THEN** a list of all undoable actions SHALL be shown with timestamps

### Requirement: Component Labels and Annotations

The editor SHALL display component information clearly.

#### Scenario: Component name display
- **GIVEN** a component is placed
- **THEN** the component name (e.g., "R1") SHALL be displayed near the component

#### Scenario: Component value display
- **GIVEN** a component has a value
- **THEN** the value (e.g., "10k") SHALL be displayed below the name

#### Scenario: Label positioning
- **GIVEN** a component's labels overlap with other elements
- **WHEN** the user drags the label
- **THEN** the label position relative to the component SHALL be adjustable

#### Scenario: Hide/show labels
- **GIVEN** the View menu is open
- **THEN** the user SHALL be able to toggle:
  - Component names visibility
  - Component values visibility
  - Pin names visibility

### Requirement: Node Voltage Probes

The editor SHALL allow placing voltage probes on nodes.

#### Scenario: Place voltage probe
- **GIVEN** the probe tool is active
- **WHEN** the user clicks on a wire or node
- **THEN**:
  - A probe marker SHALL appear
  - The node SHALL be named (or use auto-generated name)
  - The voltage SHALL be added to default simulation outputs

#### Scenario: Probe configuration
- **GIVEN** a probe is placed
- **WHEN** the user double-clicks the probe
- **THEN** a dialog SHALL allow:
  - Naming the signal
  - Setting display color in scope
  - Choosing scale factor

### Requirement: Current Measurement

The editor SHALL allow measuring current through components.

#### Scenario: Add current measurement
- **GIVEN** a component is selected
- **WHEN** the user right-clicks and selects "Measure Current"
- **THEN**:
  - A current probe icon SHALL appear on the component
  - The current SHALL be added to simulation outputs

#### Scenario: Current direction indication
- **GIVEN** a current measurement exists
- **THEN** an arrow SHALL indicate the positive current direction

### Requirement: Hierarchical Schematics

The editor SHALL support subcircuits for design hierarchy.

#### Scenario: Create subcircuit from selection
- **GIVEN** components are selected
- **WHEN** the user selects "Create Subcircuit"
- **THEN**:
  - A dialog SHALL prompt for subcircuit name
  - The selection SHALL be replaced by a subcircuit block
  - Connections to external nodes SHALL become subcircuit pins
  - The subcircuit content SHALL be editable separately

#### Scenario: Navigate into subcircuit
- **GIVEN** a subcircuit block exists
- **WHEN** the user double-clicks on it
- **THEN** the editor SHALL display the subcircuit's internal schematic

#### Scenario: Breadcrumb navigation
- **GIVEN** the user is viewing a subcircuit
- **THEN** a breadcrumb trail SHALL show the hierarchy path
- **AND** clicking any level SHALL navigate to that schematic

### Requirement: Design Rule Checking

The editor SHALL validate schematic correctness.

#### Scenario: Floating node warning
- **GIVEN** a node has only one connection
- **THEN** the editor SHALL display a warning indicator

#### Scenario: Missing ground warning
- **GIVEN** the circuit has no ground reference
- **THEN** the editor SHALL warn before simulation

#### Scenario: Short circuit detection
- **GIVEN** voltage sources are directly connected in parallel with different values
- **THEN** the editor SHALL highlight the potential short circuit

### Requirement: Find and Navigate

The editor SHALL provide search functionality.

#### Scenario: Find component by name
- **GIVEN** the user presses Ctrl+F
- **WHEN** the user types a component name
- **THEN**:
  - Matching components SHALL be highlighted
  - The view SHALL center on the first match
  - Arrow keys SHALL navigate between matches
