## Why

The current waveform/scope experience is coupled to PulsimGui application layout and does not define a reusable module boundary. This blocks reuse in other desktop products, makes scope evolution harder, and prevents a clear API contract between simulation backends and visualization.

Users also expect a PLECS-like scope workflow for high-confidence signal analysis (cursors, trace data table, saved views, quick trace management), but with a more modern visual system and clearer interaction model.

## What Changes

- Define the scope as a **standalone workbench module** with a host adapter API, so it can run embedded in PulsimGui or be reused in other projects.
- Redefine waveform viewer layout to a PLECS-inspired structure with:
  - collapsible left sidebar for signal/scope management
  - central plotting canvas
  - contextual bottom measurement panel that appears when cursors are enabled
- Expand multi-scope behavior so users can create and manage multiple scopes in one workspace and attach multiple signals per scope.
- Add detailed cursor-and-measurement workflow where users explicitly choose which measurements appear in the bottom panel.
- Add PLECS-inspired data-analysis affordances (saved views, trace list, zoom overview) with a modernized visual design and consistent desktop UX.
- Define persistence and portability rules so scope workspaces can be exported/imported independent of host application internals.

## Impact

- Affected specs: `waveform-viewer`
- Affected code (expected):
  - new standalone scope package/module (e.g., `src/pulsimgui/scope_workbench/` or separately distributable package)
  - host adapter layer for simulation signal streaming
  - waveform UI widgets (sidebar, cursor panel, scope workspace manager)
  - project/session persistence schema for portable scope layouts
  - automated tests for deterministic headless scope behavior
