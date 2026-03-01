# Buck Converter Example

This tutorial validates the simulation workflow for a buck topology using the built-in project template.

## Objective

- Open the buck template.
- Adjust basic input/switching/load parameters.
- Run a transient simulation.
- Read `Vsw`, `Vout`, and inductor current.

## Steps

1. Open `File → New from Template`.
2. Select **Buck Converter**.
3. Verify core blocks:
   - Input source (`Vin`)
   - Switching element (MOSFET)
   - Freewheel diode
   - Inductor (`L1`)
   - Output capacitor (`Cout`)
   - Load (`Rload`)
4. Open `Simulation Settings` and start with:
   - `Stop time`: `10ms`
   - `Step size`: `2us`
   - `Output points`: `5000` to `10000`
   - Transient robustness enabled
5. Run with **Run** (`F5`).
6. In viewer/scope, inspect:
   - `V(SW)`
   - `V(VOUT)`
   - `I(L1)`

## What to Analyze

- **SW node**: high-frequency pulsed waveform.
- **VOUT**: stabilized average level with ripple.
- **I(L1)**: triangular ramp (continuous or discontinuous mode depending on load/inductance).

## Useful Adjustments

- High `VOUT` ripple: increase `Cout` and/or switching frequency.
- Excessive inductor ripple current: increase `L1`.
- Poor convergence: reduce `Step size`, keep robustness enabled, and review extreme parameters.

## Internal References

- Project examples: [`examples/`](https://github.com/lgili/PulsimGUI/tree/main/examples)
- Detailed solver setup: [Simulation Configuration](../gui/configuracao-simulacao.md)
