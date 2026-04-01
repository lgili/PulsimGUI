## Context

This change refines the standalone scope workbench into the professional analysis environment approved by the team.

It builds on the already accepted goals of reuse and host isolation, but goes further by defining the exact UX architecture needed to align implementation with the approved VirtuScope-style mockup and the product notes supplied on 2026-03-31.

The resulting scope must feel like a technical desktop instrument:
- plot-first
- dense but readable
- neutral chrome with colorful data
- scalable to multiple scopes, traces, runs, and analysis modes
- deterministic enough for headless tests and workspace persistence

## Goals / Non-Goals

### Goals

- Define a single canonical layout for the professional scope workspace.
- Make the plot area the dominant visual region while keeping analysis controls close at hand.
- Specify a complete interaction contract for menu bar, toolbar, signals panel, plot, inspector, bottom drawer, quick metrics, and status bar.
- Support multiple scopes and multiple signals per scope without ambiguous state ownership.
- Standardize measurement behavior across quick metrics, plot overlays, inspector, and bottom tables.
- Preserve host-agnostic reuse and serialized workspace portability.
- Provide phased implementation guidance so the UI can evolve without losing the approved direction.

### Non-Goals

- Reproduce PLECS or the approved mockup pixel-for-pixel.
- Redesign PulsimGui's entire application shell in this change.
- Replace the existing plotting backend purely for stylistic reasons.
- Require advanced analysis modes such as Bode, XY, or harmonics in the first rollout.

## Approved Reference Model

The approved target is a scope workspace inspired by PLECS, digital oscilloscopes, and the supplied VirtuScope mockup. The UI is organized into six persistent regions:

1. `Menu Bar`
2. `Main Toolbar`
3. `Left Sidebar: Signals Panel`
4. `Central Workspace`
5. `Right Sidebar: Inspector`
6. `Bottom Area`
   - quick metrics strip
   - bottom drawer
   - status bar

The layout remains resizable and must scale from laptop widths to 4K desktops.

### Recommended Geometry

These are design guidelines, not hard-coded constants:
- left sidebar: `240-320 px`
- right inspector: `260-340 px`
- bottom drawer collapsed header: `36-44 px`
- bottom drawer expanded body: `160-260 px`
- menu bar: `28-34 px`
- toolbar: `44-56 px`
- status bar: `28-34 px`

## UX Architecture Decisions

### Decision: The scope uses a plot-first shell with compact top chrome

The plot must remain the dominant element. Menu and toolbar rows are compact, dense, and semantically grouped. The user should never lose sight of the waveform because of oversized chrome.

Top chrome responsibilities:
- `Menu Bar`: application-style commands and toggles
- `Main Toolbar`: high-frequency actions only

Toolbar groups:
- `Simulation`: Run, Pause, Stop, Step
- `Navigation`: Zoom In, Zoom Out, Fit, Pan, Autoscale
- `Analysis`: Cursor, FFT, Measurements, Math
- `Workspace`: Split View, Compare, Export Snapshot, Layout Settings

All toolbar actions require:
- tooltip title
- short description
- shortcut disclosure when applicable
- active/disabled state clarity

### Decision: The left sidebar is the operational source of truth for signals

The `Signals` panel is where users discover, filter, organize, and route traces.

The panel is structured as:
1. header
2. search/filter field
3. hierarchical tree view
4. quick-action footer

Tree hierarchy must support growth:
- runs
- math
- derived signals
- markers/events in future phases

Each signal row carries:
- visibility control
- color swatch
- name
- axis badge
- optional type badge
- selection state

Expected interactions:
- single click selects
- double click renames or opens quick properties
- axis badge cycles assignment
- drag/drop reorders or reassigns to plot/axis
- context menu exposes trace operations

### Decision: The central workspace is tabbed and mode-aware

The central workspace is not a single chart. It is an analysis container with view tabs and per-tab state.

Initial tabs:
- `Scope`
- `FFT`
- `Compare`

Each tab keeps its own visualization state where practical:
- zoom window
- active selection
- local analysis settings

The `Scope` tab contains:
- plot header / active-trace chips when needed
- main plot surface
- minimap / navigator inset in the lower-right region
- overlay layers for cursors, markers, and selection

Supported plot compositions:
- single plot overlay
- multi-axis overlay
- stacked plots

### Decision: The right inspector is contextual and sectioned

The right sidebar is a professional instrument inspector, not a duplicate of the bottom table.

Sections:
- `Trace`
- `Axis`
- `Style`
- `Cursor`
- `Measurements`

The inspector updates from the current selection and supports direct editing with immediate visual feedback.

Inspector edits are authoritative for:
- trace alias and style
- axis assignment and limits
- line style and thickness
- snap mode
- enabled measurements and their scope selector

### Decision: Bottom analysis is split into quick metrics, drawer, and status

The bottom area has three separate responsibilities:

1. `Quick Metrics Strip`
- always visible
- compact summary for the current signal or active interval
- shows cursor-driven values when cursors are active

2. `Bottom Drawer`
- expandable/collapsible
- hosts `Measurements`, `Events`, and `Console` tabs
- remembers last active tab and last height

3. `Status Bar`
- always visible
- compact simulation and measurement state

This avoids conflating transient cursor data with durable analysis tables.

### Decision: Selection and measurement state are shared across surfaces

The same selected trace must be reflected in:
- left signals tree
- active plot emphasis
- right inspector
- measurement table row highlight
- quick metrics strip

The same cursor interval and measurement scope must feed:
- plot overlay labels
- inspector cursor section
- quick metrics
- bottom drawer measurement table
- status bar readouts

This synchronized state is required to avoid contradictory numbers across the workspace.

## Component Map

### High-Level Components

- `ScopeWorkbenchWindow`
- `ScopeMenuBar`
- `ScopeToolBar`
- `SignalsPanel`
- `ScopeWorkspaceTabs`
- `ScopePlotContainer`
- `ScopeInspectorPanel`
- `ScopeBottomArea`
- `ScopeStatusBar`

### Signals Panel Subcomponents

- `SignalsPanelHeader`
- `SignalsSearchField`
- `SignalsTreeView`
- `SignalTreeItemWidget`
- `AddExpressionButton`

### Central Workspace Subcomponents

- `AnalysisTabBar`
- `PlotCanvas`
- `PlotOverlayLayer`
- `PlotHeader`
- `PlotNavigatorInset`
- `QuickMetricsStrip`

### Inspector Subcomponents

- `InspectorTraceSection`
- `InspectorAxisSection`
- `InspectorStyleSection`
- `InspectorCursorSection`
- `InspectorMeasurementsSection`

### Bottom Area Subcomponents

- `BottomDrawerTabs`
- `MeasurementsTable`
- `EventsList`
- `ConsoleView`
- `StatusReadoutBar`

## Data and State Model

The UI is driven by explicit workspace models rather than implicit widget state.

### Entities

#### `Signal`
- `id`
- `name`
- `alias`
- `unit`
- `data_x`
- `data_y`
- `color`
- `visible`
- `axis_id`
- `plot_id`
- `signal_type`
- `source_run_id`
- `style`
- `metadata`

#### `Run`
- `id`
- `name`
- `timestamp`
- `signals`
- `simulation_mode`
- `sample_rate`
- `duration`
- `notes`

#### `PlotView`
- `id`
- `mode`
- `axis_left`
- `axis_right`
- `visible_signal_ids`
- `zoom_state`
- `cursor_state`
- `grid_state`

#### `Axis`
- `id`
- `unit`
- `min`
- `max`
- `autoscale`
- `inverted`
- `scale_type`

#### `CursorState`
- `enabled`
- `x1`
- `x2`
- `y1`
- `y2`
- `snap_mode`

#### `MeasurementSet`
- `target_signal_id`
- `scope`
- `enabled_metrics`
- `values`

#### `WorkspaceState`
- `active_scope_id`
- `active_tab`
- `visible_panels`
- `bottom_drawer_state`
- `layout_preset`
- `selection_state`
- `inspector_section_state`
- `sidebar_section_state`

## Interaction Model

### Primary Workflow A: Analyze signals

1. Run or load simulation results.
2. Filter and select signals in the left sidebar.
3. Show traces in `Scope` tab.
4. Select a trace to update inspector and quick metrics.
5. Enable cursors and measure interval data.
6. Review detailed rows in the bottom drawer.

### Primary Workflow B: Edit trace presentation

1. Select a trace from the tree or plot.
2. Update axis, color, or style in inspector.
3. Plot and row chips update immediately.
4. Persist changes inside workspace state.

### Primary Workflow C: Create math trace

1. Press `Add Expression`.
2. Open formula editor with signal catalog.
3. Validate expression and preview target unit.
4. Insert new trace under `Math` and optionally add it to the plot.

### Primary Workflow D: Compare runs or scopes

1. Load multiple runs.
2. Use left tree and workspace controls to bind traces to scopes.
3. Switch to `Compare` tab for overlaid or separated comparison.
4. Use the same measurement and cursor tools across comparison views.

## Visual System

The workspace uses a neutral instrument shell with colorful data.

### Principles

- panels and chrome remain low-noise
- data colors carry signal identity
- typography is compact and legible
- corners are rounded but restrained
- numbers use tabular alignment where possible

### Signal Identity Rules

A signal color must remain consistent across:
- tree row
- plot trace
- quick metrics marker
- measurement row marker
- minimap preview
- inspector swatch

### Accessibility Rules

- every toolbar button has tooltip text
- keyboard focus must be visible in sidebars, tabs, tables, and inspector inputs
- all high-frequency actions expose shortcuts
- text/line contrast must remain readable in both dark and hybrid-light shells

## Performance Rules

The scope must remain responsive under dense sessions.

Required behaviors:
- efficient redraw
- incremental measurement updates during cursor drag
- viewport-aware rendering and decimation
- no blocking recomputation for simple selection changes
- deterministic table updates under headless tests

Priority order:
1. cursor drag fluidity
2. zoom/pan responsiveness
3. immediate selection sync
4. fast tooltip/crosshair feedback

## Rollout Plan

### Phase 1: Workspace shell and interaction contract

- menu bar and grouped toolbar
- left signals panel structure
- central scope tab and plot layout
- right inspector shell
- quick metrics strip and status bar

### Phase 2: Analysis depth

- bottom drawer tabs
- advanced measurement scope selector
- add-expression editor
- FFT tab parity
- navigator inset and compare behaviors

### Phase 3: Persistence and scalability

- workspace save/restore of full layout state
- multi-run comparison polish
- performance tuning and dense-session validation
- export/reporting polish

## Risks / Trade-offs

- A denser professional layout increases the number of coordinated states.
  - Mitigation: maintain explicit workspace and selection models.
- Right inspector + bottom drawer can duplicate information if not scoped correctly.
  - Mitigation: inspector edits configuration; drawer presents results and logs.
- A faithful professional UI may increase implementation cost versus a generic chart wrapper.
  - Mitigation: phase rollout and reuse component primitives.

## Open Questions

- Whether `Compare` should begin as a mode of the main plot or a fully separate renderer.
- Whether the bottom drawer should auto-expand when cursors are first placed or remain manually opened.
- Whether axis badges should cycle only `L/R` in the first phase or include `New Plot` directly from the tree.
