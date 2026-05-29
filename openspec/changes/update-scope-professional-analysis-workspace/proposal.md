## Why

The standalone scope workbench already establishes isolation and reusable workspace behavior, but the product still lacks a detailed, authoritative UX specification for the professional scope experience the team wants to ship.

The approved VirtuScope-style mockup and the new functional notes define a much richer target than the current waveform specification: a full analysis workspace with compact menu/toolbar chrome, structured signal management, right-side inspector, multi-surface measurements, and synchronized state across all analysis surfaces. Without a dedicated OpenSpec change for this target, implementation will continue to drift and regress toward ad-hoc UI decisions.

## What Changes

- Upgrade the waveform viewer specification from a generic scope panel into a professional analysis workspace with a canonical six-region layout:
  - menu bar
  - main toolbar
  - left signals sidebar
  - central workspace
  - right inspector
  - bottom area (quick metrics, drawer, status bar)
- Define the interaction contract for the left signals tree, central plot tabs, measurement overlays, bottom drawer, and right inspector.
- Specify how multiple scopes, multiple runs, multiple traces, math expressions, and analysis tabs coexist in one reusable workspace.
- Define synchronized selection, cursor, axis, and measurement behavior across signals panel, plot, inspector, and tables.
- Document the visual-density, accessibility, performance, and persistence rules required to make the scope feel like a professional desktop instrument rather than a generic chart widget.
- Break implementation into phased tasks so future work can proceed without reinterpreting the approved mockup each time.

## Impact

- Affected specs:
  - `waveform-viewer`
- Affected code (expected):
  - `src/pulsimgui/views/scope/scope_window.py`
  - `src/pulsimgui/views/waveform/waveform_viewer.py`
  - standalone scope workspace/session models and persistence helpers
  - measurement/selection synchronization helpers
  - toolbar/menu/icon resources used by the scope workbench
  - headless Qt tests covering layout, cursor, inspector, and persistence behavior
