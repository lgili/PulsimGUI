## 1. P0 — Regression fixes

- [x] 1.1 `shortcut_format` helper + adoption in palette cards.
- [x] 1.2 Status bar version segment reads `pulsim.__version__`
      *(already correct in code; "0.5.1" the audit saw was a stale
      local install — see commit message for v0.8.1).*
- [x] 1.3 `_open_project_file` ends with auto-fit (`zoom_to_fit`
      called on the next event-loop tick).
- [x] 1.4 Toolbar rotate icons switched from the `arrow-clockwise`
      glyph family (visually indistinguishable from undo/redo) to
      `arrows-clockwise` (object-rotation glyphs).
- [x] 1.5 Component card label truncation + tooltip fallback.

## 2. P1 — Information architecture (this release)

- [x] 2.1 Solver pill widget + status-bar adoption + click-to-open
      settings + health-state on `simulation_finished`.
- [x] 2.5 Run Bar widget (Run / Pause / Stop + progress + realtime
      factor) wired to `SimulationService` signals.

## 3. Deferred to wave 2

- [ ] 3.1 Dirty / stale / unsaved indicator triple wired into
      schematic items + scope window + title bar.
- [ ] 3.2 Empty-state action cards (Blank / Quick-add / Templates /
      Recent files).
- [ ] 3.3 Inline diagnostics layer (badges on components with
      validation errors).
- [ ] 3.4 Net highlighting on hover.
- [ ] 3.5 Wire-label collision avoidance.
- [ ] 3.6 Unified titlebar + breadcrumb + view-switcher.
- [ ] 3.7 Project tab in left rail.
- [ ] 3.8 Generalized command palette (`>`, `:`, `@`, `#`, `?` modes).
- [ ] 3.9 Console panel (Output / Problems / Telemetry).
- [ ] 3.10 Split-view YAML editor.
- [ ] 3.11 History panel + time-travel.
- [ ] 3.12 Full icon-set redraw.

## 4. Tests + docs

- [x] 4.1 Smoke test: each new widget renders on
      `QT_QPA_PLATFORM=offscreen`.
- [x] 4.2 Unit test: `shortcut_format` smoke test on macOS host.
- [x] 4.3 Update `docs/ux-audit-2026-05.md` to mark shipped items.
- [ ] 4.4 README screenshot refresh (deferred to wave 2 alongside
      the unified titlebar).

## 5. Release

- [ ] 5.1 Bump PulsimGui version `0.8.0 → 0.8.1` across
      `pyproject.toml` and `src/pulsimgui/__init__.py`.
- [ ] 5.2 Tag `v0.8.1`, push, monitor the release workflow.
- [ ] 5.3 Verify the GitHub Release artifacts (linux tarball, AppImage,
      macOS dmg, windows installer) build cleanly.
