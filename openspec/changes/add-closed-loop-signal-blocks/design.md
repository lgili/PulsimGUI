# Design: add-closed-loop-signal-blocks

## Signal-Domain Data Model

In Pulsim, every component belongs to one of two domains:
- **Electrical domain** – components with voltages/currents solved by MNA (resistors,
  capacitors, MOSFETs, etc.)
- **Signal domain** – components that process scalar floating-point values through
  a discrete event/step evaluation (Constant, Gain, Sum, PI, PWM, Probes, etc.)

A **signal wire** connects an output pin of one signal-domain block to an input
pin of another. The schematic editor already enforces that signal wires cannot
cross into the electrical domain (`SIGNAL_DOMAIN_COMPONENTS` set in `component.py`).

## Constant Block

```
┌───────┐
│  1.0  ├──► OUT
└───────┘
```

- Single parameter: `value: float` (default `0.0`)
- No input pins, one output pin `OUT`
- Backend: trivially returns `params["value"]` every step
- GUI rendering: square/rectangle with value centered, configurable from Properties

## Signal-Flow Evaluation Order

Signal blocks form a **Directed Acyclic Graph (DAG)**. Before the first simulation
step, the backend adapter builds the graph and computes a topological order using
Kahn's algorithm. This order is cached and reused every step (topology doesn't
change during a run).

```
Evaluation order example (buck closed-loop):
  1. Constant (Vref)           → no inputs
  2. VOLTAGE_PROBE             → reads electrical snapshot
  3. GAIN (×feedback_scale)    → reads VOLTAGE_PROBE.OUT
  4. SUBTRACTOR (error)        → reads Constant.OUT, GAIN.OUT
  5. LIMITER (error clamp)     → reads SUBTRACTOR.OUT
  6. PI_CONTROLLER             → reads LIMITER.OUT (error)
  7. PWM_GENERATOR             → reads PI.OUT (duty)
```

**Algebraic loop detection**: if `topological_sort` finds a remaining non-empty
set after Kahn drains (in-degree > 0 remains), a cycle exists. The error message
lists all component IDs in the cycle so the user can fix the schematic.

## PWM Duty-Cycle Input Pin

`PWM_GENERATOR` gains an **optional** signal input pin `DUTY_IN`:
- If connected → duty cycle is overridden by the incoming signal value each step;
  the static `duty_cycle` parameter is ignored during that step
- If unconnected → behavior is identical to current implementation (backwards compat)

Pin position: `(-35, 20)` — below the existing `FREQ` label area so it does not
overlap with the carrier/clock port.

## Limiter Block

```
          ┌──────────┐
 IN ──►   │ clamp    │ ──► OUT
          │ [lo, hi] │
          └──────────┘
```

- Parameters: `lower: float` (default `-1e9`), `upper: float` (default `1e9`)
- Single input `IN`, single output `OUT`
- Backend: `out = max(lower, min(upper, in))`
- Note: already defined in `ComponentType.LIMITER` and has pin layout; only the
  catalog entry and backend handler are missing.

## PI Controller Signal Wiring

Current: `PI_CONTROLLER` accepts `REF` and `FB` signal pins (already in pin layout).
The `REF` pin is typically fed by a `Constant` (reference), and `FB` by a probe
(measurement), possibly through a `Gain` or `Limiter`.

Internally the PI uses `PIController::update(ref, fb, t)` from `control.hpp`
(already exposed in C++). The Python adapter calls the binding each step.

## Probe → Signal Chain Integration

`VOLTAGE_PROBE` and `CURRENT_PROBE` already have an `OUT`/`MEAS` signal pin. The
signal evaluator reads the probe's most recent `measurement` value (set by the
electrical solver) and treats it as a signal source. Probes have no upstream
signal dependencies, so they appear at the head of the topological order.

## File Format Backwards Compatibility

Existing `.pulsim` files that use `PWM_GENERATOR` without a `DUTY_IN` connection
will load correctly because:
1. The pin is added to the layout but is **optional** – unconnected pins are normal.
2. The backend checks `if "DUTY_IN" in connected_signal_wires` before overriding
   the duty parameter.

No migration needed.

## New Files

| File | Purpose |
|------|---------|
| `python/pulsim/signal_evaluator.py` (PulsimCore) | Signal graph build + topo sort + per-block evaluation |
| `python/tests/test_signal_evaluator.py` (PulsimCore) | Unit + integration tests |

## Modified Files

### PulsimGui
| File | Change |
|------|--------|
| `src/pulsimgui/models/component.py` | Add `CONSTANT`, `LIMITER` catalog, `DUTY_IN` pin on PWM |
| `src/pulsimgui/models/component_catalog.py` | Add `CONSTANT`, `LIMITER` entries |
| `src/pulsimgui/views/schematic/items/component_item.py` | Render `CONSTANT` block |
| `src/pulsimgui/views/properties/properties_panel.py` | `value` for Constant, `lower/upper` for Limiter |

### PulsimCore
| File | Change |
|------|--------|
| `python/pulsim/signal_evaluator.py` | **NEW** |
| `python/pulsim/backend_adapter.py` (or equivalent) | Call evaluator in step loop |
| `python/tests/test_signal_evaluator.py` | **NEW** |
