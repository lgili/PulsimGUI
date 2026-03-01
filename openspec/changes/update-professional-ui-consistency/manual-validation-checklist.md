# Manual UI Validation Checklist

Date: 2026-02-21  
Change: `update-professional-ui-consistency`

## Scope

This checklist is the acceptance path for these OpenSpec tasks:

- `2.4` Runtime theme switch does not require restart and leaves no stale colors.
- `3.4` Tooltip labeling and icon-only action discoverability are clear.
- `4.4` Selection and wire visuals remain legible in all built-in themes.
- `7.4` Thermal multi-series plots remain readable in all built-in themes.

## Preconditions

1. Run app from workspace with local sources:

```bash
PYTHONPATH=src python3 -m pulsimgui
```

2. Use a project that has:
- One schematic with at least 6 components and 5+ wires.
- One transient result with at least 4 signals.
- One thermal result with at least 4 devices.

3. Validate all built-in themes:
- `light`
- `dark`
- `modern_dark`

4. Validate at these window widths (desktop):
- `1600 px` (wide)
- `1280 px` (default)
- `1024 px` (narrow)

## A. Runtime Theme Switching (`2.4`)

1. Open app in `light` theme.
2. Switch to `dark`, then `modern_dark`, then back to `light`.
3. Repeat sequence while:
- Schematic has selected components.
- Waveform viewer is visible with traces/cursors enabled.
- Thermal viewer dialog is open with data.

Expected:
- No restart required.
- No stale colors in toolbar, overflow icon, minimap, status widgets, waveform, thermal, schematic overlays.
- Context menu colors follow active theme immediately.
- No console exceptions on theme switch.

## B. Toolbar Discoverability (`3.4`)

1. On each width (`1600/1280/1024`), inspect toolbar groups.
2. Hover every icon-only action.
3. Open overflow menu and verify secondary actions remain reachable.

Expected:
- Primary simulation actions stay visible: `Run`, `Pause`, `Stop`, `DC`, `AC`.
- Overflow contains secondary actions (grid/overlays/minimap/sweep/thermal/settings).
- Tooltips are clear and specific.
- No clipped icons or inaccessible controls.

## C. Schematic Legibility (`4.4`)

1. In each theme, open same schematic and zoom levels (`25%`, `100%`, `200%`).
2. Check:
- Grid visibility vs background.
- Wire readability vs component bodies.
- Selection outlines.
- Pin highlight.
- Alignment guides.
- Component drop preview.
- Minimap viewport rectangle and placeholder state.

Expected:
- Wires remain distinguishable from grid and components.
- Selection/overlay signals are visible but not overpowering.
- Minimap viewport is visible in both dark and light backgrounds.

## D. Thermal Multi-Series Readability (`7.4`)

1. Open Thermal Viewer with >=4 devices and non-trivial losses.
2. Validate tabs: `Thermal Network`, `Temperatures`, `Loss Breakdown`.
3. Confirm legend labels, axis text, grid, and series colors in every theme.

Expected:
- Temperature traces are distinguishable across all devices.
- Loss bars (`Conduction`, `Switching`) remain visually separable.
- Axis labels and tick labels keep contrast.
- Table text and headers stay readable.

## Evidence Capture

Save screenshots for each theme:

- `evidence/light-main.png`
- `evidence/dark-main.png`
- `evidence/modern-dark-main.png`
- `evidence/light-waveform-cursors.png`
- `evidence/dark-thermal-multiseries.png`
- `evidence/modern-dark-schematic-overlays.png`
- `evidence/narrow-1024-toolbar-overflow.png`

## Findings Log Template

| ID | Area | Theme | Width | Severity | Observation | Repro Steps | Suggested Fix | Status |
|----|------|-------|-------|----------|-------------|-------------|---------------|--------|
| F-001 | Toolbar | dark | 1024 | P2 | Example | Example | Example | Open |

## Exit Criteria

All items pass in all three themes and all target widths, or remaining failures are logged with severity and follow-up issue owners.
