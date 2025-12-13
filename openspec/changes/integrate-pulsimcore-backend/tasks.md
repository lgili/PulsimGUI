# Tasks: PulsimCore Backend Integration

## 1. Backend Abstraction Layer

- [x] 1.1 Create `BackendCapabilities` protocol in `services/backend_protocol.py`
  - Define all required methods with type hints
  - Use `@runtime_checkable` for isinstance checks
  - Document each method with docstrings

- [x] 1.2 Create result dataclasses in `services/backend_types.py`
  - `DCResult` with node_voltages, branch_currents, convergence_info
  - `ACResult` with frequencies, magnitude, phase
  - `ThermalResult` with devices, losses, temperatures
  - `ConvergenceInfo` with iteration history and problematic nodes

- [x] 1.3 Create settings dataclasses in `services/backend_types.py`
  - `DCSettings` with strategy, tolerances, limiting options
  - `ACSettings` with frequency range and points
  - `ThermalSettings` with ambient temperature and loss options
  - Extend existing `TransientSettings` (was `SimulationSettings`)

- [x] 1.4 Create `BackendVersion` class
  - Parse version strings (e.g., "0.2.1")
  - API version tracking for compatibility
  - `is_compatible_with()` method

- [x] 1.5 ~~Create `BackendRegistry` in `services/backend_registry.py`~~ (Already exists as BackendLoader)
  - Discover backends from installed packages
  - Support entry points for plugins
  - `available_backends()` and `activate()` methods

- [x] 1.6 Add unit tests for abstraction layer
  - Test protocol compliance
  - Test version compatibility
  - Test registry discovery

## 2. DC Operating Point Integration

- [x] 2.1 Add `run_dc()` method to `PulsimBackend`
  - Build pulsim.v1.NewtonOptions from DCSettings
  - Call pulsim.v1.DCConvergenceSolver
  - Convert result to GUI DCResult

- [x] 2.2 Add DC strategy mapping
  - Map DCSettings.strategy to pulsim.v1.DCStrategy enum
  - Handle "auto" strategy selection

- [x] 2.3 Modify `SimulationService.run_dc_operating_point()`
  - Check `backend.has_capability("dc")`
  - Call `backend.run_dc()` instead of placeholder
  - Emit proper signals with real results

- [ ] 2.4 Update `DCResultsDialog` to display real data
  - Show node voltages table
  - Show branch currents table
  - Show convergence info summary

- [ ] 2.5 Add DC tests
  - Test simple resistive circuit
  - Test circuit with diodes
  - Test convergence failure handling

## 3. AC Analysis Integration

- [ ] 3.1 Verify `pulsim.run_ac()` is exposed in bindings
  - Check PulsimCore bindings.cpp
  - If missing, add to PulsimCore first

- [x] 3.2 Add `run_ac()` method to `PulsimBackend`
  - Build AC options from ACSettings
  - Call pulsim.run_ac()
  - Convert to GUI ACResult

- [x] 3.3 Modify `SimulationService.run_ac_analysis()`
  - Check `backend.has_capability("ac")`
  - Call `backend.run_ac()` instead of placeholder
  - Emit ACResult with real Bode data

- [ ] 3.4 Update `BodePlotDialog` with real data
  - Display real magnitude vs frequency
  - Display real phase vs frequency
  - Add gain/phase margin calculations

- [ ] 3.5 Add AC tests
  - Test RC low-pass filter
  - Test LC resonance
  - Test frequency range edge cases

## 4. Thermal Simulation Integration

- [x] 4.1 Add `run_thermal()` method to `PulsimBackend`
  - Create ThermalSimulator from circuit
  - Run thermal analysis with electrical results
  - Extract Foster network and losses

- [ ] 4.2 Modify `ThermalAnalysisService.build_result()`
  - Try real backend first
  - Fall back to synthetic on failure
  - Set `is_synthetic` flag on result

- [x] 4.3 Update thermal result conversion
  - Map backend Foster stages to `FosterStage`
  - Extract conduction and switching losses
  - Build temperature traces

- [ ] 4.4 Update `ThermalViewerDialog` for real data
  - Show "(Synthetic)" badge when using fallback
  - Display real loss breakdown
  - Show Foster network parameters

- [ ] 4.5 Add thermal tests
  - Test with MOSFET circuit
  - Test synthetic fallback path
  - Test loss calculation accuracy

## 5. Solver Options UI

- [x] 5.1 Extend `SimulationSettings` dataclass
  - Add `dc_strategy: str`
  - Add `max_newton_iterations: int`
  - Add `enable_voltage_limiting: bool`
  - Add `max_voltage_step: float`
  - Add `gmin_initial: float`
  - Add `gmin_final: float`

- [x] 5.2 Add Solver tab to `SimulationSettingsDialog`
  - Integration method dropdown (Auto, RK4, RK45, BDF)
  - Newton iterations spinbox
  - Voltage limiting checkbox
  - Max voltage step field
  - Tolerance fields

- [x] 5.3 Add DC Strategy section to Solver tab
  - Strategy dropdown (Auto, Direct, GMIN, Source, Pseudo)
  - GMIN parameters (initial, final) when GMIN selected
  - Description text for each strategy

- [x] 5.4 Wire solver options to backend
  - Pass options through to `PulsimBackend`
  - Build DCSettings from SimulationSettings
  - Map to pulsim.v1.NewtonOptions

- [ ] 5.5 Persist solver settings
  - Save to project file
  - Save to user preferences
  - Restore on dialog open

- [ ] 5.6 Add solver options tests
  - Test UI value changes
  - Test persistence
  - Test backend receives options

## 6. Convergence Diagnostics

- [x] 6.1 Create `ConvergenceDiagnosticsDialog`
  - Summary tab with key metrics
  - Iteration history plot (residual vs iteration)
  - Problematic variables list
  - Suggestions panel

- [ ] 6.2 Add iteration history extraction
  - Extract from pulsim.v2.ConvergenceHistory
  - Convert to GUI IterationRecord list
  - Handle missing history (older backends)

- [ ] 6.3 Add problematic node detection
  - Extract from pulsim.v2.PerVariableConvergence
  - Map indices to node names
  - Sort by worst convergence

- [x] 6.4 Implement suggestion engine
  - "Increase max_iterations" if near limit
  - "Enable voltage limiting" if large steps
  - "Check for floating nodes" if singular matrix
  - "Try GMIN stepping" if DC fails

- [x] 6.5 Integrate with failure paths
  - Show "Diagnostics" button on simulation error
  - Auto-open diagnostics on DC failure (optional)
  - Log diagnostics to output panel

- [x] 6.6 Add diagnostics tests
  - Test dialog with various failure types
  - Test suggestion logic
  - Test with convergence success (no diagnostics)

## 7. Version Compatibility

- [ ] 7.1 Add version detection to `PulsimBackend`
  - Read `pulsim.__version__`
  - Parse to `BackendVersion`
  - Check against MIN_BACKEND_API

- [ ] 7.2 Implement capability detection
  - Check for v2 module presence
  - Check for ThermalSimulator
  - Check for run_ac
  - Update `capabilities` set

- [ ] 7.3 Add version warning UI
  - Show warning banner if version < minimum
  - List unavailable features
  - Link to upgrade instructions

- [ ] 7.4 Implement graceful degradation
  - Disable menu items for unavailable features
  - Show "Upgrade Required" tooltip
  - Fall back to placeholder where possible

- [ ] 7.5 Add backend info to About dialog
  - Show backend name and version
  - Show available capabilities
  - Show installation location

- [ ] 7.6 Add version compatibility tests
  - Mock old backend version
  - Test feature disabling
  - Test warning display

## 8. Integration Testing

- [ ] 8.1 Create integration test suite
  - Test full DC analysis workflow
  - Test full AC analysis workflow
  - Test full transient workflow
  - Test thermal with transient

- [ ] 8.2 Test backend switching
  - Switch from placeholder to pulsim
  - Switch between pulsim versions
  - Verify state preservation

- [ ] 8.3 Test error handling
  - Backend not installed
  - Backend crashes mid-simulation
  - Invalid circuit data
  - Timeout handling

- [ ] 8.4 Performance testing
  - Measure conversion overhead
  - Profile hot paths
  - Compare with direct pulsim usage

## 9. Documentation

- [ ] 9.1 Update developer documentation
  - Document BackendCapabilities protocol
  - Document adding new backends
  - Document version compatibility

- [ ] 9.2 Update user documentation
  - Document solver settings
  - Document DC strategies
  - Document convergence troubleshooting

- [ ] 9.3 Add inline help
  - Tooltips for solver options
  - Help buttons linking to docs
  - Context-sensitive help

## 10. Final Validation

- [ ] 10.1 Run full test suite
  - All unit tests pass
  - All integration tests pass
  - No regressions

- [ ] 10.2 Manual testing checklist
  - DC analysis on resistive circuit
  - DC analysis on MOSFET circuit
  - AC analysis on RC filter
  - Thermal on switching converter
  - Solver options persist correctly
  - Convergence diagnostics show on failure

- [ ] 10.3 Performance validation
  - GUI remains responsive
  - No memory leaks
  - Reasonable startup time

- [ ] 10.4 Demo mode validation
  - GUI works without PulsimCore
  - Placeholder results display
  - Clear indication of demo mode
