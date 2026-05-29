## 1. Scope — THD, Power, Energy

- [x] 1.1 New helper module `views/scope/measurements.py` with pure
      functions `compute_thd(samples, sample_rate, fundamental_hz, n)`
      / `compute_power(va, vb, i, dt)` / `compute_energy(power, dt)`.
      Unit tests in `tests/test_scope/test_measurements.py`.
- [x] 1.2 FFT page: add a fundamental-frequency spinner + "snap to
      peak" button + THD readout label (`THD = X.XX %`).
- [x] 1.3 Bottom-drawer measurement table: add `THD%`, `P_avg`,
      `Energy` as optional columns; surface in the "+ Add
      Measurement" dialog.
- [x] 1.4 Math-signal dialog: add `power(va, vb, i)` and
      `energy(va, vb, i)` to the supported-functions list and the
      evaluator.

## 2. Welcome surface

- [x] 2.1 New `views/widgets/welcome_overlay.py` with four
      action cards.
- [x] 2.2 `main_window` wires the overlay to show whenever the
      active circuit has zero components, and hides it when
      components are added.
- [x] 2.3 Templates card opens a modal that lists the 15 gallery
      topologies + 9 numbered tutorial examples with one-line
      descriptions; selecting one copies the project to memory
      so the user can save-as without overwriting the original.

## 3. Schematic export

- [x] 3.1 New `File → Export → Schematic Image…` action.
- [x] 3.2 Modal dialog with format / resolution / background /
      margin options.
- [x] 3.3 Renders the current circuit to QImage / QSvgGenerator
      respecting the chosen options.
- [x] 3.4 New `Edit → Copy Schematic as Image` action (`⌘⇧C`)
      writes the same render to `QApplication.clipboard()`.

## 4. Run Bar real progress

- [x] 4.1 Add `progress` Signal emission to the transient inner
      loop based on `len(time_array) / expected_steps` whenever
      the backend doesn't already publish progress, throttled to
      10 Hz.
- [x] 4.2 Set `t_total` on the Run Bar when starting a run so the
      progress bar normalises against the right denominator.

## 5. Tests + docs

- [x] 5.1 Unit tests for `views/scope/measurements.py`
      (compute_thd against an analytical square / triangle wave;
      compute_power on a constant DC).
- [x] 5.2 Smoke test that opens the welcome overlay, clicks a
      template, and confirms a new project is loaded.
- [x] 5.3 Smoke test that exports a known circuit to PNG, asserts
      the PNG is non-empty and the right size.
- [x] 5.4 Update `docs/user-manual.md` (Run Simulation, Analyze
      Waveforms sections) + `docs/examples-gallery.md` (welcome
      surface mention).

## 6. Release

- [x] 6.1 Bump PulsimGui `0.8.4 → 0.9.0` (wave bumps minor).
- [x] 6.2 Tag, push, monitor; verify GitHub Release artifacts.
