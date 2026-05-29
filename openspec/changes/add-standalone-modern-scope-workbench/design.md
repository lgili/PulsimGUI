## Context

This change defines a new scope architecture and UX contract that is **independent from PulsimGui shell layout** and can be reused in other desktop simulation projects.

The design target is:
- functional parity with core PLECS scope analysis workflows
- improved modern visual quality and readability
- deterministic behavior suitable for CI and headless GUI tests

### Benchmark Inputs (PLECS)

Reference sources used to derive interaction behaviors:
- [PLECS Data Visualization page](https://www.plexim.com/products/plecs/data_visualization)
- [PLECS User Manual 4.9 (Scope data window section)](https://www.plexim.com/sites/default/files/plecsmanual.pdf)
- [PLECS scope screenshot](https://www.plexim.com/sites/default/files/pictures/scope_cycloconv.png)
- [PLECS Fourier/scope data screenshot](https://www.plexim.com/sites/default/files/pictures/scope_fourier_cycloconv.png)

Visual references:

![PLECS Scope Reference](https://www.plexim.com/sites/default/files/pictures/scope_cycloconv.png)

![PLECS Fourier Reference](https://www.plexim.com/sites/default/files/pictures/scope_fourier_cycloconv.png)

## Goals / Non-Goals

### Goals

- Build a scope module that can run without importing PulsimGui application shell code.
- Provide a reusable API contract for host applications to publish signals and receive UI events.
- Preserve PLECS-like signal inspection workflows (cursor deltas, trace table, saved views, zoom context).
- Add modern UX behavior:
  - collapsible sidebar
  - cleaner typography and spacing
  - contextual bottom panel for cursor measurements
- Support many scopes and many signals per scope with predictable performance.

### Non-Goals

- Reproduce PLECS visual assets one-to-one.
- Implement new simulation solvers in this change.
- Introduce network dependencies for scope functionality.

## Decisions

### Decision: Standalone module with explicit host adapter

The scope workbench will be delivered as a standalone package boundary, with no direct imports from schematic editor, project tree, or app-shell internals.

Host applications integrate through a typed adapter interface (signals in, commands/events out):

- `register_workspace(workspace_id, metadata)`
- `publish_samples(workspace_id, batch)`
- `publish_signal_catalog(workspace_id, signals)`
- `subscribe_ui_events(callback)`
- `load_workspace_state(serialized_state)` / `save_workspace_state()`

This allows embedding in PulsimGui and reuse in unrelated Qt/Python desktop projects.

### Decision: Workspace-first scope model

A workspace owns multiple scopes. Each scope owns:
- one or more plot panes
- assigned signals
- axis/cursor configuration
- local measurement configuration

Data model (logical):
- `ScopeWorkspace`
- `ScopeView`
- `PlotPane`
- `SignalRef`
- `CursorSet`
- `MeasurementSelection`
- `SavedView`

### Decision: Sidebar is collapsible, not removable

The left sidebar remains part of the layout but can collapse to an icon rail.

Behavior:
- expanded width: 280 px default
- collapsed width: 52 px icon rail
- toggle action in header + shortcut `Ctrl+B`
- state persisted per workspace

Sidebar sections:
- Scopes list (add/duplicate/remove)
- Signals catalog (filter + drag/drop)
- Active traces list (visibility, color, isolate)
- Quick actions (add expression, import layout)

### Decision: Bottom panel is contextual and cursor-driven

The bottom measurement panel is hidden until cursors are activated.

State machine:
- `NoCursor`: panel hidden
- `SingleCursor`: panel visible with cursor A metrics only
- `DualCursor`: panel visible with A/B and delta metrics

Rules:
- panel opens automatically when user enables cursor tool or creates cursor A
- panel closes when all cursors are disabled
- user chooses measurement columns via `+ Add Measurement`
- measurements can be scoped to:
  - full visible window
  - cursor A
  - cursor B
  - interval A→B

### Decision: PLECS-like analysis affordances with modernized UI

We keep PLECS-like workflow concepts while modernizing style and interaction:
- saved views list (named zoom/time windows)
- trace manager (active trace focus and visibility)
- zoom overview mini-panel
- data table with selectable measurement columns

Modernization constraints:
- stronger spacing hierarchy
- color tokens with accessible contrast
- reduced chrome/noise around chart area
- smooth but subtle transitions (< 180 ms)

### Decision: Multi-scope and multi-signal scalability

Users can create many scopes in one workspace and attach many traces per scope.

Minimum support target:
- at least 12 scopes per workspace
- at least 32 visible traces per scope
- smooth cursor drag and zoom interactions at 30+ FPS on recommended hardware

### Decision: Portable persistence schema

Scope state is serialized as host-agnostic JSON/TOML-friendly data:
- scope layout/tree
- signal bindings by stable IDs (not UI index)
- cursor state
- selected measurement columns
- saved views
- panel collapse state
- visual preferences

The serialized format must be importable into another host project as long as required signal IDs are resolvable.

## Interaction Spec (Detailed)

### 1. Add and route signals

1. User creates/opens a scope in sidebar.
2. User drags one or more signals from catalog into scope pane.
3. Dropping on empty area creates a new plot pane; dropping on existing pane overlays trace.
4. Each trace gets deterministic color assignment and appears in trace manager.

### 2. Cursor workflow and bottom panel

1. User enables cursors from toolbar (`Cursor` button).
2. Cursor A appears on first click; bottom panel opens.
3. Optional second click creates cursor B.
4. Bottom panel shows base metrics (`tA`, `tB`, `Δt`, `f=1/Δt`) and selected user columns.
5. User clicks `+ Add Measurement`, chooses metric types (RMS, Peak, Min, Max, Mean, etc.).
6. Selected metrics appear as table columns and update in real time while dragging cursors.

### 3. Sidebar collapse/expand

1. User clicks collapse chevron in sidebar header.
2. Sidebar animates to icon rail; labels hide, icons remain.
3. Hovering icon shows tooltip and optional flyout preview.
4. Expanding restores scroll position and section expansion state.

### 4. Multi-scope management

1. User clicks `+ Scope` in scope list.
2. New scope opens with default empty pane.
3. User may duplicate a scope to copy style/cursor/measurement setup.
4. Each scope keeps independent state while sharing the global signal catalog.

## Risks / Trade-offs

- Added architecture layers increase initial implementation effort.
  - Mitigation: strict adapter contract and incremental rollout.
- High trace counts may impact rendering performance.
  - Mitigation: decimation, viewport-level culling, batched redraw.
- Reuse across projects can expose integration edge cases.
  - Mitigation: host compatibility tests with placeholder backend.

## Validation Plan

- Unit tests for cursor math, measurement calculations, saved-view serialization.
- Integration tests for adapter contract with a fake backend publisher.
- Qt headless tests (`QT_QPA_PLATFORM=offscreen`) for sidebar collapse and cursor panel state transitions.
- Regression snapshots for visual hierarchy (expanded/collapsed/sidebar + bottom panel states).

## Migration Plan

1. Introduce standalone scope module and adapter API behind a feature flag.
2. Implement compatibility bridge from existing waveform viewer usage.
3. Migrate one workflow at a time (single scope, then multi-scope, then saved views/trace manager).
4. Deprecate legacy tightly coupled viewer path after parity validation.

## Open Questions

- Should duplicated scopes share signal bindings by reference or by copy?
- Should the bottom panel support per-signal templates (e.g., power stage preset vs control preset)?
- Should scope workspaces be saved inside project file only, or also as standalone reusable presets?
