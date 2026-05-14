## ADDED Requirements

### Requirement: THD readout in FFT analysis
The FFT analysis tab SHALL surface a Total Harmonic Distortion readout when the user supplies a fundamental frequency.

#### Scenario: User sets fundamental and sees THD
- **GIVEN** the FFT tab shows the spectrum of a captured signal
- **WHEN** the user enters a fundamental frequency in the new spinner (or clicks "snap to peak")
- **THEN** the panel SHALL compute `THD% = 100 · √Σ(A_k²) / A_1` over harmonics k=2..N and render `THD = X.XX %` adjacent to the spectrum

#### Scenario: Snap-to-peak helper
- **GIVEN** the FFT spectrum is rendered
- **WHEN** the user clicks the "snap to peak" button
- **THEN** the fundamental-frequency field SHALL update to the frequency of the largest in-band magnitude bin (excluding DC)

### Requirement: Power and Energy measurement columns
The bottom-drawer measurement table SHALL expose `THD%`, `P_avg`, and `Energy` as optional columns selectable through the "+ Add Measurement" dialog.

#### Scenario: Add THD column for a paired V signal
- **GIVEN** the measurement table is visible
- **WHEN** the user opens the "+ Add Measurement" dialog and ticks "THD%"
- **THEN** the table SHALL add a `THD%` column with values computed using the per-signal fundamental frequency stored alongside the FFT state

#### Scenario: Power column requires a current pair
- **GIVEN** the user adds a `P_avg` column to a voltage signal that has not been paired with a current
- **THEN** the cell SHALL render `—` rather than emitting a synthetic value

### Requirement: Math-signal power and energy helpers
The math-signal expression evaluator SHALL accept `power(va, vb, i)` and `energy(va, vb, i)` as new helper functions in addition to the existing `abs/sqrt/square/derivative/integral/moving_avg`.

#### Scenario: User writes a power-trace expression
- **GIVEN** the user opens "Add Math Signal" with `Va`, `Vb`, `Iload` available
- **WHEN** the formula is `power(Va, Vb, Iload)`
- **THEN** the dialog SHALL evaluate to `(Va − Vb) * Iload` element-wise and produce the new derived signal
