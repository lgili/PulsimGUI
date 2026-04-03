## 1. Theme Architecture
- [x] 1.1 Replace hard-coded scope shell colors with theme-derived semantic scope tokens.
- [x] 1.2 Separate plot-surface tokens from chrome/control tokens so readability survives both light and dark themes.

## 2. Scope Surface Integration
- [x] 2.1 Update `ScopeWindow.apply_theme()` to style chrome, sidebars, inspector, bottom drawer, menus, and popup controls from `ThemeService`.
- [x] 2.2 Update scope-owned dialogs and transient surfaces, including the math expression dialog, to use the same token contract.
- [x] 2.3 Update `QComboBox` popup item views and `QMenu` styling for scope-specific controls.

## 3. Child Widgets
- [x] 3.1 Refactor waveform-viewer child panels that currently override the app theme with scope-local dark colors.
- [x] 3.2 Ensure signals panel and measurements panel remain visually consistent when the app theme changes.

## 4. Validation
- [x] 4.1 Add deterministic tests for theme propagation to standalone scope dialogs, menus, and combo popups.
- [x] 4.2 Run focused headless scope test suites and OpenSpec validation.
