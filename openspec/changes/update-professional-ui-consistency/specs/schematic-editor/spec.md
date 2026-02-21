## ADDED Requirements

### Requirement: Theme-Aware Overlay Rendering

The schematic editor SHALL render overlays and contextual UI in a theme-consistent manner.

#### Scenario: Context menu follows active theme
- **GIVEN** the user opens a schematic context menu
- **WHEN** any built-in theme is active
- **THEN** menu background, hover, separators, and icon tones SHALL match active theme tokens

#### Scenario: Overlay visuals follow active theme
- **GIVEN** drop preview, pin highlight, alignment guides, and selection visuals are shown
- **WHEN** the theme changes
- **THEN** overlay colors and emphasis SHALL update to remain readable on the current canvas background

### Requirement: Minimap Theme Consistency

The minimap SHALL align with the active theme and maintain clear viewport navigation cues.

#### Scenario: Minimap updates on theme switch
- **GIVEN** minimap is visible
- **WHEN** the user changes theme
- **THEN** minimap background, border, viewport rectangle, and element strokes SHALL update using theme-derived colors

#### Scenario: Minimap readability on empty scene
- **GIVEN** schematic scene has no placed components
- **WHEN** minimap renders placeholder state
- **THEN** placeholder text and framing SHALL remain legible in both light and dark themes
