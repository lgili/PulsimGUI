## ADDED Requirements

### Requirement: Card Label Truncation
Component library cards SHALL render the component name with platform-consistent typography and never visibly truncate.

#### Scenario: Short label fits naturally
- **GIVEN** a component with a 1–8 character name (e.g. "Resistor")
- **THEN** the card SHALL render the name in a single line at the configured body font size

#### Scenario: Long label auto-shrinks
- **GIVEN** a component with a 9–14 character name (e.g. "Transformer")
- **THEN** the card SHALL render the name in a single line at one font step below the body size

#### Scenario: Very long label uses ellipsis
- **GIVEN** a component with a 15+ character name (e.g. "Sat. Inductor", "Coupled Inductor")
- **THEN** the card SHALL render the name truncated with a Unicode ellipsis and SHALL show the full name in the card's accessibleDescription / tooltip

### Requirement: Platform-Aware Shortcut Rendering
Keyboard shortcut hints displayed in component cards, menu items, and tooltips SHALL respect the host platform's modifier glyph conventions.

#### Scenario: macOS modifier glyphs
- **GIVEN** the application is running on macOS
- **WHEN** rendering a shortcut hint that uses the Cmd modifier
- **THEN** the displayed string SHALL use `⌘` (U+2318) rather than the literal string `Cmd`

#### Scenario: Linux / Windows literal modifiers
- **GIVEN** the application is running on Linux or Windows
- **WHEN** rendering a shortcut hint that uses the Ctrl modifier
- **THEN** the displayed string SHALL use the literal `Ctrl+<key>` form

#### Scenario: Multi-modifier composition
- **GIVEN** a shortcut combining Shift + a letter
- **WHEN** rendered on macOS
- **THEN** the result SHALL be `⇧<letter>` rather than `Shift+<letter>`
