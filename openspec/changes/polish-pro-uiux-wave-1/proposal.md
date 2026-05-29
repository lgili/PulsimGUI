## Why

The May 2026 UI/UX audit (`docs/ux-audit-2026-05.md`) catalogued five
observable regressions, six information-architecture gaps, and a long
list of polish opportunities. The first wave (P0) is purely bug
restoration — the status bar still reads "Pulsim 0.5.1" after
Pulsim 0.9.0 shipped, opening a project doesn't auto-fit, the toolbar
duplicates undo/redo, component card labels truncate, and shortcut
hints don't respect the macOS modifier glyphs.

The second wave (P1) targets the items that the audit identified as
"what separates polished from professional-tool-grade": Run Bar,
solver pill in the status bar, dirty / stale / unsaved indicator
triple, empty-state action cards, and inline diagnostics. These are
the bits a PSIM or PLECS user notices the moment they open the app.

This proposal bundles the P0 wave (must-ship) with the achievable
slice of P1 (high-leverage, low-risk). Items judged too ambitious for
a single release wave (split-view YAML editor, generalized command
palette, history time-travel, full icon redraw) are explicitly deferred
to wave 2.

## What Changes

### P0 — Polish patch (no API breaks)

- **Status bar version pin**: read `pulsim.__version__` at app startup
  and render in the status bar's "backend" segment. Falls back to
  "unknown" if pulsim is not importable.
- **Auto-fit on open**: `_open_project_file` ends with a
  `view.fit_to_content()` call (animated, 250 ms ease-out).
- **Toolbar de-duplication**: the second undo/redo cluster is removed.
  History stays the file undo/redo; the action that previously occupied
  the duplicate slot is dropped.
- **Card label truncation fix**: longer component names ("Transformer",
  "Sat. Inductor") render with auto-shrunk font (down to a configured
  floor) and Qt's elided-text fallback. Full name shows on
  hover/tooltip.
- **Platform shortcut rendering**: a new
  `pulsimgui.utils.shortcut_format(key_sequence)` helper renders
  `⌘+M` on macOS and `Ctrl+M` on Windows/Linux. Adopted in the palette
  cards, tooltips, and menus.

### P1 — Information architecture wave

- **Solver pill**: a segmented widget in the status bar shows the
  current integrator + dt + linear solver + adaptive flag, color-coded
  by last-run convergence health (green / amber / red). Clicking the
  pill opens the Simulation Settings dialog focused on the solver
  section.
- **Dirty / stale / unsaved indicator triple**: three independent
  pieces of state get distinct visual treatment:
  - **File dirty** (parameters edited but not saved) — title bar shows
    `* unsaved`.
  - **Simulation stale** (parameters edited since the last successful
    run) — every touched component gets a small amber dot at the corner
    of its bounding rect.
  - **Waveform stale** (scope is showing data from a previous run that
    no longer matches the schematic) — scope window header reads
    "stale" with a one-click "Re-run" button.
- **Empty-state action cards**: when no schematic is loaded, the
  canvas shows four action cards (Blank schematic / Quick-add /
  Templates / Recent files) instead of a paragraph of text. Each card
  has a hover lift and clicks to act.
- **Inline diagnostics layer**: when YAML emission validation fails
  for a component, the component renders with a red error badge in the
  top-right corner of its bounding rect. Hovering the badge shows the
  error tooltip; clicking jumps the properties panel to the offending
  field with a red outline.
- **Run Bar**: a horizontal control band above the status bar (visible
  whenever a simulation can run) shows: Run / Pause / Stop buttons
  (large, labelled), a progress bar binding to
  `t_current / t_stop`, the elapsed-time readout, and the realtime
  factor (`x.x×`). When idle the bar is collapsed; when running it
  expands and animates the progress bar.

### Deferred (wave 2 — not in this proposal)

- Unified titlebar with breadcrumb + view-switcher
- Project tab in the left rail
- Full color-token + typography scale adoption
- Wire-label collision avoidance
- Net highlighting on hover
- Minimap chrome + corner-snap
- Generalized command palette (multiple prefix modes)
- Console / Output / Problems / Telemetry dock
- Split-view YAML editor
- History panel + time-travel
- Full icon-set redraw
- Live simulation cursor

These items remain on the wave-2 backlog tracked in the audit doc.
Several (e.g. the command palette) build on top of the wave-1
infrastructure (e.g. the Run Bar shares state with the simulation
service), so the order matters.

## Impact

- Affected specs:
  - `application-shell` — status bar, toolbar, run controls, title bar
  - `schematic-editor` — auto-fit on open, dirty markers, inline
    diagnostics layer
  - `component-library` — card label rendering, shortcut formatting
  - `simulation-control` — solver pill, run bar, stale-waveform flag
- Affected code (new + modified):
  - `src/pulsimgui/utils/shortcut_format.py` (new)
  - `src/pulsimgui/views/widgets/run_bar.py` (new)
  - `src/pulsimgui/views/widgets/solver_pill.py` (new)
  - `src/pulsimgui/views/widgets/empty_state_cards.py` (new)
  - `src/pulsimgui/views/widgets/status_widgets.py` (modify)
  - `src/pulsimgui/views/main_window.py` (modify)
  - `src/pulsimgui/views/library/library_panel.py` (modify — card
    truncation)
  - `src/pulsimgui/views/schematic/items/component_item.py` (modify —
    dirty dot + error badge)
  - `src/pulsimgui/views/schematic/view.py` (modify — auto-fit hook)
  - `src/pulsimgui/services/simulation_service.py` (modify — surface
    progress signals + run-state)
- Backwards compatible: no removed actions, no API changes. All new
  widgets are additive; existing layouts shift to accommodate the Run
  Bar but no panels are removed.
