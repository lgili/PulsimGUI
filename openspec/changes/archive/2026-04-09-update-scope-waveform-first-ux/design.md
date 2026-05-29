## Context
The standalone scope workbench already supports menus, toolbar actions, sidebars, inspector editing, bottom measurements, and analysis tabs. Functionally it is ahead of a basic viewer, but the current expanded layout still lets chrome overwhelm the plot.

A visual review of the live scope identified four core failures:
- expanded layouts reduce the plot too aggressively
- mixed-scale traces are overlaid in ways that obscure lower-amplitude signals
- the plot surface is not visually distinct enough from shell chrome in light themes
- too many simultaneous bands compete below and around the plot

## Goals / Non-Goals
### Goals
- Preserve the waveform as the dominant surface in normal desktop usage.
- Keep the scope fully theme-aware while preserving a dedicated analysis surface for the plot.
- Reduce cognitive and spatial competition between sidebars, inspector, quick metrics, timeline controls, and the detailed drawer.
- Make default trace composition safer for power-electronics waveforms with large dynamic range differences.

### Non-Goals
- Introduce brand-new analysis modes beyond Scope / FFT / Compare.
- Redesign the host application shell outside the scope window.
- Replace the existing scope workbench architecture or persistence model.

## Decisions
### Decision: Waveform-first startup and reset layout
A fresh scope window and `Reset Layout` SHALL restore a waveform-first state:
- signals panel collapsed
- inspector collapsed
- bottom drawer collapsed
- central plot receives the maximum remaining space

This is the safest default because it preserves first-read comprehension and makes chrome opt-in instead of mandatory.

### Decision: Adaptive panel budget instead of fixed chrome entitlement
The scope SHALL treat left panel, right inspector, and bottom drawer as competing consumers of plot area. When the available window size is constrained, the UI SHALL prefer one of these strategies over permanent compression:
- collapse a panel
- compact a panel further
- render the inspector as an overlay or temporary surface
- cap drawer height and switch to content-fit behavior

Implementation guideline:
- at common desktop sizes around `1600x980`, the plot should remain visually dominant even when one major auxiliary surface is open
- opening all auxiliary surfaces simultaneously should trigger adaptive behavior rather than blindly shrinking the plot

### Decision: Automatic mixed-scale composition
Default trace composition should minimize the chance that one trace visually erases another.

The composition engine should apply this heuristic order:
1. Different units: prefer separate pane or alternate axis rather than same-axis overlay.
2. Same unit but strongly different dynamic range: prefer stacked panes or alternate axis.
3. Comparable unit and range: overlay is acceptable.

Implementation guideline:
- use unit metadata first when present
- otherwise use signal statistics / visible-range amplitude ratio
- keep manual override available through inspector and context menu

### Decision: Dedicated plot-surface tokens inside ThemeService
The scope must continue to honor `ThemeService`, but the plot itself should use analysis-specific tokens distinct from shell chrome.

This means:
- the application theme still controls the source palette
- the plot uses derived tokens tuned for trace contrast, grid readability, and cursor overlays
- in light-shell themes, the plot may remain dark-neutral or high-contrast neutral if that yields better engineering readability

### Decision: Compact chrome and non-duplicated bottom information
The lower scope area should separate two modes:
- collapsed mode: one slim persistent strip for navigation / quick context
- expanded mode: detailed measurement drawer with table

When the drawer is expanded:
- redundant quick metrics should collapse, merge, or hide
- the drawer height should fit content up to a bounded cap
- the plot should lose as little height as possible

### Decision: Compact inspector and signals panel density
The signals panel and inspector should remain available, but their internal density should be optimized for analysis rather than forms.

This means:
- shorter rows
- smaller headers
- tighter grouping
- less dead whitespace
- action hierarchy that favors direct manipulation over oversized form controls

## Risks / Trade-offs
- Automatic pane or axis separation may surprise users who expect every signal to overlay by default.
  - Mitigation: keep manual override obvious and persistent.
- A dark plot inside a light shell creates a stronger visual seam.
  - Mitigation: use theme-derived border and plot-container tokens so the transition feels intentional.
- Overlay inspector behavior adds more layout states to test.
  - Mitigation: define deterministic breakpoint/state rules and add headless tests for them.

## Validation Plan
- Headless tests for fresh-open and reset-layout default states.
- Headless tests for drawer compaction and adaptive panel behavior.
- Headless tests for automatic trace grouping when units or amplitude ratios conflict.
- Manual screenshot validation in light and dark themes at approximately `1600x980`.
