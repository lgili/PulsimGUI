## Why

The post-v0.8.4 competitive audit (`docs/ux-audit-2026-05.md` + the
PSIM/PLECS comparison delivered May 13) flagged four user-facing
items where PulsimGui still trails the commercial incumbents in
everyday productivity:

1. The scope already does math channels + FFT + windowing, but
   doesn't surface **THD**, **power**, or **energy** as
   first-class readouts. Users have to export CSV and call
   `compute_thd` in Python — PSIM and PLECS show it inline on the
   FFT cursor and in the measurement table.
2. Opening the app drops the user on an empty canvas with a
   paragraph of text. PSIM and PLECS show a **welcome surface**
   with cards for New / Open / Recent / Templates / Gallery.
3. Exporting a schematic for a report goes through a fragile
   right-click "save scene" path. There's no first-class **PNG /
   SVG export** with margin + scale options, and no
   **copy-to-clipboard** flow.
4. The Run Bar's progress segment is wired to a
   `SimulationService.progress` signal that the backend almost
   never emits — so the progress bar looks stuck even when a
   simulation is healthy. Users have no feedback during long
   runs.

These four items together unlock the daily PSIM / PLECS-style
workflow without touching the runtime. They're explicitly Wave 2
in the audit; deeper items (compare 2 runs, bus wires, auto-reroute,
SPICE importer) stay in Wave 3 / Wave 4.

## What Changes

### Item 1 — Scope: THD + Power + Energy

- Add a **THD readout** to the existing FFT page. The user picks
  a fundamental frequency (with a "snap to peak" helper that
  picks the largest in-band bin); the panel computes
  `THD% = 100 · √Σ(A_k²) / A_1` over harmonics 2..N and shows it
  prominently with the spectrum.
- Extend the bottom-drawer measurement table with three new
  optional columns: `THD%`, `P_avg` (only when two signals are
  paired as V/I), and `Energy`. Selectable via the existing "+
  Add Measurement" dialog.
- The math-signal dialog gains two new helper functions:
  `power(va, vb, i)` and `energy(va, vb, i)` so users can derive
  P(t) and E(t) traces without leaving the scope.

### Item 2 — Welcome screen

A new dock overlay that replaces the empty-canvas text whenever
no project is open. Four cards, hover-elevation, single-click
action:

- **New schematic** — opens an empty `.pulsim` with sensible
  simulation defaults.
- **Open project…** — invokes the existing open-file dialog.
- **Recent projects** — lists the 5 most-recent files from
  `SettingsService`, click to open.
- **From template** — opens a modal listing the 15 gallery
  topologies (with thumbnails) and copies the chosen one to a
  fresh untitled project so the user can save-as.

The welcome surface hides as soon as a circuit has at least one
component, and re-appears when the canvas is emptied (e.g. File
→ Close).

### Item 3 — Schematic export

A new `File → Export → Schematic Image…` action opens a small
dialog that lets the user pick:

- Format: PNG (default) or SVG.
- Resolution: 1× / 2× / 3× / Custom DPI.
- Background: White / Transparent / Theme.
- Margin: 0 / 16 / 32 / 64 px.

The action also gains a sibling **Edit → Copy Schematic as
Image** (`⌘⇧C` / `Ctrl+Shift+C`) that writes the rendered PNG
to the clipboard so the user can paste straight into a report
draft.

### Item 4 — Run Bar real progress

The simulation service grows two new bits of state — `t_current`
and `t_total` — that are sampled in the existing transient inner
loop every ~10 ms of wall time. When the backend doesn't emit
progress signals (current behavior), the service falls back to
estimating progress from the runtime's `time_array` length vs
the expected `tstop / dt`. The Run Bar binds to this via the
existing `on_progress` slot so the user sees motion immediately
on Run.

## Impact

- Affected specs:
  - `waveform-viewer` — THD / power / energy readouts in scope.
  - `application-shell` — schematic export + welcome surface +
    real progress.
  - `project-management` — recent-projects list now surfaces in
    the welcome cards.
  - `simulation-control` — wall-time-driven progress fallback.
- Affected code:
  - `src/pulsimgui/views/scope/scope_window.py` — FFT THD
    annotation + 3 new measurement columns.
  - `src/pulsimgui/views/scope/measurements.py` (new) — pure
    helper functions for THD / power / energy (so the same
    math is unit-testable without Qt).
  - `src/pulsimgui/views/widgets/welcome_overlay.py` (new) —
    welcome surface widget.
  - `src/pulsimgui/views/main_window.py` — wires welcome surface,
    schematic export action, and the new clipboard action.
  - `src/pulsimgui/services/simulation_service.py` — wall-time
    progress estimator.
  - `docs/user-manual.md` — three new subsections describing the
    new features.
- Backwards compatible — all additions; nothing removed.
