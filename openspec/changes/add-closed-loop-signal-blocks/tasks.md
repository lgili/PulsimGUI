# Tasks: add-closed-loop-signal-blocks

## Phase 1 – GUI: Constant Block

- [ ] **T1.1** Add `CONSTANT = auto()` to `ComponentType` enum in
  `src/pulsimgui/models/component.py`
- [ ] **T1.2** Add `CONSTANT` pin layout to `COMPONENT_PIN_LAYOUT`: one output
  pin `OUT` at `(+30, 0)`
- [ ] **T1.3** Add default params `{"value": 0.0}` for `CONSTANT` in
  `DEFAULT_COMPONENT_PARAMS`
- [ ] **T1.4** Add `CONSTANT` to `SIGNAL_DOMAIN_COMPONENTS` set
- [ ] **T1.5** Add `CONSTANT` entry in `component_catalog.py` under
  "Signal & Control" with shortcut `Ctrl+K`
- [ ] **T1.6** Add `CONSTANT` to `QUICK_ADD_COMPONENTS` with keywords
  `["const", "constant", "ref", "reference", "value"]`
- [ ] **T1.7** Add rendering support for `CONSTANT` in
  `src/pulsimgui/views/schematic/items/component_item.py` – draw a rectangle
  with the numeric `value` centered inside (similar to Gain triangle rendering)
- [ ] **T1.8** Add `CONSTANT` to properties panel: show `value` field as
  `FloatParameterEditor`

## Phase 2 – GUI: Limiter in Catalog + PWM duty-cycle pin

- [ ] **T2.1** Add `LIMITER` entry to `component_catalog.py` under
  "Signal & Control" (already in enum; just missing from catalog)
- [ ] **T2.2** Verify `LIMITER` default params include `lower` and `upper`; add
  to `DEFAULT_COMPONENT_PARAMS` if missing
- [ ] **T2.3** Add `DUTY_IN` signal input pin to `PWM_GENERATOR` pin layout at
  `(-35, 20)` so it visually separates from the existing CLK-style pins
- [ ] **T2.4** Ensure `DUTY_IN` pin is listed as a signal-domain input pin so
  connection rules allow wiring from math block outputs

## Phase 3 – Backend: Signal-Flow Evaluator (PulsimCore Python layer)

- [ ] **T3.1** Create `python/pulsim/signal_evaluator.py` with:
  - `build_signal_graph(components, wires) -> dict` – builds adjacency list of
    signal-domain blocks from netlist
  - `topological_sort(graph) -> list[str]` – Kahn's algorithm; raises
    `AlgebraicLoopError` if cycle is detected
  - `evaluate_signal_block(block, inputs, state, t, dt) -> float` – dispatches
    per block type
- [ ] **T3.2** In `evaluate_signal_block`, implement handlers for:
  - `CONSTANT`: return `params["value"]`
  - `VOLTAGE_PROBE` / `CURRENT_PROBE`: return measurement from electrical solver
    snapshot (already available in backend adapter step)
  - `GAIN`: return `params["k"] * input[0]`
  - `SUM`: return `sum(inputs)`
  - `SUBTRACTOR`: return `inputs[0] - inputs[1]`
  - `LIMITER`: return `clamp(input[0], params["lower"], params["upper"])`
  - `PI_CONTROLLER`: call `PIController.update(ref, feedback, t)` using C++
    binding; return output
  - `PWM_GENERATOR`: if `DUTY_IN` wire connected, override `duty_cycle` with
    signal value before generating gate pulse
- [ ] **T3.3** Wire `signal_evaluator` into the simulation step loop in the
  backend adapter so it runs **after** the electrical solver snap but **before**
  gate signals are applied to switches
- [ ] **T3.4** Propagate `AlgebraicLoopError` to the GUI as a simulation error
  with a human-readable message listing the cycle members

## Phase 4 – Backend: PI + Limiter C++ binding exposure

- [ ] **T4.1** Verify `PIController` pybind11 binding is already exported in
  `python/bindings/`; expose `update(ref, fb, t)` and `reset()` if not yet done
- [ ] **T4.2** Add a lightweight `Limiter` free-function binding:
  `pulsim.clamp(value, lower, upper) -> float` (or simply use Python's built-in
  `min/max` – acceptable if C++ binding is not needed for perf)

## Phase 5 – Tests

- [ ] **T5.1** Unit test `signal_evaluator.topological_sort` with:
  - linear chain (no cycle) → correct order
  - two-node cycle → raises `AlgebraicLoopError`
- [ ] **T5.2** Unit test each block handler in `evaluate_signal_block`
- [ ] **T5.3** Integration test: load `buck_converter_closed_loop.pulsim`, run
  1 ms simulation, assert output voltage converges toward reference
- [ ] **T5.4** Regression test: load `07_rc_backend_smoke.pulsim` (no signal
  blocks), assert simulation still passes (backwards compat)

## Phase 6 – Documentation

- [ ] **T6.1** Update `docs/user-manual.md` – add "Signal & Control Blocks"
  section describing each block, its parameters, and a wiring example
- [ ] **T6.2** Update `examples/README.md` – add `buck_converter_closed_loop`
  example walkthrough screenshot/description
