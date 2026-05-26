## Context
The professional scope workspace evolved with a custom dark shell that intentionally ignored the global application theme. That delivered a controlled dark visual baseline, but it fractured the styling contract: some widgets follow `ThemeService`, some are re-skinned with scope-local constants, and some Qt popup surfaces fall back to platform defaults.

The requested direction is to restore `ThemeService` as the single source of truth while preserving the scope's readability and technical density.

## Goals / Non-Goals
- Goals:
  - Re-enable full theme propagation inside the scope workspace.
  - Keep the scope readable in both light and dark themes.
  - Eliminate hard-coded dark-only style leaks in dialogs, menus, combo popups, and inspector controls.
  - Preserve deterministic visual identity for traces and cursor overlays.
- Non-Goals:
  - Redesign the scope layout or interaction model.
  - Introduce a new theme system outside `ThemeService`.
  - Rework unrelated application windows.

## Decisions
- Decision: Scope styling will be generated from semantic scope tokens derived from the active `Theme` object.
  - Why: The scope needs tighter contrast control than generic forms, but that can still be expressed as theme-derived tokens instead of hard-coded colors.
- Decision: Plot-area tokens and chrome tokens will be separate.
  - Why: Users may choose a light application theme while still expecting a darker plot surface for waveform contrast.
- Decision: Popup surfaces (`QMenu`, `QComboBox QAbstractItemView`, dialogs) must be explicitly themed inside the scope stylesheet or widget-local styles.
  - Why: These are the main places where platform default colors leak back in.
- Decision: Scope-owned dialogs such as the math expression editor will no longer consume the global theme directly without adaptation.
  - Why: The dialog must follow the same scope token contract as the workspace that opened it.

## Risks / Trade-offs
- Light theme readability can regress if plot and chrome tokens are not separated carefully.
  - Mitigation: Keep plot-specific contrast tokens independent from chrome background tokens.
- Qt popup surfaces may still differ across platforms.
  - Mitigation: Add explicit styling for item views and popup menus, and test headless rendering paths.
- Existing visual tuning for the dark scope may soften.
  - Mitigation: Preserve current spacing/layout and only refactor color/token ownership first.

## Migration Plan
1. Replace scope-local hard-coded shell palette helpers with theme-derived scope tokens.
2. Route scope-owned child widgets through the same token contract.
3. Update dialogs, menus, combo popups, and inspector action surfaces.
4. Add regression tests for theme propagation in the standalone scope.

## Open Questions
- None. The requested direction is explicit: the active application theme must control the scope again.
