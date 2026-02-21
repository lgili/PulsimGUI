## Context

PulsimGui already includes a central `ThemeService`, but visual behavior is split between:

- global QSS-driven styling
- custom widgets with local `setStyleSheet(...)`
- pyqtgraph surfaces with direct color assignment
- painter-based overlays using fixed color constants

This split creates a visible mismatch during theme switching and increases maintenance cost for new UI work.

The objective is to move from "styled screens" to a stable visual system where all rendering paths consume a shared theme contract.

## Goals / Non-Goals

### Goals

- Guarantee consistent light/dark rendering across main workflows (draw, configure, run, analyze).
- Remove hardcoded UI color drift by centralizing visual tokens.
- Improve action discoverability and speed in simulation-centric sessions.
- Preserve current feature set while raising visual quality and predictability.
- Keep cross-platform behavior deterministic in Qt/PySide6.

### Non-Goals

- Full interaction model redesign.
- Adding new simulation features.
- Replacing Qt docking with a custom docking framework.
- Building a new plotting backend.

## Decisions

### Decision: Introduce an explicit visual token contract

`ThemeColors` will be expanded and treated as the canonical source for:

- panel/card surfaces and hover states
- validation/warning/error UI states
- context menu and overlay tokens
- plot-specific tokens (plot bg/axis/grid/legend)
- trace/measurement palettes per theme

This removes ad-hoc color selection from view modules.

### Decision: Add a theme bridge for non-QSS renderers

A lightweight adapter layer will map `Theme` to modules that are not fully controlled by QSS:

- pyqtgraph (`PlotWidget`, axes, legend, grid)
- custom `QPainter` overlays (minimap, preview, guides)
- dynamic icon recoloring in status/toolbar/context menus

This keeps QSS for native widgets and uses explicit application for graphics surfaces.

### Decision: Define ThemeAware widget integration contract

Custom views that render their own visuals will expose `apply_theme(theme)` (or equivalent).

Main window theme application will:

1. apply global stylesheet,
2. apply scene colors,
3. call `apply_theme(...)` on registered theme-aware widgets,
4. refresh icon cache and icon-bearing controls.

This sequence avoids partial updates and stale colors.

### Decision: Reframe toolbar by task frequency

Toolbar layout will prioritize frequent loops used in engineering sessions:

1. file/edit primitives,
2. viewport controls,
3. simulation controls (run/pause/stop + analysis entry points),
4. overflow for lower-frequency commands.

This aligns visual prominence with actual user value and reduces menu dependence.

### Decision: Enforce visual consistency guardrails

New or touched UI modules in this change must consume theme tokens.
Hardcoded literals are allowed only for:

- physically meaningful trace semantics explicitly defined in a per-theme palette,
- temporary debugging visuals not exposed in release UI.

## Trade-offs

- Adding bridge code increases initial complexity but sharply reduces style drift over time.
- Some custom widget refactoring is required even when behavior is unchanged.
- Strict tokenization may slow one-off UI experimentation, but improves long-term quality.

## Risks and Mitigations

- Risk: Theme regressions on runtime switching.
  - Mitigation: Add targeted UI regression tests for switch events on key widgets.
- Risk: Reduced trace distinguishability after palette standardization.
  - Mitigation: Validate palettes against contrast and color-distance thresholds.
- Risk: Toolbar changes disrupt existing muscle memory.
  - Mitigation: Keep command set unchanged and preserve shortcuts; adjust only grouping/placement.

## Implementation Plan

### Phase 1: Theme contract and bridge

- Extend theme tokens.
- Implement plotting/overlay/theme-aware adapters.
- Wire main-window propagation sequence.

### Phase 2: Core editor surfaces

- Update schematic overlays/context menus/minimap.
- Update properties and library panels.
- Normalize status widgets.

### Phase 3: Analysis surfaces

- Update waveform and thermal viewers.
- Align measurement/readout styling and legend/axis behavior.

### Phase 4: Validation and polish

- Add regression checks for theme switching and contrast.
- Verify dock/toolbar behavior across window sizes.
- Remove residual hardcoded literals in touched modules.

## Validation Strategy

- Automated:
  - OpenSpec strict validation.
  - Unit/UI tests for runtime theme propagation and no-stale-colors behavior.
- Manual checklist:
  - switch theme during idle editing, active selection, and post-simulation results
  - inspect main shell + minimap + properties + library + waveform + thermal
  - verify toolbar grouping on compact and wide window sizes

## Open Questions

- Should "Modern Dark" remain as a separate built-in theme or be folded into a generalized dark token set?
- Do we want a user-facing preference for compact vs comfortable toolbar density in this change or in a follow-up?
