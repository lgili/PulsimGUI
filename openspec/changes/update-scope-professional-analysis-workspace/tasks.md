## 1. Information Architecture and Models

- [x] 1.1 Align the standalone scope workspace model with the new six-region layout contract
- [ ] 1.2 Formalize selection, cursor, measurement, and panel state ownership in shared scope state models
- [x] 1.3 Define serialization fields for inspector state, quick metrics, bottom drawer, and tabbed analysis modes

## 2. Top Chrome

- [x] 2.1 Implement the scope menu bar with File, View, Simulation, Tools, Window, and Help menus
- [x] 2.2 Rebuild the main toolbar into grouped simulation, navigation, analysis, and workspace actions
- [x] 2.3 Add tooltips, shortcuts, active states, and disabled states for all top-level actions

## 3. Left Signals Panel

- [x] 3.1 Implement the structured `Signals` panel with header, search, hierarchical tree, and footer actions
- [x] 3.2 Support run grouping, math grouping, visibility toggles, axis badges, and context menus
- [x] 3.3 Add deterministic drag/drop and selection synchronization with the plot and inspector

## 4. Central Workspace

- [x] 4.1 Implement tabbed central views for Scope, FFT, and Compare with independent view state
- [x] 4.2 Support overlay, dual-axis, and stacked-plot compositions with consistent trace identity
- [x] 4.3 Implement navigator inset, crosshair/cursor overlays, and plot context menus
- [ ] 4.4 Ensure zoom, pan, fit, and trace selection interactions remain responsive under dense data

## 5. Inspector and Analysis Controls

- [x] 5.1 Implement the right inspector with Trace, Axis, Style, Cursor, and Measurements sections
- [x] 5.2 Make inspector edits update the plot, signals panel, and measurement surfaces in real time
- [ ] 5.3 Implement add-expression flow with validation, unit preview, and optional auto-plot behavior

## 6. Bottom Area

- [x] 6.1 Implement always-visible quick metrics strip with selection-aware summaries
- [x] 6.2 Implement expandable bottom drawer with Measurements, Events, and Console tabs
- [x] 6.3 Add measurement scope controls for full range, visible range, and between cursors
- [x] 6.4 Implement compact status bar with simulation state, mode, sample rate, and cursor readouts

## 7. Persistence, Accessibility, and Validation

- [ ] 7.1 Persist panel sizes, tab state, selected signals, measurement columns, cursor state, and layout presets
- [ ] 7.2 Add keyboard navigation, focus states, shortcuts, and tooltip coverage across the scope workspace
- [x] 7.3 Add deterministic headless tests for sidebar, inspector, plot selection sync, bottom drawer, and session restore
- [x] 7.4 Run `openspec validate update-scope-professional-analysis-workspace --strict`
