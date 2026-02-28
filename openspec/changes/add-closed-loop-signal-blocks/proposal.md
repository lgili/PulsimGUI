# Proposal: add-closed-loop-signal-blocks

## Status
DRAFT

## Summary
Add and complete the signal/control math block chain needed for closed-loop power
electronics simulations. This includes: a new **Constant** source block, a fully
wired **Gain** block, **Sum/Subtractor** multi-input support, a **Limiter** block,
and end-to-end signal routing from measurement probes through the math chain →
PI controller → PWM duty-cycle input → gate signal.

## Motivation
Closed-loop converters (buck, boost, inverter) require a complete control path:

```
[Ref Constant] ──────────────────────────────────┐
                                                  ▼
[V/I Probe] ──► [Gain] ──► [Sum/Sub] ──► [Limiter] ──► [PI] ──► [PWM(duty)] ──► [Switch Gate]
```

Currently:
- `CONSTANT` block does **not exist** in `ComponentType`, the catalog, pin layout,
  or backend; there is no way to inject a fixed numeric reference value into the
  signal network.
- `GAIN` accepts an electrical probe output pin but cannot yet accept a signal
  from a math block (Sum, Sub, another Gain) as its input.
- `SUM` / `SUBTRACTOR` have GUI pin definitions but their backend simulation
  handler does not propagate multiple signal-domain inputs properly.
- `LIMITER` is defined in `ComponentType` and has pin layout but has no backend
  simulation step implementation in PulsimCore's Python layer.
- `PWM_GENERATOR` has no signal-input pin for external duty-cycle; duty is set
  only through a static parameter today.
- The PulsimCore simulation adapter (`backend_adapter`) does not build a
  signal-flow evaluation order, so math blocks downstream of a probe are never
  evaluated in the correct step sequence.

## Scope

### PulsimGui (frontend)

| Area | Change |
|------|--------|
| `component.py` – `ComponentType` | Add `CONSTANT = auto()` |
| `component.py` – pin layout | Add pins for `CONSTANT`: one output (`OUT`) |
| `component.py` – default params | `value: 0.0` for `CONSTANT` |
| `component_catalog.py` | Add `CONSTANT` to "Signal & Control" group |
| `component_catalog.py` | Add `LIMITER` to "Signal & Control" group (already in enum, missing from catalog) |
| Schematic renderer | Render `CONSTANT` as a block with the value text inside |
| Properties panel | Allow editing `value` for `CONSTANT`; `lower` / `upper` for `LIMITER` |
| `component.py` – `SIGNAL_DOMAIN_COMPONENTS` | `CONSTANT` is signal-domain |
| `component.py` – `PWM_GENERATOR` pins | Add `DUTY_IN` signal input pin (optional, overrides param when connected) |

### PulsimCore (backend – Python simulation layer)

| Area | Change |
|------|--------|
| Signal block evaluator | Implement topological sort of signal-flow graph before each simulation step |
| `CONSTANT` handler | Output `params["value"]` every step |
| `GAIN` handler | Source value from connected signal wire OR probe output |
| `SUM` handler | Sum all connected `IN_n` signal inputs |
| `SUBTRACTOR` handler | `IN_0 - IN_1` from signal wires |
| `LIMITER` handler | `clamp(IN, lower, upper)` |
| `PI_CONTROLLER` handler | Read `REF` and `FB` from signal wires; write `OUT` |
| `PWM_GENERATOR` handler | If `DUTY_IN` wire present, use its value instead of `duty_cycle` param |

### PulsimCore (backend – C++ `control.hpp`)

No new headers required; `PIController` class already implements PI with
anti-windup and output clamp. `Limiter` is trivial (`std::clamp`); will be
inlined in the Python adapter step.

## Out of Scope
- PID derivative block (separate change)
- Rate limiter backend (already has GUI; backend deferred)
- Bode plot / frequency-domain analysis of closed loop
- Auto-tuning of PI gains

## Risks
- **Signal evaluation order**: cycles in the signal graph (algebraic loops) must
  be detected and rejected with a clear error message.
- **Mixed-domain wires**: a signal wire must never connect to an electrical pin.
  Existing rule in `component.py` covers this; Constant/Limiter must be listed in
  `SIGNAL_DOMAIN_COMPONENTS`.
- **PWM `DUTY_IN` pin is optional**: if unconnected, duty-cycle falls back to the
  static `duty_cycle` parameter to maintain backwards compatibility with existing
  `.pulsim` files.

## Acceptance Criteria
1. User can place a `Constant` block, set its value, and wire it to a `Sum` input.
2. User can wire `V Probe OUT` → `Gain IN` → `Subtractor IN_1`; `Constant OUT` →
   `Subtractor IN_0`; `Subtractor OUT` → `PI REF`; `PI OUT` → `PWM DUTY_IN`;
   `PWM OUT` → MOSFET gate. Simulation runs and produces closed-loop waveform.
3. `Limiter` clamps a signal and its output can feed the PI or PWM.
4. Algebraic loop is detected at simulation start and shown as a user-visible error.
5. All existing `.pulsim` example files continue to load and simulate correctly
   (backwards compat for `PWM_GENERATOR` without `DUTY_IN` connected).
