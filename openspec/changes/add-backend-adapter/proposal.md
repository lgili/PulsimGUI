## Why
The GUI still runs entirely on placeholder waveforms and cannot talk to the real Pulsim backend. We need a stable way to load the `pulsimcore` solver that ships on PyPI, swap between versions (stable/nightly), and surface compatibility information to the user. Without an adapter we cannot validate real circuits or guarantee that simulation buttons map to backend features.

## What Changes
- Introduce a backend adapter layer that loads whichever `pulsimcore` version is installed (or selected) via pip metadata and exposes a stable interface to the GUI.
- Replace the placeholder simulation/parameter sweep workers with calls into the adapter for transient, DC, AC, and sweep executions, plus circuit conversion utilities.
- Add UI + settings affordances to display the detected backend version, allow overriding it when multiple builds are installed, and block simulations when no compatible backend exists.
- Provide structured error handling so version mismatches, missing APIs, or runtime exceptions propagate to the front-end status/progress messaging.

## Impact
- Specs: `simulation-control`
- Code: `src/pulsimgui/services/simulation_service.py`, `services/settings_service.py`, new backend adapter module, parameter sweep infrastructure, status/progress UX.
