## 1. Spec Alignment
- [x] 1.1 Review the existing `waveform-viewer` requirements and align terminology with the standalone professional scope workbench.
- [x] 1.2 Confirm the interaction contract for waveform-first startup, reset-layout behavior, and adaptive panel budget.

## 2. Layout and Hierarchy
- [x] 2.1 Make fresh-open and reset-layout states restore the waveform-first layout with left panel, inspector, and bottom drawer collapsed.
- [x] 2.2 Implement adaptive panel behavior so auxiliary surfaces do not permanently starve the plot at common desktop sizes.
- [x] 2.3 Reduce toolbar, plot-header, sidebar, and inspector density to return more area to the waveform.
- [x] 2.4 Make the bottom drawer open as a compact, content-fit secondary surface rather than a large permanent band.
- [x] 2.5 Collapse, merge, or hide redundant quick metrics when the detailed drawer is expanded.

## 3. Plot Readability and Composition
- [x] 3.1 Introduce dedicated plot-surface theme tokens derived from `ThemeService` for high-contrast waveform readability in both light and dark shell themes.
- [x] 3.2 Implement automatic composition heuristics for traces with incompatible units or strongly different amplitudes.
- [x] 3.3 Preserve manual overrides for pane assignment, axis assignment, and overlay behavior after automatic composition runs.

## 4. Validation
- [x] 4.1 Add deterministic headless tests for waveform-first defaults and reset-layout restore behavior.
- [x] 4.2 Add deterministic headless tests for adaptive panel states and compact drawer behavior.
- [x] 4.3 Add deterministic headless tests for automatic mixed-scale trace separation.
- [x] 4.4 Run focused scope suites and `openspec validate update-scope-waveform-first-ux --strict`.
