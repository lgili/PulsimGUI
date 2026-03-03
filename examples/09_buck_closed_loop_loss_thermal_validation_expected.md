# 09 - Buck Closed-Loop Loss + Thermal Validation (Expected Values)

Use this with `09_buck_closed_loop_loss_thermal_validation.pulsim`.

## Operating Point

- `Vin = 12 V`
- `Vout_ref = 6 V`
- `Rload = 8 ohm`
- `L = 220 uH`
- `Cout = 220 uF`
- `fs = 10 kHz`

## Theoretical Electrical Targets (Ideal Buck, CCM)

1. Duty cycle:

`D_ideal = Vout/Vin = 6/12 = 0.50`

2. Output current:

`Iout = Vout/R = 6/8 = 0.75 A`

3. Output power:

`Pout = Vout * Iout = 4.5 W`

4. Inductor ripple (peak-to-peak):

`DeltaIL = (Vin - Vout) * D / (L * fs)`

`DeltaIL = (12 - 6) * 0.5 / (220e-6 * 10e3) = 1.36 App`

5. Output ripple (capacitor ESR ignored):

`DeltaVout ~= DeltaIL / (8 * fs * C) = 77 mVpp`

## Pass Criteria (GUI)

- `Vout` average (last 20% of transient): `5.7 V` to `6.3 V`
- PWM duty in steady state: `0.45` to `0.55`
- `Vsw` toggling between approximately `0 V` and `12 V`
- `IL` must not diverge and should show triangular ripple around load current

## Loss/Thermal Criteria

- Thermal Viewer must show non-zero losses for `M1` and `D1` when `enable_losses=true`.
- `Tj_M1`, `Tj_D1`, `T_Rload` traces must rise above ambient at startup and settle.
- No over-limit status expected with these limits:
  - `M1 thermal_limit = 150 C`
  - `D1 thermal_limit = 175 C`
  - `Rload thermal_limit = 125 C`

## If backend falls back to synthetic thermal model

Expected approximate values from current GUI synthetic backend:

- `M1 total loss ~ 3.2 W` (2.5 conduction + 0.7 switching)
- `D1 total loss ~ 0.95 W` (0.8 conduction + 0.15 reverse recovery)
- `Tj_M1` rise ~ `+50 C` over ambient
- `Tj_D1` rise ~ `+30 C` over ambient
