## MODIFIED Requirements
### Requirement: The professional scope workspace SHALL follow a technical visual language where chrome remains neutral and data remains vivid.
The professional scope workspace SHALL follow a technical visual language where chrome remains neutral and data remains vivid, while all scope-owned surfaces continue to honor the active application theme provided by `ThemeService`.

#### Scenario: Theme propagation across scope-owned surfaces
- **GIVEN** the application theme changes between light and dark variants
- **WHEN** the standalone scope workspace reapplies its theme
- **THEN** the scope chrome, inspector, sidebars, bottom drawer, menus, combo popups, and dialogs SHALL all derive their colors from the active application theme
- **AND** no scope-owned surface SHALL fall back to unrelated platform-default light or dark colors

#### Scenario: Plot readability under different app themes
- **GIVEN** the user selects either a light or dark application theme
- **WHEN** the scope plot is rendered
- **THEN** the plot surface MAY use theme-derived contrast tokens distinct from surrounding chrome
- **AND** traces, grid lines, text, overlays, and measurements SHALL remain readable without bypassing `ThemeService`
