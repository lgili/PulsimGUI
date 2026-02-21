## 1. Theme System Foundation

- [x] 1.1 Expand `ThemeColors` to include explicit tokens for overlays, context menus, plot surfaces, and measurement/readout accents.
- [ ] 1.2 Define a clear mapping between existing UI surfaces and new tokens (documented in code comments/design notes).
- [x] 1.3 Implement helper utilities/adapters for applying theme tokens to non-QSS rendering paths.
- [x] 1.4 Add fallback behavior for unknown/missing tokens to prevent broken rendering.

## 2. Main Window Theme Propagation

- [x] 2.1 Refactor main theme application flow to include stylesheet + scene + theme-aware custom widgets in deterministic order.
- [x] 2.2 Register and apply theme updates to minimap, properties panel, waveform viewer, thermal viewer, and status widgets.
- [x] 2.3 Ensure toolbar and overflow icons refresh correctly after theme switches.
- [ ] 2.4 Verify runtime theme switch does not require restart and leaves no stale widget colors.

## 3. Toolbar IA and Responsiveness

- [x] 3.1 Reorganize toolbar groups by workflow frequency (file/edit, viewport, simulation).
- [x] 3.2 Keep command parity while moving low-frequency actions to overflow.
- [x] 3.3 Implement responsive behavior for narrow widths without clipping core simulation controls.
- [ ] 3.4 Validate tooltip labeling and action discoverability for icon-only controls.

## 4. Schematic and Overlay Consistency

- [x] 4.1 Theme-align schematic context menus and remove hardcoded menu colors from view code.
- [x] 4.2 Theme-align minimap surfaces, viewport box, and placeholder states.
- [x] 4.3 Theme-align drop preview, pin highlight, and alignment guide overlays where applicable.
- [ ] 4.4 Validate selection/wire visuals remain legible in all built-in themes.

## 5. Library and Parameter Panel Consistency

- [x] 5.1 Refactor library card/category/search visuals to consume shared theme tokens.
- [x] 5.2 Normalize category accent handling for light/dark readability.
- [x] 5.3 Refactor properties panel section headers, icon buttons, validation states, and no-selection state to use theme tokens.
- [x] 5.4 Ensure invalid-value feedback is visually consistent with global warning/error semantics.

## 6. Waveform Viewer Theming

- [x] 6.1 Add theme application path for waveform viewer (plot bg, grid, axes, legend, controls, readouts).
- [x] 6.2 Replace hardcoded measurement panel colors with tokenized values.
- [x] 6.3 Introduce per-theme trace palette with distinguishable colors and stable ordering.
- [x] 6.4 Verify cursor/readout colors keep sufficient contrast in both light and dark themes.

## 7. Thermal Viewer Theming

- [x] 7.1 Add theme application path for thermal viewer plots/tables/captions.
- [x] 7.2 Replace fixed dark backgrounds with theme-token mapping.
- [x] 7.3 Align loss chart and temperature trace palettes with waveform/system palette strategy.
- [ ] 7.4 Validate readability of multi-series displays in all built-in themes.

## 8. Consistency Guardrails and Tests

- [ ] 8.1 Add regression tests for runtime theme switching on key widgets.
- [ ] 8.2 Add checks/tests ensuring touched modules do not introduce new unmanaged hardcoded color literals.
- [ ] 8.3 Add focused tests for toolbar grouping/overflow behavior across window sizes.
- [ ] 8.4 Run targeted manual UI checklist and record findings/fixes (see `manual-validation-checklist.md`).

## 9. Documentation and Release Notes

- [ ] 9.1 Update user/developer docs to describe the visual token model and theme propagation expectations.
- [ ] 9.2 Document extension guidance for future custom widgets (`apply_theme` contract).
- [ ] 9.3 Add release notes summarizing visual consistency improvements and any toolbar layout changes.
