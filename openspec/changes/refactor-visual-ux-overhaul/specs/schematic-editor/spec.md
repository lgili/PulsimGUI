## ADDED Requirements

### Requirement: Visual Feedback During Drag

The editor SHALL provide rich visual feedback when dragging components from the library.

#### Scenario: Drag preview with component symbol
- **GIVEN** the user starts dragging a component from the library
- **WHEN** dragging over the canvas
- **THEN** a ghost preview SHALL:
  - Show the actual component symbol (not a rectangle)
  - Be semi-transparent (60% opacity)
  - Snap to grid with visual grid highlight
  - Show valid/invalid drop zone indicator

#### Scenario: Magnetic snap preview
- **GIVEN** a component is being dragged near existing pins
- **WHEN** the component pin aligns with an unconnected pin
- **THEN** the editor SHALL:
  - Show a dashed line preview of potential wire
  - Highlight both pins with accent color
  - Show a "snap" indicator when alignment is exact

### Requirement: Component Hover Effects

The editor SHALL provide visual feedback when hovering over schematic elements.

#### Scenario: Component hover glow
- **GIVEN** the user hovers over a component
- **WHEN** the component is not selected
- **THEN** the component SHALL:
  - Show a subtle glow effect (4px blur, theme accent)
  - Slightly elevate (1px shadow)
  - Show pin names if configured

#### Scenario: Wire segment hover
- **GIVEN** the user hovers over a wire segment
- **WHEN** the segment is not selected
- **THEN** the segment SHALL:
  - Thicken slightly (from 2px to 3px)
  - Brighten color by 20%
  - Show junction dots at intersections

### Requirement: Enhanced Selection Visual

The editor SHALL provide clear, attractive selection visuals.

#### Scenario: Single component selection
- **GIVEN** a component is selected
- **THEN** the selection SHALL show:
  - Accent-colored border (2px)
  - Subtle drop shadow (4px blur, 20% opacity)
  - Resize handles at corners and edges
  - Rotation handle above component

#### Scenario: Box selection preview
- **GIVEN** the user is drawing a selection box
- **THEN** the selection box SHALL:
  - Have a semi-transparent fill (10% accent color)
  - Have a dashed border (accent color)
  - Show component count in corner as it changes
  - Animate border with marching ants effect

#### Scenario: Multi-selection bounding box
- **GIVEN** multiple components are selected
- **THEN** the selection SHALL show:
  - Single bounding box around all selected items
  - Selection count badge in top-right corner
  - Group manipulation handles

### Requirement: Improved Wire Routing Visual

The editor SHALL provide professional wire routing with visual enhancements.

#### Scenario: Wire preview during drawing
- **GIVEN** the user is drawing a wire
- **WHEN** moving the cursor
- **THEN** the wire preview SHALL:
  - Show dashed line in preview color
  - Animate with subtle flow effect
  - Show orthogonal routing guides
  - Highlight valid connection points

#### Scenario: Wire connection validation
- **GIVEN** the user attempts to connect a wire to a pin
- **WHEN** the connection would be valid
- **THEN** the editor SHALL show a green checkmark indicator
- **WHEN** the connection would be invalid
- **THEN** the editor SHALL show a red X indicator with tooltip

#### Scenario: Junction highlighting
- **GIVEN** a wire junction exists
- **WHEN** the user hovers near the junction
- **THEN** the junction dot SHALL:
  - Enlarge (from 4px to 6px diameter)
  - Show a highlight ring
  - Display tooltip with connected nets

### Requirement: Smooth Zoom and Navigation

The editor SHALL provide smooth, animated zoom and pan operations.

#### Scenario: Animated zoom
- **WHEN** the user scrolls to zoom
- **THEN** the zoom SHALL:
  - Animate smoothly over 150ms
  - Center on cursor position
  - Show zoom level indicator briefly

#### Scenario: Zoom overlay controls
- **WHEN** viewing the schematic
- **THEN** a zoom control overlay SHALL be visible in the corner:
  - Zoom in/out buttons
  - Zoom slider
  - Fit-to-content button
  - Current zoom percentage

#### Scenario: Minimap for large schematics
- **GIVEN** the schematic exceeds the visible viewport
- **WHEN** the minimap is enabled
- **THEN** a minimap SHALL appear showing:
  - Thumbnail of entire schematic
  - Current viewport rectangle (draggable)
  - Click-to-navigate functionality

## MODIFIED Requirements

### Requirement: Grid System

The editor SHALL provide a configurable grid with refined visual design.

#### Scenario: Grid display
- **GIVEN** grid is enabled
- **WHEN** viewing the schematic
- **THEN** the grid SHALL:
  - Display subtle dots at intersections (not lines by default)
  - Scale dot size appropriately with zoom (smaller when zoomed out)
  - Use theme-appropriate colors (barely visible, not distracting)
  - Show major grid lines every 5 units (optional)

#### Scenario: Grid visibility at zoom levels
- **GIVEN** the zoom level changes
- **THEN** the grid SHALL:
  - Fade out gradually below 50% zoom
  - Remain subtle and non-distracting at all levels
  - Never compete visually with components

### Requirement: Component Placement

The editor SHALL allow intuitive placement of circuit components with enhanced visual feedback.

#### Scenario: Drag from library
- **GIVEN** the component library is visible
- **WHEN** the user drags a component from the library onto the canvas
- **THEN**:
  - A ghost preview with actual component symbol SHALL follow the cursor
  - The component SHALL snap to grid with visual feedback (grid cell highlight)
  - Valid drop zones SHALL be indicated
  - Releasing the mouse SHALL place the component with subtle animation
  - The component SHALL receive a unique default name (e.g., R1, R2, C1)

#### Scenario: Quick add with keyboard
- **GIVEN** the editor has focus
- **WHEN** the user types a component shortcut (e.g., "r" for resistor, "c" for capacitor)
- **THEN**:
  - The component SHALL appear at the cursor position with fade-in animation
  - The component name field SHALL be selected for immediate editing
  - Enter confirms placement with slide-into-place animation, Esc cancels

### Requirement: Component Labels and Annotations

The editor SHALL display component information clearly with modern typography.

#### Scenario: Component name display
- **GIVEN** a component is placed
- **THEN** the component name (e.g., "R1") SHALL:
  - Be displayed in a clean, readable font
  - Have subtle text shadow for readability on any background
  - Animate position when component moves

#### Scenario: Component value display
- **GIVEN** a component has a value
- **THEN** the value (e.g., "10k") SHALL:
  - Be displayed below the name with slightly smaller font
  - Use engineering notation automatically (10k, 100u, 1M)
  - Have consistent positioning relative to component orientation
