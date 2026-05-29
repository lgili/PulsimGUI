# 09 - Buck Closed-Loop Loss + Thermal Validation (Expected Values)

Use this with `09_buck_closed_loop_loss_thermal_validation.pulsim`.

## Operating Point

- `Vin = 12 V`
- `Vout_ref = 6 V`
- `Rload = 8 ohm`
- `L = 220 uH`
- `Cout = 220 uF`
- `fs = 10 kHz`
- `tstop = 20 ms`
- Backend baseline: `pulsim >= 0.7.1`

## Datasheet Baseline Used In This Example

- `M1` (SiC MOSFET reference): ROHM `SCT2080KE`
  - `RDS(on)` typ: `80 mOhm @ 25 C`, `117 mOhm @ 125 C`
  - switching energies (test condition in datasheet): `Eon typ 174 uJ`, `Eoff typ 51 uJ`
  - body-diode reverse recovery: `Qrr typ 44 nC`, `trr typ 31 ns`
  - transient thermal ladder: `Rth=[0.078, 0.197, 0.162] K/W`, `Cth=[0.005, 0.018, 0.249] J/K`
- `D1` (ultrafast diode reference): Diodes Inc. `MUR460`
  - `Vf typ 1.28 V @ 4 A`
  - `trr max 50 ns`
  - thermal: `RthJC typ 8 C/W`, `RthJL typ 11 C/W`, `RthJA typ 30 C/W`
- `Rload` (power resistor reference style): TT Electronics `WH25` family
  - temperature coefficient used in model: `50 ppm/C` (`alpha=5e-5`)

Notes:
- `M1` uses `switching_loss_model=datasheet` with a 2x2x2 (`I`,`V`,`T`) surface built around the datasheet operating point.
- The additional surface points away from the nominal datasheet test point were inferred by proportional scaling (documented approximation for simulation robustness).
- `D1` reverse-recovery energy is represented with scalar `switching_err_j` for converter-loss accounting.

Source links:
- ROHM SCT2080KE datasheet mirror (switching and body-diode values): https://www.digikey.com/htmldatasheets/production/1272689/0/0/1/sct2080ke.html
- ROHM SCT2080KE thermal ladder values (`Rth1..3`, `Cth1..3`): https://manuals.plus/m/f14e13e18a31f2ee32518875e28e77b4408c4210b367e236460e42313f11d6e6
- Diodes Inc. MUR460 product + datasheet entry (`Vf`, `trr`, thermal limits): https://www.diodes.com/part/view/MUR460/
- TT Electronics WH25 family specs (`TCR 50ppm/C`): https://www.ttelectronics.com/products/passive-components/resistors/wh25/

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
- PWM duty in steady state: `0.60` to `0.64` (non-ideal switch/diode losses)
- `Vsw` toggling between approximately `0 V` and `12 V`
- `IL` must not diverge and should show triangular ripple around load current

## Loss/Thermal Criteria

- Thermal Viewer must show non-zero losses for `M1`, `D1`, and `Rload` when `enable_losses=true`.
- `Tj_M1`, `Tj_D1`, `T_Rload` traces must rise above ambient at startup and settle.
- No over-limit status expected with these limits:
  - `M1 thermal_limit = 150 C`
  - `D1 thermal_limit = 175 C`
  - `Rload thermal_limit = 125 C`
- With the shipped example parameters and `tstop = 20 ms`, expected ranges:
  - `total_loss`: `6.2 W` to `6.7 W`
  - `M1 total loss`: `1.9 W` to `2.3 W` (conduction + switching)
  - `D1 total loss`: `0.13 W` to `0.23 W` (conduction + reverse recovery)
  - `Rload total loss`: `4.0 W` to `4.3 W` (mainly conduction)
  - `T(M1)` final: `25.60 C` to `25.75 C`
  - `T(D1)` final: `25.01 C` to `25.04 C`
  - `T(Rload)` final: `25.22 C` to `25.34 C`
