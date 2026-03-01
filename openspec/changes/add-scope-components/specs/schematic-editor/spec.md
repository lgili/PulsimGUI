## ADDED Requirements
### Requirement: Scope Components
The schematic editor SHALL expose dedicated electrical and thermal scope components that describe how simulation outputs are captured.

#### Scenario: Configurable inputs
- **GIVEN** a scope component is selected
- **WHEN** the user edits its properties
- **THEN** the user SHALL be able to choose 1–8 input channels, mark each channel as "separate plot" or "overlay", and rename each channel

#### Scenario: Multi-wire overlay
- **GIVEN** a scope input is configured for overlay mode
- **THEN** the editor SHALL allow multiple wires to terminate on that input pin so all connected signals feed the same plot

#### Scenario: Open scope from schematic
- **GIVEN** a scope component exists
- **WHEN** the user double-clicks it
- **THEN** the associated waveform or thermal scope window SHALL open (or be focused if already open)

### Requirement: Wire Alias Editing
Users SHALL be able to assign aliases to wires and nodes directly on the schematic.

#### Scenario: Inline wire rename
- **GIVEN** a wire is selected
- **WHEN** the user presses F2 or uses the context action "Rename Signal"
- **THEN** an inline text field SHALL appear that lets the user assign an alias that is distinct from the auto-generated node name

#### Scenario: Alias metadata propagation
- **GIVEN** a wire alias is defined
- **THEN** the alias SHALL be stored in the project, displayed as an annotation near the wire, and used by scopes, probes, and the global signal list

### Requirement: Signal Mux Components
The editor SHALL provide mux and demux control blocks for bundling scalar signals.

#### Scenario: Configurable mux width
- **GIVEN** a mux component is selected
- **WHEN** the user edits its properties
- **THEN** the user SHALL be able to specify the number of scalar inputs (2–16) and the ordering in which they feed the single output bus pin

#### Scenario: Demux channel labeling
- **GIVEN** a demux component exists
- **THEN** each output pin SHALL show an editable label (defaulting to channel index) so users can map bus lanes to named wires

#### Scenario: Flow with scopes
- **GIVEN** mux/demux blocks are connected between functional blocks and a scope
- **THEN** the schematic SHALL preserve individual signal aliases through the mux/demux so scopes display the expected names
