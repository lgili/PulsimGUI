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

- [x] 2.4 Update `DCResultsDialog` to display real data
  - Show node voltages table
  - Show branch currents table
  - Show convergence info summary

- [x] 2.5 Add DC tests
  - Test simple resistive circuit
  - Test circuit with diodes
  - Test convergence failure handling

## 3. AC Analysis Integration

- [x] 3.1 Verify `pulsim.run_ac()` is exposed in bindings
  - **RESULT**: PulsimCore has AC analysis C++ code (ACAnalyzer in ac_analysis.hpp/cpp)
  - ACOptions, ACResult, BodeData, FrequencySweepType are now exposed in Python bindings
  - extract_bode_data() and calculate_stability_margins() functions exposed
  - **RESOLVED**: Added `devices()` and `connections()` accessors to v1::Circuit
  - Added `convert_to_ir_circuit()` function in bindings.cpp to convert v1::Circuit to pulsim::Circuit
  - `run_ac()` function now takes v1::Circuit and converts internally
  - AC analysis verified working with RC low-pass filter showing correct -3dB at cutoff

- [x] 3.2 Add `run_ac()` method to `PulsimBackend`
  - Build AC options from ACSettings
  - Call pulsim.run_ac()
  - Convert to GUI ACResult

- [x] 3.3 Modify `SimulationService.run_ac_analysis()`
  - Check `backend.has_capability("ac")`
  - Call `backend.run_ac()` instead of placeholder
  - Emit ACResult with real Bode data

- [x] 3.4 Update `BodePlotDialog` with real data
  - Display real magnitude vs frequency
  - Display real phase vs frequency
  - Add gain/phase margin calculations (Stability Margins tab added)

- [x] 3.5 Add AC tests (21 tests in test_ac_analysis.py)
  - Test RC low-pass filter (passband, rolloff, cutoff, phase)
  - Test frequency range edge cases (narrow, wide, single point, very low/high)
  - Test stability margin calculations

## 4. Thermal Simulation Integration

- [x] 4.1 Add `run_thermal()` method to `PulsimBackend`
  - Create ThermalSimulator from circuit
  - Run thermal analysis with electrical results
  - Extract Foster network and losses

- [x] 4.2 Modify `ThermalAnalysisService.build_result()`
  - Try real backend first via `_try_backend_thermal()`
  - Fall back to synthetic via `_build_synthetic_result()`
  - Set `is_synthetic` flag on result
  - Added `backend` property to ThermalAnalysisService
  - MainWindow passes backend to ThermalAnalysisService

- [x] 4.3 Update thermal result conversion
  - Map backend Foster stages to `FosterStage`
  - Extract conduction and switching losses
  - Build temperature traces

- [x] 4.4 Update `ThermalViewerDialog` for real data
  - Show "(Synthetic Data)" badge when using fallback
  - Window title shows "(Synthetic)" suffix
  - Display real loss breakdown
  - Show Foster network parameters

- [x] 4.5 Add thermal tests (16 tests in test_thermal_service.py)
  - Test synthetic thermal data generation
  - Test backend integration with mock backend
  - Test fallback to synthetic on error/exception
  - Test ThermalResult and ThermalDeviceResult dataclasses

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

- [x] 5.5 Persist solver settings
  - Save to project file
  - Save to user preferences
  - Restore on dialog open

- [x] 5.6 Add solver options tests (21 tests in test_solver_options.py)
  - Test UI value changes (dialog loads/saves settings correctly)
  - Test persistence (settings survive dialog roundtrip)
  - Test backend receives options (DCSettings built from SimulationSettings)

## 6. Convergence Diagnostics

- [x] 6.1 Create `ConvergenceDiagnosticsDialog`
  - Summary tab with key metrics
  - Iteration history plot (residual vs iteration)
  - Problematic variables list
  - Suggestions panel

- [x] 6.2 Add iteration history extraction
  - Extract from pulsim.v2.ConvergenceHistory (with attribute fallbacks)
  - Convert to GUI IterationRecord list with all fields
  - Handle missing history (returns empty list for older backends)

- [x] 6.3 Add problematic node detection
  - Extract from pulsim.v2.PerVariableConvergence (with attribute fallbacks)
  - Map indices to node names using circuit.node_names()
  - Sort by worst convergence (by normalized_error, descending)

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

- [x] 7.1 Add version detection to `PulsimBackend`
  - Read `pulsim.__version__` and parse to `BackendVersion`
  - Check against MIN_BACKEND_API (0.2.0)
  - Store parsed_version and is_compatible in BackendInfo

- [x] 7.2 Implement capability detection
  - Check for dc_operating_point, v2.solve_dc, v1.DCConvergenceSolver
  - Check for run_ac, ACAnalysis
  - Check for ThermalSimulator
  - Update capabilities set and unavailable_features list

- [x] 7.3 Add version warning UI
  - SimulationSettingsDialog shows compatibility_warning
  - Shows unavailable features in capabilities list
  - Warning label visible when issues detected

- [x] 7.4 Implement graceful degradation
  - Menu items disabled for unavailable capabilities
  - Tooltips show "requires backend upgrade" for disabled items
  - Thermal viewer uses synthetic fallback with tooltip hint

- [x] 7.5 Add backend info to About dialog
  - Shows backend name, version, location
  - Shows available capabilities
  - Shows unavailable features (highlighted)
  - Shows compatibility warning if present

- [x] 7.6 Add version compatibility tests (18 tests in test_version_compatibility.py)
  - BackendVersion parsing and comparison
  - BackendInfo compatibility checking
  - MIN_BACKEND_API validation

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
