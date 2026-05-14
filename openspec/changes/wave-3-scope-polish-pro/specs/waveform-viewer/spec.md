## MODIFIED Requirements

### Requirement: Scope window branding
The scope window SHALL render its brand strings using only the PulsimGui identity, never using prototype names from in-progress design experiments.

#### Scenario: Top-left brand label
- **GIVEN** the scope window is open
- **THEN** the top-left brand label SHALL read exactly "Scope" (paired with the standard PulsimGui glyph)

#### Scenario: Top-right version label
- **GIVEN** the scope window is open
- **THEN** the top-right version label SHALL read "Scope · PulsimGui {version}" where {version} is the active value of `pulsimgui.__version__`

#### Scenario: Qt window title
- **GIVEN** the scope window is bound to a scope component named `Scope1`
- **THEN** the Qt window title SHALL read "Scope1 — PulsimGui Scope" and SHALL NOT contain the substrings "VirtuScope" or "SimuScope"

## ADDED Requirements

### Requirement: Single stat surface per channel
Inline trace statistics (RMS, Peak, Mean) SHALL appear in exactly one place per channel: the channel-strip card adjacent to the trace name.

#### Scenario: No duplication in bottom strip
- **GIVEN** the scope window is open with at least one signal
- **THEN** the bottom-band chip strip SHALL NOT show `RMS`, `Peak`, `Mean`, `Δt`, or `ΔY` chips
- **AND** the channel-strip card SHALL be the only place those numbers render

#### Scenario: Status bar carries readiness + sample rate only
- **GIVEN** the scope window is open
- **THEN** the status bar SHALL show a readiness phrase (`Idle` / `Streaming` / `Ready — N signals`) and `Sample rate: X`
- **AND** SHALL NOT show Δt / ΔY (these are owned by the cursor panel)

### Requirement: Scope toolbar visual grouping
The scope toolbar SHALL group its buttons into four labelled clusters separated by thin vertical separators: Playback, View, Tools, Layout.

#### Scenario: Four groups visible
- **GIVEN** the scope window is open
- **THEN** the toolbar SHALL contain exactly four button groups with a 1 px vertical separator between each pair
- **AND** the Playback group SHALL contain Run / Pause / Stop / Step
- **AND** the View group SHALL contain Fit / Reset zoom / Snapshot
- **AND** the Tools group SHALL contain Cursors / Math / FFT
- **AND** the Layout group SHALL contain Toggle panels / Expand

#### Scenario: Every button has a shortcut tooltip
- **GIVEN** the user hovers any toolbar button
- **THEN** the tooltip SHALL include the keyboard shortcut associated with the action when one exists

### Requirement: Sidebar rail labels
The scope's left vertical rail SHALL display a short text label below each glyph (Signals, Cursors, Tables, Views, Measure) so users can identify the rail's affordances without hovering.

#### Scenario: Rail labels render
- **GIVEN** the rail is in its default collapsed state
- **THEN** each rail glyph SHALL be paired with a 9 pt label beneath it
- **AND** the rail width SHALL be 48 px so the labels render without truncation

### Requirement: Scope empty state hero card
When no signals are plotted the scope SHALL render a centred card with guided actions, replacing the prior single-line text in the canvas corner.

#### Scenario: Card visible when no signals
- **GIVEN** the scope window is open but `len(scope.signals) == 0`
- **THEN** a centred card SHALL render with the heading "No signals yet"
- **AND** three action buttons SHALL be visible: Open project (only when no project is loaded), Auto-add probes, Run simulation
- **AND** a one-paragraph helper SHALL describe how to populate the scope

#### Scenario: Card hides when signals arrive
- **GIVEN** the empty-state card is visible
- **WHEN** the scope receives at least one signal payload
- **THEN** the card SHALL hide and the plot area SHALL fill its slot
