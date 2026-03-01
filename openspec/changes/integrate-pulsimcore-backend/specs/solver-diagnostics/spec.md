# Solver Diagnostics

## Purpose

Provide detailed diagnostics when simulations fail to converge, helping users understand and fix convergence issues.

## ADDED Requirements

### Requirement: Convergence Diagnostics Dialog

The application SHALL provide a dialog displaying detailed convergence diagnostics.

#### Scenario: Open diagnostics from error
- **GIVEN** a simulation has failed to converge
- **WHEN** the error dialog appears
- **THEN** it SHALL include a "Show Diagnostics" button
- **AND** clicking the button SHALL open the Convergence Diagnostics dialog

#### Scenario: Summary tab
- **GIVEN** the diagnostics dialog is open
- **THEN** the Summary tab SHALL display:
  - Convergence status (Converged/Failed)
  - Total iterations attempted
  - Final residual norm
  - Strategy used (Newton, GMIN Stepping, etc.)
  - Time of failure (for transient)

#### Scenario: Iteration history tab
- **GIVEN** the diagnostics dialog is open
- **THEN** the History tab SHALL display:
  - Plot of residual vs iteration number
  - Table with iteration details (residual, damping, step norm)
  - Visual indication of convergence trend (improving/stalling/diverging)

#### Scenario: Problematic variables tab
- **GIVEN** convergence failed
- **THEN** the Variables tab SHALL display:
  - List of nodes that didn't converge
  - Each entry shows: node name, value, tolerance, error
  - Sorted by worst convergence first
  - Highlighting for voltage vs current variables

#### Scenario: Suggestions tab
- **GIVEN** the diagnostics dialog is open
- **THEN** the Suggestions tab SHALL display context-aware recommendations

### Requirement: Automatic Suggestions

The application SHALL provide intelligent suggestions based on the failure mode.

#### Scenario: Iteration limit reached
- **GIVEN** the solver stopped due to max_iterations
- **THEN** suggestions SHALL include:
  - "Increase maximum iterations (current: N)"
  - "Consider using GMIN stepping for difficult circuits"

#### Scenario: Divergence detected
- **GIVEN** the residual was increasing over iterations
- **THEN** suggestions SHALL include:
  - "Enable voltage limiting to prevent large steps"
  - "Reduce maximum voltage step (current: X V)"
  - "Check for floating nodes in the circuit"

#### Scenario: Stalling detected
- **GIVEN** the residual stopped decreasing but didn't converge
- **THEN** suggestions SHALL include:
  - "Try source stepping to find operating point gradually"
  - "Check for numerical issues (very small component values)"
  - "Increase tolerance if acceptable"

#### Scenario: Singular matrix
- **GIVEN** the solver reported singular matrix
- **THEN** suggestions SHALL include:
  - "Check for floating nodes (nodes with no DC path to ground)"
  - "Add small resistance to suspicious nodes"
  - "Verify all voltage sources have proper connections"

#### Scenario: DC failure before transient
- **GIVEN** DC operating point failed before transient simulation
- **THEN** suggestions SHALL include:
  - "Try pseudo-transient analysis to find DC point"
  - "Manually specify initial conditions"
  - "Simplify circuit to isolate the problem"

### Requirement: Convergence History Tracking

The application SHALL track convergence history from the solver.

#### Scenario: Extract iteration records
- **GIVEN** the solver returns a `ConvergenceHistory`
- **WHEN** results are processed
- **THEN** each iteration record SHALL contain:
  - Iteration number
  - Residual norm
  - Maximum voltage error
  - Maximum current error
  - Damping factor used
  - Step norm

#### Scenario: History not available
- **GIVEN** an older backend version without history support
- **WHEN** diagnostics are requested
- **THEN** a message SHALL indicate "Detailed history not available"
- **AND** basic summary information SHALL still be shown

### Requirement: Per-Variable Convergence

The application SHALL display per-variable convergence status.

#### Scenario: Variable list extraction
- **GIVEN** the solver returns `PerVariableConvergence`
- **THEN** the dialog SHALL display:
  - Variable index
  - Variable name (mapped from circuit nodes)
  - Current value
  - Change in last iteration
  - Tolerance
  - Normalized error
  - Converged status (Yes/No)

#### Scenario: Highlight worst variables
- **GIVEN** per-variable convergence is available
- **THEN** the top 5 worst-converging variables SHALL be highlighted
- **AND** these SHALL be shown first in the list

#### Scenario: Map indices to names
- **GIVEN** variable indices from solver
- **WHEN** displayed in the dialog
- **THEN** indices SHALL be mapped to human-readable names
  - Indices 0 to N-1: Node voltages V(node_name)
  - Indices N to M: Branch currents I(device_name)

### Requirement: Diagnostics Export

The application SHALL allow exporting diagnostics for debugging.

#### Scenario: Export to file
- **GIVEN** the diagnostics dialog is open
- **WHEN** the user clicks "Export"
- **THEN** a file dialog SHALL open
- **AND** the user can save diagnostics as JSON or text

#### Scenario: Export content
- **GIVEN** diagnostics are exported
- **THEN** the export SHALL include:
  - Convergence summary
  - Full iteration history
  - Per-variable status
  - Circuit metadata (number of nodes, devices)
  - Solver settings used

#### Scenario: Copy to clipboard
- **GIVEN** the diagnostics dialog is open
- **WHEN** the user clicks "Copy Summary"
- **THEN** a text summary SHALL be copied to clipboard
- **AND** it SHALL be suitable for pasting into issue reports

### Requirement: Integration with Output Panel

The application SHALL log convergence information to the output panel.

#### Scenario: Convergence failure logging
- **GIVEN** a simulation fails to converge
- **THEN** the output panel SHALL show:
  - Error summary line
  - Iteration count and final residual
  - Top 3 problematic nodes
  - Hint to open full diagnostics

#### Scenario: Verbose convergence logging
- **GIVEN** verbose logging is enabled in preferences
- **THEN** the output panel SHALL show:
  - Each Newton iteration with residual
  - Strategy changes (e.g., "Switching to GMIN stepping")
  - Timestep adjustments (for transient)
