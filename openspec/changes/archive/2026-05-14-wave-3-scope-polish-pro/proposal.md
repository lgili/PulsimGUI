## Why

A half-finished pass to rebrand the scope window as "VirtuScope" /
"SimuScope v1.0" left it visually inconsistent with the rest of
PulsimGui: two different brands ("VirtuScope" top-left, "SimuScope
v1.0" top-right), and the surrounding UX still carries the
duplication paper-cuts the v0.9.0 audit catalogued:

- **Stats triplicate**: the channel-strip card already shows RMS /
  Peak / Avg, but the bottom drawer repeats the same numbers as
  chips, and the status bar repeats them yet again. Eye doesn't
  know where to land.
- **Toolbar with 14+ buttons in one flat row**, no visual grouping,
  no separators — even an experienced user can't memorise it.
- **Sidebar rail** carries five vertical icons (signals, cursors,
  table, layers, eye) without labels or tooltips that survive a
  glance — discoverability is poor.
- **Bottom-bar duplication**: a "Fit / Full Range / + Measure /
  Expand" cluster sits next to a status bar that says "Ready · Scope
  Mode · Sample rate: … · Δt — · ΔY —" in a smaller font with the
  same information.
- **Empty state** when no signals are connected reads "No signals
  to plot. Connect scope channels and run simulation." in 11 pt
  text shoved into a corner of an otherwise blank canvas — the
  user has no idea what to do next.

The shipped v0.9.0 release carries this regression to end users; my
mandate is to ship a clean replacement before the user's next work
session.

## What Changes

### Item A — Drop the alien brands, restore Pulsim identity

- The scope's top-left brand label becomes **"Scope"**, paired
  with the standard `pulsim` glyph already used elsewhere.
- The top-right version string becomes **`Scope · PulsimGui <v>`**
  where `<v>` is the active GUI version pulled from
  `pulsimgui.__version__`. The unrelated "v1.0" string disappears.
- The Qt window title goes from "Scope1 — VirtuScope" to
  "Scope1 — PulsimGui Scope".

### Item B — Single source of truth for inline stats

- The bottom "chip strip" (`RMS / Peak / Mean / Δt / ΔY`) is
  removed. The channel-strip card already shows the same numbers
  bigger and right next to the trace name.
- The window status bar collapses to `Sample rate: N · ⓘ tooltip`
  plus a one-line readiness phrase ("Idle" / "Streaming" /
  "Ready — N signals"). Δt / ΔY belong to the cursor panel only.

### Item C — Group toolbar buttons + add separators

The 14 toolbar buttons are reorganised into four labelled groups
with thin vertical separators:

- **Playback**: Run · Pause · Stop · Step
- **View**: Fit · Reset zoom · Snapshot
- **Tools**: Cursors · Math · FFT
- **Layout**: Toggle panels · Expand

Each button gets a tooltip with its keyboard shortcut so the icon
ambiguity is fixable on hover.

### Item D — Labelled sidebar rail

The vertical rail's five icons gain a 9 pt label below the glyph
(Signals / Cursors / Tables / Views / Measure). The rail expands to
a slightly wider 48 px so the labels render without truncation;
existing collapse behaviour is preserved.

### Item E — Hero empty state

When no signals are plotted the scope shows a card centred in the
canvas (similar to the welcome overlay) with three guided actions:

1. **Open project** (only when no project is open)
2. **Auto-add probes** — adds a voltage probe to every uniquely
   named electrical node up to a sensible max
3. **Run simulation** (calls `MainWindow.action_run.trigger`)

Plus a one-paragraph explanation: "Drop a scope component on a
node, run the simulation, and the captured waveforms appear here".

## Impact

- Affected specs: `waveform-viewer` (delta).
- Affected code:
  - `src/pulsimgui/views/scope/scope_window.py` — brand labels,
    toolbar grouping, sidebar rail labels, status-bar dedup,
    empty-state card.
  - Existing scope tests under `tests/test_views/test_scope_*` —
    adjust assertions that mention the old brand strings.
- Backwards compatible — no public API changes.
