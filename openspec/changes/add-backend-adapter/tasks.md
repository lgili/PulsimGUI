## 1. Backend abstraction
- [ ] 1.1 Document the adapter interface (required methods, expected data) mirroring `pulsimcore` APIs.
- [ ] 1.2 Implement a loader that discovers installed `pulsimcore` distributions via `importlib.metadata`, selects a version, and instantiates the adapter.
- [ ] 1.3 Add settings/state to surface the active backend version and allow opting into an alternate compatible build when multiple are present.

## 2. Simulation service integration
- [ ] 2.1 Refactor `SimulationService` workers to call the adapter for transient/DC/AC/sweep runs instead of generating placeholder signals.
- [ ] 2.2 Implement circuit conversion helpers that map GUI projects into the structures expected by the adapter/backend.
- [ ] 2.3 Ensure pause/stop/cancel signals, progress, and streaming waveform updates are routed through the adapter consistently.
- [ ] 2.4 Provide clear error propagation (missing backend, incompatible API) to the UI and disable run controls when unavailable.

## 3. UX + validation
- [ ] 3.1 Update simulation settings/status panels to show backend availability/version and any warnings.
- [ ] 3.2 Add tests covering backend discovery, selection, and failure paths.
- [ ] 3.3 Document how to install/switch backend versions via pip for developers and end users.
