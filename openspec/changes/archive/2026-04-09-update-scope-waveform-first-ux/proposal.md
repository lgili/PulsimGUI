## Why
The current scope has the right functional building blocks, but the waveform is still not consistently treated as the primary surface. In practice, once the left signals panel, right inspector, and bottom measurements are open together, the plot loses too much usable area and mixed-scale traces become harder to interpret.

The next scope pass should focus on waveform-first hierarchy, adaptive chrome behavior, and automatic trace legibility so the UI feels like a professional analysis instrument instead of a generic data panel.

## What Changes
- Introduce a waveform-first layout policy for the scope window, including fresh-open and reset-layout defaults where auxiliary surfaces start collapsed.
- Add adaptive panel budgeting so sidebars, inspector, and bottom drawer do not permanently starve the plot when the viewport is constrained.
- Add automatic mixed-scale trace composition rules so signals with incompatible units or strongly different amplitudes are separated by pane or axis by default.
- Refine the visual hierarchy so the plot remains a dedicated high-contrast analysis surface even when the application shell uses a light theme.
- Reduce toolbar, sidebar, inspector, and bottom drawer density so frequent analysis workflows preserve plot visibility.
- Allow quick metrics to compact or merge when the detailed drawer is open, avoiding duplicate analysis bands.

## Impact
- Affected specs: `waveform-viewer`
- Affected code:
  - `src/pulsimgui/views/scope/scope_window.py`
  - `src/pulsimgui/views/waveform/waveform_viewer.py`
  - theme/token plumbing used by scope-owned surfaces
  - scope layout, plot composition, and measurement drawer tests
