# Spec Delta: schematic-editor

## ADDED Requirements

### Requirement: Rulers Display
The schematic editor SHALL display measurement rulers along the edges.

#### Scenario: Horizontal ruler display
- Given the schematic view is open
- When rulers are enabled (View > Show Rulers)
- Then a horizontal ruler appears along the top edge
- And the ruler shows tick marks at regular intervals
- And major ticks are labeled with coordinate values

#### Scenario: Vertical ruler display
- Given the schematic view is open
- When rulers are enabled
- Then a vertical ruler appears along the left edge
- And the ruler shows tick marks at regular intervals
- And major ticks are labeled with coordinate values

#### Scenario: Ruler synchronization
- Given rulers are visible
- When the user scrolls or zooms the schematic
- Then the rulers update to reflect the visible region
- And tick spacing adjusts based on zoom level

#### Scenario: Ruler toggle
- Given the schematic view is open
- When the user selects View > Show Rulers (or presses shortcut)
- Then rulers visibility toggles on/off
- And the preference is persisted

---

### Requirement: Enhanced Component Labels
Components SHALL display their value alongside the name for quick identification.

#### Scenario: Value label display
- Given a component is placed on the schematic
- And the component has a primary parameter (e.g., resistance for resistor)
- When value labels are enabled in preferences
- Then the component displays "{name} = {value}" (e.g., "R1 = 1kΩ")

#### Scenario: SI prefix formatting
- Given a component value is displayed
- When the value is 1000 or greater, or 0.001 or smaller
- Then the value is formatted with appropriate SI prefix
- And units are shown (Ω, F, H, V, A)

#### Scenario: Label background
- Given a component label is displayed
- When the label overlaps with other elements
- Then the label has a semi-transparent background
- And the text remains readable

---

### Requirement: Wire Junction Visibility
Wire junctions SHALL be prominently displayed for clear circuit topology.

#### Scenario: Junction appearance
- Given two or more wires connect at a point
- When the junction is rendered
- Then a filled circle of 6px radius is displayed
- And the circle color matches the wire color

#### Scenario: Junction at zoom levels
- Given a wire junction exists
- When the user zooms in or out
- Then the junction remains visible and proportional
- And the junction is clearly distinguishable from wire endpoints

---

### Requirement: Simulation Visualization
The schematic SHALL provide visual feedback of electrical values during simulation.

#### Scenario: Voltage color coding
- Given a simulation is running
- When simulation visualization is enabled
- Then nodes are colored based on voltage level
- And negative voltages appear blue
- And positive voltages appear red
- And zero/ground appears neutral (white/gray)

#### Scenario: Current flow indication
- Given a simulation is running
- When current flow display is enabled
- Then wires show directional arrows indicating current flow
- And arrow density/size indicates current magnitude

#### Scenario: Power dissipation display
- Given a simulation is running
- When power display is enabled
- Then components show a heat indicator
- And higher power dissipation shows warmer colors (yellow/red)

#### Scenario: Visualization toggle
- Given the simulation menu is open
- When the user selects "Show Simulation Values"
- Then visualization overlays are toggled on/off
- And the setting persists during the session

---

### Requirement: Context Menu Organization
The context menu SHALL be organized with logical submenus.

#### Scenario: Edit submenu
- Given a component or wire is selected
- When the user right-clicks
- Then the context menu shows an "Edit" submenu
- And the submenu contains: Cut, Copy, Paste, Delete, Duplicate

#### Scenario: Transform submenu
- Given a component is selected
- When the user right-clicks
- Then the context menu shows a "Transform" submenu
- And the submenu contains: Rotate CW, Rotate CCW, Flip Horizontal, Flip Vertical

#### Scenario: Align submenu
- Given multiple components are selected
- When the user right-clicks
- Then the context menu shows an "Align" submenu
- And the submenu contains: Align Left, Right, Top, Bottom, Center Horizontal, Center Vertical

#### Scenario: Menu icons
- Given the context menu is displayed
- When viewing any menu item
- Then each item has an appropriate icon
- And icons are consistent with toolbar icons
