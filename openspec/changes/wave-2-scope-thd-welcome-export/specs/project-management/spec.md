## ADDED Requirements

### Requirement: Recent-projects card on welcome surface
The welcome surface's "Recent projects" card SHALL show up to five entries from `SettingsService.recent_projects`, ordered most-recent first.

#### Scenario: Recent list shows after first save-and-reopen
- **GIVEN** the user has saved at least one `.pulsim` file in the current OS user account
- **WHEN** the welcome surface renders
- **THEN** the Recent projects card SHALL list up to five recent file basenames in chronological order, each clickable to reopen

#### Scenario: Click on stale entry shows clear error
- **GIVEN** a recent-projects entry whose file was deleted or renamed outside the app
- **WHEN** the user clicks it
- **THEN** the app SHALL show a non-fatal toast (`File not found: <path>`) and remove that entry from the recent-projects list
