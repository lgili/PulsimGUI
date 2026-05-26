## Why
The scope workspace currently overrides the application theme with a scope-local dark shell, which creates inconsistent theming across dialogs, menus, combo popups, inspector controls, and embedded waveform surfaces. This makes the workspace visually incoherent and prevents users who prefer light themes from getting a complete themed experience.

## What Changes
- Refactor the scope workspace to derive all chrome, panel, control, dialog, menu, and popup styling from `ThemeService` instead of hard-coded dark scope palettes.
- Introduce scope-specific semantic theme tokens built from the active app theme so the scope can preserve technical contrast without bypassing the global theme.
- Update the waveform viewer, measurements panel, signals panel, math expression dialog, inspector menus, and combo dropdown popups to use the same active theme contract.
- Add regression tests for theme propagation across standalone scope surfaces and interactive popups/dialogs.

## Impact
- Affected specs: `waveform-viewer`
- Affected code: `src/pulsimgui/views/scope/scope_window.py`, `src/pulsimgui/views/waveform/waveform_viewer.py`, scope-related tests, theme integration paths
