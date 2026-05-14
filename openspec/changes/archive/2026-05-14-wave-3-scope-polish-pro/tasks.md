## 1. Branding

- [x] 1.1 Replace "VirtuScope" → "Scope" in the top-left brand label.
- [x] 1.2 Replace "SimuScope v1.0" → "Scope · PulsimGui &lt;v&gt;" using
      `pulsimgui.__version__`.
- [x] 1.3 Window title goes from "&lt;name&gt; — VirtuScope" to
      "&lt;name&gt; — PulsimGui Scope".

## 2. Stat dedup

- [x] 2.1 Remove the bottom "chip strip" (RMS / Peak / Mean / Δt / ΔY).
- [x] 2.2 Status bar shows only readiness phrase + sample rate.
      Δt / ΔY stay in the cursor panel.

## 3. Toolbar grouping

- [x] 3.1 Wrap the 14 toolbar buttons into four `QFrame`-style
      groups with a 1 px vertical separator between them.
- [x] 3.2 Tooltips on every button include the keyboard shortcut.

## 4. Sidebar rail labels

- [x] 4.1 Add a 9 pt label below each sidebar-rail glyph.
- [x] 4.2 Bump rail width 36 → 48 px so the labels render cleanly.

## 5. Empty state

- [x] 5.1 New `_EmptyStateCard` widget centred in the plot area when
      `len(self._stacked_signals) == 0`.
- [x] 5.2 Card has three action buttons + a one-paragraph helper.

## 6. Tests

- [x] 6.1 Update `tests/test_views/test_scope_window_*` to check
      the new brand strings + group structure.
- [x] 6.2 Run full suite; document any pre-existing flakes.

## 7. Release

- [x] 7.1 Bump PulsimGui `0.9.0 → 0.9.1`.
- [x] 7.2 Tag v0.9.1, push, monitor.
