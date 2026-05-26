## MODIFIED Requirements

### Requirement: Scope Panel Structure

The waveform viewer SHALL be delivered as a standalone scope workbench that can run as a top-level window or as an embeddable panel inside a host application.

The default layout SHALL include:
- a collapsible left sidebar for scopes/signals/traces
- a central plotting area
- a contextual bottom analysis panel that is cursor-driven
- a top action bar and a compact status strip

#### Scenario: Launch in standalone mode
- **GIVEN** a host starts the scope workbench without embedding
- **WHEN** the first workspace is opened
- **THEN** the scope SHALL render as an independent window with its own menu/toolbars and no dependency on PulsimGui dock layout

#### Scenario: Launch in embedded mode
- **GIVEN** a host embeds the scope workbench in its UI
- **WHEN** the scope is shown
- **THEN** the scope SHALL preserve the same internal layout/behavior as standalone mode while delegating only window chrome to the host

#### Scenario: Sidebar collapse behavior
- **GIVEN** the scope sidebar is expanded
- **WHEN** the user triggers collapse
- **THEN** the sidebar SHALL collapse to an icon rail and preserve state for restore

### Requirement: Cursors

The viewer SHALL provide oscilloscope-like cursor interaction and activate contextual analysis UI from cursor state.

#### Scenario: Cursor activation opens contextual panel
- **GIVEN** no cursor is active
- **WHEN** the user enables the cursor tool and places cursor A
- **THEN** the bottom analysis panel SHALL appear automatically

#### Scenario: Dual-cursor metrics
- **GIVEN** cursors A and B are active
- **THEN** the viewer SHALL show at minimum:
  - time at A and B
  - delta time (`Δt`)
  - derived frequency (`1/Δt` when `Δt != 0`)
  - per-trace values at each cursor
  - per-trace delta values between cursors

#### Scenario: Cursor drag update
- **GIVEN** a cursor is active
- **WHEN** the user drags the cursor
- **THEN** all cursor-dependent values in overlays and bottom panel SHALL update continuously

#### Scenario: Cursor deactivation hides contextual panel
- **GIVEN** the bottom panel is visible because of active cursors
- **WHEN** the user disables/removes all cursors
- **THEN** the bottom panel SHALL hide and release its reserved layout space

### Requirement: Measurements

The viewer SHALL let users choose which measurements are visible, with cursor-aware targeting rules.

#### Scenario: User-selected measurement columns
- **GIVEN** the bottom analysis panel is visible
- **WHEN** the user clicks `+ Add Measurement`
- **THEN** the user SHALL be able to add/remove measurement columns such as RMS, Peak, Min, Max, Mean, Period, Frequency, and Duty Cycle

#### Scenario: Measurement interval targeting
- **GIVEN** measurements are configured
- **WHEN** the user chooses the target interval
- **THEN** each measurement SHALL support calculation over:
  - visible window
  - cursor A point
  - cursor B point
  - cursor interval A→B

#### Scenario: Per-scope measurement persistence
- **GIVEN** measurement columns were customized in one scope
- **WHEN** the workspace is saved and restored
- **THEN** each scope SHALL restore its own measurement column configuration

#### Scenario: Unavailable measurement state
- **GIVEN** a selected measurement cannot be computed for the current interval or signal type
- **THEN** the table SHALL show a deterministic placeholder and explanatory tooltip instead of stale values

### Requirement: Multiple Scopes

The system SHALL support creating and managing multiple scopes, each with multiple signals and independent analysis state.

#### Scenario: Add scope
- **GIVEN** a workspace is open
- **WHEN** the user selects `+ Scope`
- **THEN** a new empty scope SHALL be created and become active

#### Scenario: Independent scope state
- **GIVEN** two or more scopes exist
- **WHEN** the user changes zoom/cursor/measurement settings in one scope
- **THEN** the other scopes SHALL remain unchanged

#### Scenario: Multiple signals per scope
- **GIVEN** a scope is active
- **WHEN** the user adds multiple signals to that scope
- **THEN** the scope SHALL render all added signals with per-trace visibility and style controls

#### Scenario: Duplicate scope template
- **GIVEN** an existing scope has configured panes/cursors/measurements
- **WHEN** the user duplicates that scope
- **THEN** a new scope SHALL be created with copied visualization settings and independent future edits

## ADDED Requirements

### Requirement: Standalone Scope Module Isolation

The scope workbench SHALL expose a reusable module boundary that is independent from PulsimGui-specific editors, models, and services.

#### Scenario: Import without PulsimGui shell
- **GIVEN** another Python/Qt project installs the scope module
- **WHEN** it imports and starts the workbench with a compatible adapter
- **THEN** the scope SHALL run without importing PulsimGui application-shell modules

#### Scenario: Optional backend support
- **GIVEN** the real simulation backend is unavailable
- **WHEN** tests or demos use a placeholder adapter
- **THEN** the scope SHALL still render signals and support full UI interactions for deterministic testing

### Requirement: Host Adapter Contract

The scope workbench SHALL communicate with host applications only through a documented adapter contract.

#### Scenario: Signal catalog publishing
- **GIVEN** a host provides available signals
- **WHEN** the scope opens a workspace
- **THEN** the signal list SHALL populate from adapter-published metadata

#### Scenario: Sample streaming
- **GIVEN** simulation samples arrive in batches
- **WHEN** the host publishes a batch through the adapter
- **THEN** relevant traces in active scopes SHALL update without requiring direct host internals access

#### Scenario: Workspace persistence round-trip
- **GIVEN** a configured workspace
- **WHEN** the host requests save and later load
- **THEN** the scope SHALL round-trip layout, cursors, measurements, and trace settings through adapter-compatible serialized state

### Requirement: PLECS-Inspired Analysis Surfaces

The scope SHALL provide analysis surfaces inspired by PLECS workflows while using a modernized UI skin.

#### Scenario: Saved views surface
- **GIVEN** the user stores zoom/time windows
- **THEN** a saved-views surface SHALL list named entries and allow one-click restore

#### Scenario: Trace management surface
- **GIVEN** multiple traces are plotted
- **THEN** a trace management surface SHALL allow selecting current trace, toggling visibility, and modifying trace color/style

#### Scenario: Zoom overview surface
- **GIVEN** plotted data exceeds the visible window
- **THEN** a zoom overview surface SHALL show context and current viewport bounds

### Requirement: Collapsible Sidebar Sections

The left sidebar SHALL organize scope workflow into collapsible sections with persistent expansion state.

#### Scenario: Section persistence
- **GIVEN** the user expands/collapses sections in sidebar
- **WHEN** the workspace is restored
- **THEN** section expansion state SHALL be preserved per workspace

#### Scenario: Keyboard accessibility in collapsed mode
- **GIVEN** sidebar is collapsed to icon rail
- **WHEN** the user navigates by keyboard
- **THEN** each section/action SHALL remain reachable with visible focus indication and tooltip labels

### Requirement: Portable Scope Workspace Files

Scope workspaces SHALL be exportable/importable independently of the host project file.

#### Scenario: Export workspace preset
- **GIVEN** a user configured multiple scopes and measurements
- **WHEN** the user exports workspace preset
- **THEN** the preset SHALL include scope layout, signal bindings, cursor settings, and measurement selections

#### Scenario: Import into another project
- **GIVEN** a workspace preset from project A
- **WHEN** imported into project B
- **THEN** the scope SHALL map known signal IDs and report unresolved IDs with clear non-blocking diagnostics

### Requirement: Rendering Performance for Dense Scope Sessions

The scope SHALL maintain interactive responsiveness for dense multi-scope sessions.

#### Scenario: Dense interactive session
- **GIVEN** a workspace with many active traces across multiple scopes
- **WHEN** the user pans, zooms, or drags cursors
- **THEN** interactions SHALL remain smooth and cursor readouts SHALL update without visible lag under documented target hardware

#### Scenario: Deterministic decimation
- **GIVEN** plotted sample count exceeds display capacity
- **WHEN** the scope decimates for rendering
- **THEN** decimation SHALL be deterministic and SHALL preserve extrema needed for measurement accuracy within defined tolerance
