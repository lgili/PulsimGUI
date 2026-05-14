## ADDED Requirements

### Requirement: File ▸ Export submenu hosts FMU and codegen exports
The application's File menu SHALL contain an Export submenu listing every supported
artifact format, with at minimum "FMU 2.0…" and "C99 controller…" entries reachable
from the new menu actions defined in `simulation-control`.

#### Scenario: Export submenu visible
- **GIVEN** the main window is open with a loaded project
- **THEN** `File ▸ Export` SHALL be a submenu containing entries for at least:
  PNG (schematic), SVG (schematic), SPICE netlist, JSON netlist, FMU 2.0…, C99 controller…

#### Scenario: Entries gated on project state
- **GIVEN** no project is loaded
- **THEN** every entry under `File ▸ Export` that requires circuit state SHALL be disabled

### Requirement: Simulation menu hosts new analysis modes
The application's Simulation menu SHALL list every supported analysis mode as a top-level
menu action, including the new modes defined in `simulation-control`: FRA, Periodic
Steady-State, and Harmonic Balance.

#### Scenario: All analysis modes reachable in one click
- **GIVEN** the main window is open
- **THEN** the Simulation menu SHALL contain at minimum: Run, Pause, Stop, DC Operating
  Point, AC Analysis…, FRA…, Periodic Steady-State…, Harmonic Balance…, Parameter Sweep…,
  Thermal Viewer…, Settings…

#### Scenario: Keyboard shortcuts disclosed
- **GIVEN** the user hovers any Simulation menu action with an associated keyboard shortcut
- **THEN** the menu item SHALL display the shortcut on the right edge of the row
