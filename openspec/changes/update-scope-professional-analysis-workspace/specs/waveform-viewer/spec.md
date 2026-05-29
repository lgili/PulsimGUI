## MODIFIED Requirements

### Requirement: Scope Panel Structure

The waveform viewer SHALL present a professional analysis workspace that can run standalone or embedded while preserving the same internal structure.

The canonical internal layout SHALL contain six coordinated regions:
- `Menu Bar`
- `Main Toolbar`
- `Left Sidebar: Signals Panel`
- `Central Workspace`
- `Right Sidebar: Inspector`
- `Bottom Area` consisting of quick metrics strip, bottom drawer, and status bar

The plot area SHALL remain the primary consumer of screen space, and surrounding chrome SHALL stay compact enough to support dense analysis workflows.

#### Scenario: Standalone professional scope window
- **GIVEN** the host launches the scope as an independent window
- **WHEN** the workspace opens
- **THEN** the scope SHALL render the full professional layout with its own menu/toolbar/status surfaces
- **AND** it SHALL NOT depend on PulsimGui dock layout to expose core scope controls

#### Scenario: Embedded professional scope panel
- **GIVEN** a host embeds the scope inside another window
- **WHEN** the scope becomes visible
- **THEN** the internal regions SHALL retain the same semantics and ordering as standalone mode
- **AND** only outer window chrome may be delegated to the host

#### Scenario: Resizable analysis shell
- **GIVEN** the user resizes the scope window or drags panel splitters
- **WHEN** the layout recomputes
- **THEN** left sidebar, right inspector, bottom drawer, and central workspace SHALL resize without overlapping or hiding essential controls
- **AND** the central plot SHALL keep the maximum feasible area

### Requirement: Signal Display

The viewer SHALL expose signals through a dedicated left `Signals` panel that supports discovery, filtering, grouping, routing, and direct trace actions.

The panel SHALL contain:
- a header with title and panel-collapse control
- an incremental search field
- a hierarchical tree view for runs, signals, math traces, and future derived groups
- footer actions including `Add Expression`

Each signal row SHALL expose at minimum:
- visibility control
- color swatch
- signal name or alias
- axis badge
- selected state

#### Scenario: Incremental signal search
- **GIVEN** the signal catalog contains many rows
- **WHEN** the user types into the search field
- **THEN** matching rows SHALL be filtered in real time by signal name, group, or alias
- **AND** non-matching rows SHALL be hidden or muted deterministically

#### Scenario: Hierarchical run and math groups
- **GIVEN** multiple runs and derived expressions are available
- **THEN** the tree SHALL group raw traces by run and place user expressions under a separate math-oriented section
- **AND** groups SHALL support collapse and expand behavior with persistent state

#### Scenario: Signal-row direct actions
- **GIVEN** a signal row is visible in the tree
- **WHEN** the user toggles visibility, clicks the axis badge, or opens the context menu
- **THEN** the corresponding plot, inspector, and measurement surfaces SHALL update without losing current selection context

#### Scenario: Drag and drop to plot or plot group
- **GIVEN** a signal exists in the left panel
- **WHEN** the user drags it to the active plot region or an existing plot group
- **THEN** the signal SHALL be added to the target scope in a deterministic position
- **AND** overlay versus separate-plot behavior SHALL follow the documented drop target rules

### Requirement: Axis Control

The viewer SHALL let users assign and edit axes from both the signals panel and the inspector.

Supported axis targets SHALL include:
- `Left`
- `Right`
- `New Plot`

Each axis SHALL support:
- autoscale
- manual min/max
- offset
- inversion
- future-compatible scale types

#### Scenario: Axis badge reassignment
- **GIVEN** a trace is listed in the signals panel
- **WHEN** the user changes the axis badge
- **THEN** the trace SHALL move to the requested axis target
- **AND** the plot and inspector SHALL reflect the new assignment immediately

#### Scenario: Autoscale versus manual limits
- **GIVEN** the inspector is showing the selected trace axis section
- **WHEN** autoscale is enabled
- **THEN** manual min/max inputs SHALL be disabled
- **AND** the visible plot range SHALL update from the current trace set

### Requirement: Zoom and Pan

The viewer SHALL provide plot navigation that is tool-aware, precise, and suitable for dense waveform inspection.

Supported interactions SHALL include:
- wheel zoom
- rectangle zoom
- pan drag
- fit view
- local reset
- context-menu navigation actions

#### Scenario: Wheel-based horizontal zoom
- **GIVEN** the pointer is over the plot
- **WHEN** the user scrolls the wheel
- **THEN** the view SHALL zoom around the pointer position horizontally by default
- **AND** documented modifiers MAY change the zoom axis behavior

#### Scenario: Tool-aware drag behavior
- **GIVEN** the active toolbar tool is zoom or pan
- **WHEN** the user drags on the plot
- **THEN** the drag action SHALL follow the active tool semantics consistently
- **AND** cursor placement SHALL not accidentally trigger when another navigation tool is active

#### Scenario: Local reset and fit
- **GIVEN** the user has changed the current view window
- **WHEN** the user invokes fit or reset zoom
- **THEN** the plot SHALL return to the appropriate full-range or local default extent without disturbing trace selection state

### Requirement: Cursors

The viewer SHALL provide oscilloscope-like cursor tools with synchronized plot, inspector, quick-metrics, drawer, and status-bar readouts.

The initial professional scope release SHALL support:
- vertical cursors `X1` and `X2`
- optional horizontal cursors `Y1` and `Y2`
- delta calculations for time and selected trace value
- configurable snap mode

#### Scenario: Cursor activation updates all analysis surfaces
- **GIVEN** the cursor tool is enabled
- **WHEN** the user places or drags a cursor on the plot
- **THEN** the overlay labels, inspector cursor section, quick metrics strip, bottom drawer, and status bar SHALL update from the same cursor state

#### Scenario: Delta overlay on selected trace
- **GIVEN** two vertical cursors are active and a trace is selected
- **THEN** the plot SHALL show `Δt`, derived frequency when valid, and `ΔY` for the selected trace
- **AND** the same values SHALL be available in textual form outside the plot

#### Scenario: Snap mode selection
- **GIVEN** the inspector cursor section or another cursor control is visible
- **WHEN** the user selects `None`, `Samples`, `Peaks`, `Edges`, or `Zero Crossings`
- **THEN** cursor placement and drag behavior SHALL follow the chosen snap mode consistently

### Requirement: Measurements

The viewer SHALL expose measurements through three coordinated surfaces:
- quick metrics strip for compact always-visible summaries
- plot overlay for immediate cursor feedback
- bottom drawer measurement table for detailed per-signal results

Measurements SHALL support these scopes:
- full data range
- visible range
- between cursors

The initial professional scope release SHALL support at minimum:
- RMS
- Peak
- Min
- Max
- Mean
- Frequency
- Period

#### Scenario: Add and remove measurement columns
- **GIVEN** the measurements surface is visible
- **WHEN** the user adds or removes measurement types from the measurement selector
- **THEN** the bottom measurement table SHALL update its columns deterministically
- **AND** the quick metrics strip SHALL continue to show the compact summary subset

#### Scenario: Measurement scope changes
- **GIVEN** a signal is selected and measurement results are visible
- **WHEN** the user changes the measurement scope from full range to visible range or between cursors
- **THEN** all displayed values derived from that scope SHALL recompute consistently across the workspace

#### Scenario: Unavailable measurement placeholder
- **GIVEN** a measurement cannot be computed for the current signal or interval
- **THEN** the UI SHALL show a deterministic placeholder instead of stale numeric data
- **AND** the user SHALL be able to discover why through tooltip or inline explanation

### Requirement: Multiple Scopes

The system SHALL support multiple scopes within one workspace, each holding multiple traces and independent local analysis state.

Each scope SHALL preserve its own:
- visible traces
- plot composition
- cursor state
- measurement setup
- zoom state
- active analysis tab state where applicable

#### Scenario: Add, duplicate, rename, and remove scopes
- **GIVEN** a workspace is open
- **WHEN** the user manages scopes from the workspace controls
- **THEN** the system SHALL support creating, duplicating, renaming, and removing scopes without corrupting other scope states

#### Scenario: Independent per-scope analysis
- **GIVEN** at least two scopes exist
- **WHEN** the user changes the view or measurements in one scope
- **THEN** the other scopes SHALL retain their own independent configuration until explicitly edited

### Requirement: Signal Math

The viewer SHALL provide an expression workflow for creating derived traces without leaving the scope workspace.

The `Add Expression` flow SHALL capture:
- derived signal name
- formula
- available signals
- resulting unit preview
- validity state
- optional add-to-plot behavior

#### Scenario: Create valid expression
- **GIVEN** raw signals are available
- **WHEN** the user enters a valid mathematical expression
- **THEN** a derived signal SHALL be created under the appropriate tree group
- **AND** it SHALL be available for immediate plotting and measurement

#### Scenario: Invalid expression feedback
- **GIVEN** the expression contains invalid syntax or unresolved signals
- **THEN** the editor SHALL show deterministic validation feedback
- **AND** it SHALL NOT create a broken trace entry

### Requirement: FFT Analysis

The viewer SHALL expose FFT as a first-class analysis mode rather than only a detached auxiliary plot.

The professional scope workspace SHALL provide an `FFT` tab that shares signal selection semantics with the time-domain scope while keeping FFT-specific settings local to that tab.

#### Scenario: Switch from scope to FFT tab
- **GIVEN** one or more compatible traces are available
- **WHEN** the user opens the `FFT` tab
- **THEN** the workspace SHALL render the corresponding frequency-domain analysis view
- **AND** it SHALL preserve time-domain view state for the `Scope` tab

#### Scenario: FFT settings remain local
- **GIVEN** FFT parameters such as points or window function are edited
- **WHEN** the user returns to the `Scope` tab and later reopens `FFT`
- **THEN** the FFT tab SHALL restore its own settings without corrupting the time-domain configuration

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

#### Scenario: Compact top chrome hierarchy
- **GIVEN** the scope window is visible
- **THEN** menu bar and toolbar SHALL appear as separate rows with clear grouping
- **AND** the toolbar SHALL use separators or equivalent visual structure to communicate groups without consuming excessive height

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
- minimap/navigator inset
- plot context menu
- trace selection and emphasis

#### Scenario: Independent tab state
- **GIVEN** the user changes zoom or settings in one analysis tab
- **WHEN** the user switches to another tab and back
- **THEN** each tab SHALL restore its own relevant visualization state

#### Scenario: Navigator inset visibility
- **GIVEN** the visible window is narrower than the full data range
- **THEN** a navigator inset or minimap SHALL indicate viewport context within the total domain
- **AND** it SHALL use the same trace identity colors as the main plot

### Requirement: Inspector Panel

The professional scope workspace SHALL provide a contextual right-side inspector for the current selection.

The inspector SHALL contain collapsible sections for:
- `Trace`
- `Axis`
- `Style`
- `Cursor`
- `Measurements`

#### Scenario: Trace selection updates inspector
- **GIVEN** the user selects a trace from the plot or signals panel
- **THEN** the inspector SHALL show that trace as the active editing target
- **AND** editable fields SHALL reflect the current live state of the trace

#### Scenario: Inspector edits apply immediately
- **GIVEN** the user changes color, thickness, axis assignment, or measurement scope in the inspector
- **THEN** the plot, signals panel, and other dependent readouts SHALL update without requiring an explicit apply step

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

#### Scenario: Measurements tab in the drawer
- **GIVEN** the drawer is expanded and `Measurements` is active
- **THEN** the table SHALL present per-signal metrics with stable columns and row identity markers

#### Scenario: Events and console separation
- **GIVEN** simulation messages and technical logs are produced
- **THEN** user-facing events and lower-level console/log output SHALL remain in separate tabs rather than one mixed feed

### Requirement: Quick Metrics and Status Feedback

The professional scope workspace SHALL provide compact always-visible readouts for immediate analysis context.

The quick metrics strip SHALL summarize the current signal or active cursor interval using compact, tabular-aligned values.

The status bar SHALL show at minimum:
- simulation state
- active analysis mode
- sample rate when available
- cursor positions and deltas when active

#### Scenario: Quick metrics follow active selection
- **GIVEN** the user changes the selected trace or active interval
- **THEN** the quick metrics strip SHALL update to the corresponding summary without requiring the drawer to be opened

#### Scenario: Status bar reflects cursor state
- **GIVEN** cursors are active
- **THEN** the status bar SHALL surface `X1`, `X2`, `Δt`, and `ΔY` when meaningful
- **AND** these readouts SHALL clear or revert gracefully when cursors are removed

### Requirement: Workspace State Synchronization and Persistence

The professional scope workspace SHALL synchronize selection and persist user workspace state across sessions.

Persisted state SHALL include at minimum:
- panel visibility and sizes
- drawer height and active tab
- selected signals and visible traces
- signal colors and axis assignments
- active analysis tab
- zoom state
- cursor state
- enabled measurements
- workspace layout state for multiple scopes

#### Scenario: Cross-surface synchronized selection
- **GIVEN** the user selects a trace from any surface
- **WHEN** the selection changes
- **THEN** the signals panel, plot emphasis, inspector, quick metrics, and measurement table SHALL converge on the same selected trace

#### Scenario: Session restore
- **GIVEN** a workspace was previously saved
- **WHEN** it is restored later
- **THEN** the scope SHALL rehydrate the saved panel layout, selected traces, cursors, measurements, and analysis tabs without manual reconstruction

### Requirement: Visual Language and Accessibility

The professional scope workspace SHALL follow a technical visual language where chrome remains neutral and data remains vivid.

The UI SHALL provide:
- consistent trace colors across all surfaces
- tooltips on actionable controls
- visible hover and active states
- keyboard navigation across panels, tabs, tables, and inspector fields
- sufficient contrast for text and cursor labels

#### Scenario: Signal identity consistency
- **GIVEN** a trace is visible in multiple surfaces
- **THEN** its color identity SHALL remain consistent in the tree, plot, quick metrics, minimap, measurement table, and inspector swatch

#### Scenario: Keyboard-driven operation
- **GIVEN** the user navigates without a mouse
- **WHEN** using documented shortcuts or focus traversal
- **THEN** core actions such as run/pause, stop, fit, cursor toggle, measurement toggle, grid toggle, and add expression SHALL remain accessible
