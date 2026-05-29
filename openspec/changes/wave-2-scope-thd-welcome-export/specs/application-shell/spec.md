## ADDED Requirements

### Requirement: Welcome surface for empty workspace
When the active circuit has zero components the application SHALL render a welcome surface in the schematic canvas area with four primary actions.

#### Scenario: Empty canvas shows welcome cards
- **GIVEN** the user just launched the app or chose `File → Close`
- **WHEN** the active circuit has no components
- **THEN** the canvas SHALL display four cards: New schematic, Open project…, Recent projects, From template

#### Scenario: Welcome surface hides on first component
- **GIVEN** the welcome surface is visible
- **WHEN** the user drops a component on the canvas or imports a project with content
- **THEN** the welcome surface SHALL hide and the schematic editor SHALL be fully visible

#### Scenario: Template card opens the gallery picker
- **GIVEN** the welcome surface is visible
- **WHEN** the user clicks the "From template" card
- **THEN** a modal SHALL open listing the gallery topologies + tutorial examples with one-line descriptions
- **AND** selecting one SHALL load the project into the canvas as an untitled copy (so save-as does not overwrite the gallery file)

### Requirement: Schematic image export
The application SHALL expose `File → Export → Schematic Image…` which renders the current circuit to PNG or SVG with user-selectable resolution, background, and margin.

#### Scenario: PNG export at 2× resolution
- **GIVEN** the user has an open project with at least one component
- **WHEN** the user invokes `File → Export → Schematic Image…`, picks PNG / 2× / white / 16 px margin, and chooses a destination path
- **THEN** the app SHALL write a non-empty PNG file at the chosen path with the rendered schematic, white background, 16 px margin, and 2× the canvas DPI

#### Scenario: SVG export preserves vector quality
- **GIVEN** the same setup
- **WHEN** the user picks SVG format
- **THEN** the output SHALL be a valid SVG document whose root `<svg>` element contains the rendered schematic geometry as vector paths

### Requirement: Copy schematic to clipboard
The application SHALL provide `Edit → Copy Schematic as Image` (`⌘⇧C` on macOS, `Ctrl+Shift+C` on Windows / Linux) which writes a rendered PNG of the active circuit to the system clipboard.

#### Scenario: Copy-then-paste roundtrip
- **GIVEN** an open project with at least one component
- **WHEN** the user triggers the action
- **THEN** the system clipboard SHALL contain a `image/png` payload of the same render the export dialog would produce at 2× / white / 16 px margin
