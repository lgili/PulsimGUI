## ADDED Requirements
### Requirement: Scope and Bus Components Catalog
The component library SHALL list scope and signal bus helpers inside the Control Blocks category.

#### Scenario: Electrical scope entry
- **GIVEN** the Control Blocks > Signal Monitoring category is expanded
- **THEN** an "Electrical Scope" component SHALL appear with an icon preview that shows multiple input pins and a display outline, plus a tooltip describing configurable channels

#### Scenario: Thermal scope entry
- **GIVEN** the Control Blocks category is expanded
- **THEN** a "Thermal Scope" component SHALL be available with a tooltip explaining that it plots junction temperatures and loss traces

#### Scenario: Mux/demux entries
- **GIVEN** the Control Blocks > Math Operations category is expanded
- **THEN** "Signal Mux" and "Signal Demux" components SHALL appear with icons depicting grouped wires and channel counts

#### Scenario: Drag metadata
- **GIVEN** one of these components is dragged from the library
- **THEN** the drag preview SHALL show the correct number of pins for the current default channel count, and dropping it SHALL start placement with that default configuration
