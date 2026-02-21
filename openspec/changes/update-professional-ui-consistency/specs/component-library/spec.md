## ADDED Requirements

### Requirement: Theme-Compliant Library Surfaces

The component library SHALL use centralized theme tokens for cards, categories, and search surfaces.

#### Scenario: Card and category rendering
- **GIVEN** the component library is visible
- **WHEN** the theme changes
- **THEN** component cards, category headers, hover/selection states, and search chrome SHALL update consistently with active theme tokens

#### Scenario: Icon and accent clarity
- **GIVEN** category accents and iconography are displayed
- **WHEN** light or dark themes are active
- **THEN** icons and accent bars SHALL preserve visual hierarchy without reducing text legibility

### Requirement: Library Styling Token Source

Library visual styles touched by this change SHALL avoid unmanaged hardcoded color literals.

#### Scenario: Styling source for updated library modules
- **GIVEN** library UI styles are edited under this change
- **WHEN** rendering colors are defined
- **THEN** those colors SHALL come from shared theme tokens or approved palette definitions
