# Tasks: add-closed-loop-signal-blocks

## Phase 1 – GUI: Constant Block

- [x] **T1.1** Add `CONSTANT = auto()` to `ComponentType` enum in
  `src/pulsimgui/models/component.py`
- [x] **T1.2** Add `CONSTANT` pin layout to `COMPONENT_PIN_LAYOUT`: one output
  pin `OUT` at `(+30, 0)`
- [x] **T1.3** Add default params `{"value": 0.0}` for `CONSTANT` in
  `DEFAULT_COMPONENT_PARAMS`
- [x] **T1.4** Add `CONSTANT` to `SIGNAL_DOMAIN_COMPONENTS` set
- [x] **T1.5** Add `CONSTANT` entry in `component_catalog.py` under
  "Signal & Control" with shortcut `Ctrl+K`
- [x] **T1.6** Add `CONSTANT` to `QUICK_ADD_COMPONENTS` with keywords
  `["const", "constant", "ref", "reference", "value"]`
- [x] **T1.7** Add rendering support for `CONSTANT` in
  `src/pulsimgui/views/schematic/items/component_item.py` – deep-purple block
  with numeric `value` centered inside (`ConstantItem`)
- [ ] **T1.8** Add `CONSTANT` to properties panel: show `value` field as
  `FloatParameterEditor`

## Phase 2 – GUI: Limiter in Catalog + PWM duty-cycle pin

- [x] **T2.1** Add `LIMITER` entry to `component_catalog.py` under
  "Signal & Control" (already in enum; just missing from catalog)
- [x] **T2.2** Verify `LIMITER` default params include `lower_limit` and
  `upper_limit` in `DEFAULT_PARAMETERS` ✓ (`-1.0` / `1.0`)
- [x] **T2.3** Add `DUTY_IN` signal input pin to `PWM_GENERATOR` pin layout at
  `(-35, 20)` so it visually separates from the existing CLK-style pins
- [x] **T2.4** Ensure `DUTY_IN` pin is listed as a signal-domain input pin so
  connection rules allow wiring from math block outputs

## Phase 3 – Backend: Signal-Flow Evaluator (PulsimGui Python layer)

- [x] **T3.1** Create `src/pulsimgui/services/signal_evaluator.py` with:
  - `SignalEvaluator.build()` – builds adjacency list of signal-domain blocks
    from `circuit_data`, Kahn's topo sort, raises `AlgebraicLoopError` on cycle
  - `SignalEvaluator.step(t)` – evaluates all blocks in topo order; returns
    `{comp_id: value}` dict
- [x] **T3.2** In `step()`, handlers implemented for:
  - `CONSTANT`, `VOLTAGE_PROBE`/`CURRENT_PROBE`, `GAIN`, `SUM`, `SUBTRACTOR`,
    `LIMITER`, `RATE_LIMITER`, `INTEGRATOR`, `PI_CONTROLLER`, `PID_CONTROLLER`,
    `HYSTERESIS`, `SAMPLE_HOLD`, `SIGNAL_MUX/DEMUX`, `PWM_GENERATOR`
- [x] **T3.3** Added signal blocks to `_INSTRUMENTATION_COMPONENTS` in
  `circuit_converter.py` (skipped from C++ netlist); integrated
  `_attach_signal_evaluator()` in `PulsimBackend.run_transient()` which calls
  `circuit.set_pwm_duty_callback()` per PWM with DUTY_IN connected
- [x] **T3.4** `AlgebraicLoopError` propagates to GUI via `result.error_message`
  with human-readable cycle member list

## Phase 4 – Backend: PI + Limiter C++ binding exposure

- [x] **T4.1** `PIController` pybind11 binding already exported; Python fallback
  implemented for environments without the binding
- [ ] **T4.2** Add a lightweight `Limiter` free-function binding:
  `pulsim.clamp(value, lower, upper) -> float` (or simply use Python's built-in
  `min/max` – acceptable if C++ binding is not needed for perf)

## Phase 5 – Tests

- [x] **T5.1** Unit test topo-sort: linear chain → correct order; two-node cycle
  → raises `AlgebraicLoopError`
- [x] **T5.2** Unit test each block handler: CONSTANT, GAIN, LIMITER,
  SUBTRACTOR, SUM, PI (Python fallback), probe feedback update, PWM DUTY chain
  (22 tests in `tests/test_services/test_signal_evaluator.py`, all green)
- [ ] **T5.3** Integration test: load `buck_converter_closed_loop.pulsim`, run
  1 ms simulation, assert output voltage converges toward reference
- [ ] **T5.4** Regression test: load `07_rc_backend_smoke.pulsim` (no signal
  blocks), assert simulation still passes (backwards compat)

## Phase 6 – Documentation

- [ ] **T6.1** Update `docs/user-manual.md` – add "Signal & Control Blocks"
  section describing each block, its parameters, and a wiring example
- [ ] **T6.2** Update `examples/README.md` – add `buck_converter_closed_loop`
  example walkthrough screenshot/description
