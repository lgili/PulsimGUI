## Why

PulsimGui already has a strong functional base, but the current visual system still feels inconsistent across core workflows. The review identified recurring friction that prevents a professional, tool-grade experience comparable to PLECS:

- theme changes are not propagated consistently to custom widgets and plot surfaces
- many UI modules still use hardcoded colors instead of shared theme tokens
- toolbar hierarchy does not prioritize simulation workflows for high-frequency use
- waveform and thermal views mix fixed visual palettes with theme-aware elements

These gaps reduce perceived quality, increase visual noise, and make dark/light mode behavior inconsistent.

## What Changes

- Establish a complete theme-propagation model for custom/non-QSS widgets (minimap, properties panel, waveform viewer, thermal viewer, status widgets, context menus).
- Define and adopt a tokenized visual contract so UI modules stop relying on scattered hardcoded color literals.
- Reorganize toolbar information architecture around simulation-first usage (edit/view/simulation grouping + responsive overflow policy).
- Standardize schematic overlays and context menus to follow active theme tokens.
- Make waveform and thermal visualization surfaces theme-integrated, including axis, legend, grid, and measurement/readout colors.
- Add UX validation and regression checks (theme switching, contrast, visual consistency) to prevent future regressions.

## Impact

- Affected specs:
  - `application-shell`
  - `schematic-editor`
  - `component-library`
  - `parameter-editor`
  - `waveform-viewer`
  - `thermal-viewer`
- Affected code (expected):
  - `src/pulsimgui/services/theme_service.py`
  - `src/pulsimgui/views/main_window.py`
  - `src/pulsimgui/views/schematic/view.py`
  - `src/pulsimgui/views/widgets/minimap.py`
  - `src/pulsimgui/views/library/library_panel.py`
  - `src/pulsimgui/views/properties/properties_panel.py`
  - `src/pulsimgui/views/waveform/waveform_viewer.py`
  - `src/pulsimgui/views/thermal/thermal_viewer.py`
  - `src/pulsimgui/views/widgets/status_widgets.py`
