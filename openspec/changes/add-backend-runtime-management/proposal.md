## Why

Backend selection exists, but backend provisioning is manual: users must run `pip` outside the GUI to install a specific `pulsim` version. This makes it hard to guarantee that GUI and backend stay aligned with the intended version (for example `v0.3.0`).

## What Changes

- Add runtime backend provisioning settings (target version, source, local path, auto-sync).
- Add a runtime manager service that installs/synchronizes `pulsim` via `pip`.
- Integrate runtime synchronization into `SimulationService`.
- Add Preferences UI controls to configure and trigger backend installation/update.
- Persist simulation settings updates from the simulation dialog through `SimulationService`.
- Add tests for runtime service and simulation-service runtime integration.

## Impact

- Affected specs: `simulation-control`
- Affected code:
  - `src/pulsimgui/services/backend_runtime_service.py` (new)
  - `src/pulsimgui/services/settings_service.py`
  - `src/pulsimgui/services/simulation_service.py`
  - `src/pulsimgui/views/dialogs/preferences_dialog.py`
  - `tests/test_services/test_backend_runtime_service.py` (new)
  - `tests/test_services/test_simulation_service_runtime.py` (new)
