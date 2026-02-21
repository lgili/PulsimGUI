## ADDED Requirements

### Requirement: Theme-Compliant Parameter Presentation

The parameter editor SHALL present section hierarchy, inputs, and validation states using the active theme.

#### Scenario: Panel rendering on theme switch
- **GIVEN** the properties panel is visible with a selected component
- **WHEN** the user changes theme
- **THEN** section headers, icon controls, labels, and empty-state messaging SHALL update to the new theme without stale styles

#### Scenario: Validation state consistency
- **GIVEN** a parameter field enters invalid state
- **WHEN** validation feedback is shown
- **THEN** border, emphasis, and text cues SHALL follow shared error/warning tokens used across the application

### Requirement: Parameter Editor Styling Token Source

Parameter editor styling touched by this change SHALL rely on centralized theme tokens.

#### Scenario: Styling source for touched parameter widgets
- **GIVEN** parameter panel widgets are updated under this change
- **WHEN** colors are defined for normal, hover, active, or invalid states
- **THEN** colors SHALL come from theme tokens rather than local hardcoded literals
