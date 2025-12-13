# Proposal: Full PulsimCore Backend Integration

## Why

The GUI currently has a `PulsimBackend` adapter that only supports transient simulation. Critical features like DC operating point, AC analysis, and thermal simulation still use placeholder implementations with synthetic data. Additionally, the backend lacks proper version abstraction - if PulsimCore's API changes, the GUI breaks.

**Current Pain Points:**
1. DC analysis returns hardcoded values instead of calling `pulsim.v2.solve_dc()`
2. AC analysis generates fake Bode plots instead of real frequency response
3. Thermal simulation uses synthetic data instead of actual loss calculations
4. No UI for configuring Newton solver options (iterations, tolerances, limiting)
5. No convergence diagnostics when simulations fail
6. Backend version changes can silently break the GUI
7. No abstraction for future backend alternatives (ngspice, Xyce, etc.)

## What Changes

### 1. Backend Abstraction Layer (NEW)
- **NEW**: `BackendCapabilities` protocol defining all supported operations
- **NEW**: `BackendVersion` class with semantic versioning and compatibility checks
- **NEW**: `BackendRegistry` for discovering and managing multiple backend implementations
- **MODIFIED**: `PulsimBackend` to implement full `BackendCapabilities` interface
- **NEW**: Feature detection (`has_thermal`, `has_ac`, `supported_strategies`)

### 2. DC Operating Point Integration
- **MODIFIED**: `SimulationService.run_dc_operating_point()` to call real backend
- **MODIFIED**: `PulsimBackend` to expose `run_dc()` using `pulsim.v2.solve_dc()`
- **NEW**: DC strategy selection in UI (Auto, GMIN stepping, Source stepping, Pseudo-transient)
- **NEW**: `DCRunResult` with node voltages, branch currents, and convergence info

### 3. AC Analysis Integration
- **MODIFIED**: `SimulationService.run_ac_analysis()` to call real backend
- **NEW**: `PulsimBackend.run_ac()` using `pulsim.run_ac()`
- **NEW**: Real Bode plot data (magnitude, phase, frequencies)

### 4. Thermal Simulation Integration
- **MODIFIED**: `ThermalAnalysisService` to use real backend when available
- **NEW**: `PulsimBackend.run_thermal()` using `pulsim.ThermalSimulator`
- **NEW**: Real Foster network parameters and loss calculations
- **FALLBACK**: Synthetic data when thermal backend unavailable

### 5. Solver Options UI
- **MODIFIED**: `SimulationSettingsDialog` to expose solver configuration
- **NEW**: Newton options (max iterations, voltage limiting, tolerances)
- **NEW**: Integration method selection (BackwardEuler, Trapezoidal, BDF2)
- **NEW**: DC convergence strategy dropdown

### 6. Convergence Diagnostics
- **NEW**: `ConvergenceDiagnosticsDialog` showing iteration history
- **NEW**: Per-variable convergence status (which nodes didn't converge)
- **NEW**: Suggested fixes for common convergence failures

### 7. Version Compatibility
- **NEW**: Backend API version detection and compatibility matrix
- **NEW**: Graceful degradation when features unavailable
- **NEW**: User-facing warnings for version mismatches
- **NEW**: Support for backend hot-swapping without restart

## Impact

### Affected Specs
- `simulation-control` - Major modifications for real DC/AC/thermal
- `thermal-viewer` - Modified to use real thermal data
- **NEW** `backend-abstraction` - New capability for backend management
- **NEW** `solver-diagnostics` - New capability for convergence debugging

### Affected Code
- `src/pulsimgui/services/backend_adapter.py` - Major refactor
- `src/pulsimgui/services/simulation_service.py` - DC/AC integration
- `src/pulsimgui/services/thermal_service.py` - Real thermal integration
- `src/pulsimgui/views/dialogs/simulation_settings_dialog.py` - Solver options UI
- **NEW** `src/pulsimgui/services/backend_registry.py` - Backend discovery
- **NEW** `src/pulsimgui/views/dialogs/convergence_diagnostics_dialog.py`

### Breaking Changes
- `BackendRunResult` signature changes (additional fields)
- `SimulationSettings` dataclass extended with solver options
- Minimum PulsimCore version requirement: 0.2.0+

## Success Criteria

1. DC analysis returns real node voltages matching PulsimCore CLI
2. AC analysis produces valid Bode plots for test circuits
3. Thermal simulation shows real junction temperatures and losses
4. Solver options persist and affect simulation behavior
5. Convergence failures show diagnostic information
6. Backend version mismatch shows user-friendly warning
7. All existing tests pass with real backend
8. GUI works with placeholder when PulsimCore unavailable

## Dependencies

- PulsimCore 0.2.0+ with v2 bindings
- `pulsim.v2.solve_dc()` exposed in Python
- `pulsim.ThermalSimulator` with Foster network support
- `pulsim.run_ac()` for frequency analysis
