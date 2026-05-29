## ADDED Requirements

### Requirement: Waveform-First Adaptive Layout
The professional scope workspace SHALL prioritize waveform visibility over auxiliary chrome.

A fresh scope window and `Reset Layout` SHALL restore a waveform-first state where:
- the left signals panel is collapsed
- the right inspector is collapsed
- the detailed bottom drawer is collapsed
- the main plot receives the dominant remaining space

When multiple auxiliary surfaces are requested at once, the scope SHALL adapt by collapsing, compacting, overlaying, or height-capping secondary surfaces rather than permanently shrinking the plot below a readable analysis area.

#### Scenario: Fresh-open waveform-first state
- **GIVEN** the user opens a new professional scope window
- **WHEN** no prior workspace state is being restored
- **THEN** the scope SHALL open with left panel, inspector, and bottom drawer collapsed
- **AND** the plot SHALL be the visually dominant surface

#### Scenario: Reset layout restores waveform priority
- **GIVEN** the user has opened multiple scope side panels and the bottom drawer
- **WHEN** the user triggers `Reset Layout`
- **THEN** the scope SHALL return to the waveform-first default layout
- **AND** auxiliary surfaces SHALL no longer consume persistent space until reopened

#### Scenario: Constrained layout with multiple auxiliary surfaces
- **GIVEN** the user opens the left panel, right inspector, and bottom drawer in a common desktop-sized window
- **WHEN** the combined chrome would significantly reduce the readable plot area
- **THEN** the scope SHALL compact, collapse, overlay, or cap one or more auxiliary surfaces
- **AND** it SHALL prefer preserving plot readability over showing every auxiliary surface at full size simultaneously

### Requirement: Automatic Mixed-Scale Trace Legibility
The professional scope workspace SHALL automatically choose a trace composition that preserves readability when visible traces have incompatible units or strongly different dynamic ranges.

The automatic composition logic SHALL consider:
- unit metadata when available
- visible-range amplitude or dynamic-range comparisons
- existing user overrides before reassigning traces

#### Scenario: Different units in one scope
- **GIVEN** the user shows voltage and current traces in the same scope
- **WHEN** the scope determines the default composition
- **THEN** it SHALL avoid same-axis overlay by default
- **AND** it SHALL assign the traces to separate panes or a distinct alternate axis

#### Scenario: Strongly mismatched amplitudes
- **GIVEN** a high-amplitude switching waveform and a lower-amplitude trace are both visible
- **WHEN** same-axis overlay would make the lower-amplitude trace hard to read
- **THEN** the scope SHALL automatically move one trace to a separate pane or alternate axis
- **AND** manual reassignment by the user SHALL remain available afterward

## ADDED Requirements

### Requirement: Menu Bar and Toolbar Architecture
The professional scope workspace SHALL provide compact top-level chrome that separates application-style commands from high-frequency actions.

The `Menu Bar` SHALL contain at minimum:
- `File`
- `View`
- `Simulation`
- `Tools`
- `Window`
- `Help`

The `Main Toolbar` SHALL group actions into:
- `Simulation`
- `Navigation`
- `Analysis`
- `Workspace`

The toolbar SHALL prioritize frequently used actions and move lower-frequency actions into menus, overflow affordances, or secondary surfaces when necessary to preserve horizontal clarity.

#### Scenario: Compact top chrome hierarchy
- **GIVEN** the scope window is visible
- **THEN** menu bar and toolbar SHALL appear as separate rows with clear grouping
- **AND** the toolbar SHALL use separators or equivalent visual structure to communicate groups without consuming excessive height

#### Scenario: Prioritized visible actions
- **GIVEN** the toolbar is rendered at normal desktop widths
- **THEN** high-frequency actions such as transport, fit, cursor, measurements, grid, and panel toggles SHALL remain visually prioritized
- **AND** secondary actions SHALL NOT force the toolbar into a crowded, hard-to-scan strip

#### Scenario: Tooltip and shortcut disclosure
- **GIVEN** the user hovers a toolbar action or opens a matching menu item
- **THEN** the UI SHALL disclose the action name, a short description, and the shortcut when one exists

### Requirement: Central Workspace Tabs and Plot Composition
The central workspace SHALL provide tabbed analysis surfaces and a plot region capable of professional trace composition.

At minimum, the central workspace SHALL provide:
- `Scope` tab
- `FFT` tab
- `Compare` tab

The `Scope` tab SHALL support:
- overlay traces
- dual-axis traces
- stacked plots
- automatic mixed-scale trace separation
- plot context menu
- trace selection and emphasis

A navigator inset or minimap MAY be shown when it materially helps viewport context, but it SHALL NOT permanently obscure waveform readability.

#### Scenario: Independent tab state
- **GIVEN** the user changes zoom or settings in one analysis tab
- **WHEN** the user switches to another tab and back
- **THEN** each tab SHALL restore its own relevant visualization state

#### Scenario: Optional navigator visibility
- **GIVEN** the visible window is narrower than the full data range
- **WHEN** a navigator inset is shown
- **THEN** it SHALL indicate viewport context within the total domain
- **AND** it SHALL use the same trace identity colors as the main plot
- **AND** it SHALL avoid covering or competing with the primary waveform area

### Requirement: Inspector Panel
The professional scope workspace SHALL provide a contextual right-side inspector for the current selection.

The inspector SHALL contain collapsible sections for:
- `Trace`
- `Axis`
- `Style`
- `Cursor`
- `Measurements`

The inspector SHALL use a compact density appropriate for repeated waveform analysis and SHALL avoid consuming excessive permanent width when the plot area is constrained.

#### Scenario: Trace selection updates inspector
- **GIVEN** the user selects a trace from the plot or signals panel
- **THEN** the inspector SHALL show that trace as the active editing target
- **AND** editable fields SHALL reflect the current live state of the trace

#### Scenario: Inspector edits apply immediately
- **GIVEN** the user changes color, thickness, axis assignment, or measurement scope in the inspector
- **THEN** the plot, signals panel, and other dependent readouts SHALL update without requiring an explicit apply step

#### Scenario: Compact inspector under constrained space
- **GIVEN** the scope window width is limited and the inspector is opened
- **WHEN** full-width inspector rendering would significantly reduce the plot area
- **THEN** the inspector SHALL use a compact or overlay presentation instead of permanently starving the waveform

### Requirement: Bottom Drawer
The professional scope workspace SHALL provide an expandable bottom drawer for detailed analysis outputs that should not permanently consume plot space.

The drawer SHALL provide these tabs:
- `Measurements`
- `Events`
- `Console`

The drawer SHALL remember:
- whether it is expanded or collapsed
- its last height
- its last active tab

A fresh scope window and `Reset Layout` SHALL keep the drawer collapsed by default.

When expanded, the drawer SHALL fit its content up to a bounded cap and SHALL avoid leaving large regions of empty space around small measurement tables.

#### Scenario: Measurements tab in the drawer
- **GIVEN** the drawer is expanded and `Measurements` is active
- **THEN** the table SHALL present per-signal metrics with stable columns and row identity markers
- **AND** the drawer SHALL size itself to the active content up to its configured maximum height

#### Scenario: Default collapsed drawer
- **GIVEN** the user opens a fresh scope window or triggers `Reset Layout`
- **THEN** the bottom drawer SHALL remain collapsed until explicitly opened

#### Scenario: Events and console separation
- **GIVEN** simulation messages and technical logs are produced
- **THEN** user-facing events and lower-level console/log output SHALL remain in separate tabs rather than one mixed feed

### Requirement: Quick Metrics and Status Feedback
The professional scope workspace SHALL provide compact immediate analysis feedback without competing excessively with the main plot.

The quick metrics strip SHALL summarize the current signal or active cursor interval using compact, tabular-aligned values.

When the detailed drawer is expanded, quick metrics MAY collapse, merge, or partially hide as long as equivalent information remains available through the drawer or status bar.

The status bar SHALL show at minimum:
- simulation state
- active analysis mode
- sample rate when available
- cursor positions and deltas when active

#### Scenario: Quick metrics follow active selection
- **GIVEN** the user changes the selected trace or active interval
- **THEN** the quick metrics strip SHALL update to the corresponding summary without requiring the drawer to be opened

#### Scenario: Quick metrics yield to detailed drawer
- **GIVEN** the detailed bottom drawer is expanded
- **WHEN** showing both surfaces at full height would reduce the plot unnecessarily
- **THEN** the quick metrics strip SHALL compact, merge, or hide redundant values
- **AND** the user SHALL still retain access to the same analysis context elsewhere in the workspace

#### Scenario: Status bar reflects cursor state
- **GIVEN** cursors are active
- **THEN** the status bar SHALL surface `X1`, `X2`, `Δt`, and `ΔY` when meaningful
- **AND** these readouts SHALL clear or revert gracefully when cursors are removed

### Requirement: Visual Language and Accessibility
The professional scope workspace SHALL follow a technical visual language where chrome remains neutral and data remains vivid.

The UI SHALL provide:
- consistent trace colors across all surfaces
- tooltips on actionable controls
- visible hover and active states
- keyboard navigation across panels, tabs, tables, and inspector fields
- sufficient contrast for text and cursor labels
- a plot surface visually distinct from surrounding shell chrome

The active application theme provided by `ThemeService` SHALL remain the source of truth, but the plot SHALL use dedicated analysis-surface tokens derived from that theme so waveform readability remains strong in both light and dark shells.

#### Scenario: Signal identity consistency
- **GIVEN** a trace is visible in multiple surfaces
- **THEN** its color identity SHALL remain consistent in the tree, plot, quick metrics, measurement table, and inspector swatch

#### Scenario: Plot emphasis inside a light shell
- **GIVEN** the user is using a light application theme
- **WHEN** the scope plot is rendered
- **THEN** the plot SHALL remain visually distinct from the surrounding shell chrome
- **AND** traces, grid lines, text, overlays, and cursor labels SHALL remain easier to read than the surrounding non-plot surfaces

#### Scenario: Keyboard-driven operation
- **GIVEN** the user navigates without a mouse
- **WHEN** using documented shortcuts or focus traversal
- **THEN** core actions such as run/pause, stop, fit, cursor toggle, measurement toggle, grid toggle, and add expression SHALL remain accessible
