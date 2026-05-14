# Waveform Viewer

## Purpose

An oscilloscope-inspired waveform display for viewing simulation results with interactive cursors, measurements, and real-time streaming during simulation.
## Requirements
### Requirement: Scope Panel Structure

The waveform viewer SHALL be displayed as a dockable panel with multiple plot areas.

#### Scenario: Default position
- **GIVEN** the application is running
- **THEN** the waveform viewer SHALL be dockable at the bottom of the main window

#### Scenario: Multiple plot areas
- **GIVEN** the waveform viewer is visible
- **THEN** the user SHALL be able to create multiple vertically stacked plot areas

#### Scenario: Plot area management
- **GIVEN** multiple plot areas exist
- **WHEN** the user right-clicks on a plot area
- **THEN** options SHALL include:
  - Add plot area above/below
  - Remove this plot area
  - Merge with adjacent plot area
  - Split this plot area

### Requirement: Signal Display

The viewer SHALL display voltage and current waveforms from simulation results.

#### Scenario: Add signal to plot
- **GIVEN** simulation results are available
- **WHEN** the user drags a signal from the signal list to a plot area
- **THEN** the signal SHALL be displayed as a trace with a unique color

#### Scenario: Add signal from schematic
- **GIVEN** a voltage probe exists on the schematic
- **WHEN** the user double-clicks the probe after simulation
- **THEN** the signal SHALL be added to the waveform viewer

#### Scenario: Signal visibility toggle
- **GIVEN** signals are displayed
- **THEN** a legend SHALL show all signals with:
  - Color indicator
  - Signal name
  - Visibility checkbox
  - Click to isolate (show only this signal)

#### Scenario: Signal removal
- **GIVEN** a signal is displayed
- **WHEN** the user right-clicks the signal and selects "Remove"
- **THEN** the signal SHALL be removed from the plot

### Requirement: Axis Control

The viewer SHALL provide flexible axis configuration.

#### Scenario: Auto-scale Y axis
- **GIVEN** signals are displayed
- **WHEN** the user double-clicks the Y axis or presses A
- **THEN** the Y axis SHALL auto-scale to fit all visible signals with 10% margin

#### Scenario: Manual Y axis limits
- **GIVEN** the user right-clicks the Y axis
- **THEN** a dialog SHALL allow entering min/max values manually

#### Scenario: Y axis per signal
- **GIVEN** multiple signals are displayed
- **WHEN** the user enables "Independent Y Axes"
- **THEN** each signal SHALL have its own Y axis scale

#### Scenario: Logarithmic scale
- **GIVEN** the user right-clicks the axis
- **THEN** options SHALL include:
  - Linear scale (default)
  - Logarithmic scale
  - dB scale (20*log10)

#### Scenario: X axis control
- **GIVEN** waveforms are displayed
- **THEN** the X axis SHALL:
  - Show time in appropriate units (ns, us, ms, s)
  - Support zoom via mouse wheel
  - Support pan via drag

### Requirement: Zoom and Pan

The viewer SHALL provide intuitive navigation of waveform data.

#### Scenario: Zoom with scroll wheel
- **GIVEN** the cursor is over the plot area
- **WHEN** the user scrolls the mouse wheel
- **THEN** the view SHALL zoom in/out horizontally centered on the cursor

#### Scenario: Zoom rectangle
- **GIVEN** the user holds Ctrl and drags a rectangle
- **THEN** the view SHALL zoom to fit that time range

#### Scenario: Pan with drag
- **GIVEN** the user drags with the middle mouse button
- **THEN** the view SHALL pan horizontally

#### Scenario: Zoom to fit
- **WHEN** the user presses F or double-clicks the X axis
- **THEN** the view SHALL show the entire simulation time range

#### Scenario: Zoom stack (back/forward)
- **GIVEN** zoom operations have been performed
- **WHEN** the user presses Backspace or uses toolbar buttons
- **THEN** the view SHALL return to the previous zoom level

### Requirement: Cursors

The viewer SHALL provide measurement cursors like a real oscilloscope.

#### Scenario: Place cursor
- **GIVEN** the cursor tool is selected
- **WHEN** the user clicks on the plot
- **THEN** a vertical cursor line SHALL appear at that time position

#### Scenario: Two-cursor measurement
- **GIVEN** the user places two cursors
- **THEN** the viewer SHALL display:
  - Time at each cursor (T1, T2)
  - Delta time (T2 - T1)
  - Frequency (1 / delta time)
  - Signal values at each cursor
  - Delta value between cursors

#### Scenario: Cursor drag
- **GIVEN** a cursor exists
- **WHEN** the user drags the cursor handle
- **THEN** the cursor SHALL move and measurements SHALL update in real-time

#### Scenario: Cursor snap to peak
- **GIVEN** a cursor is being placed
- **WHEN** the user holds Shift
- **THEN** the cursor SHALL snap to the nearest peak or valley

### Requirement: Measurements

The viewer SHALL provide automatic measurements on displayed signals.

#### Scenario: Measurement panel
- **GIVEN** signals are displayed
- **WHEN** the user opens the Measurements panel
- **THEN** available measurements SHALL include:
  - Minimum, Maximum, Peak-to-Peak
  - Mean, RMS
  - Rise time, Fall time
  - Frequency, Period
  - Duty cycle
  - Overshoot, Undershoot

#### Scenario: Add measurement
- **GIVEN** the measurement panel is open
- **WHEN** the user selects a measurement type and signal
- **THEN** the measurement SHALL:
  - Appear in the measurement list
  - Update automatically when the view changes
  - Use the visible time range by default

#### Scenario: Measurement between cursors
- **GIVEN** two cursors are placed
- **WHEN** the user adds a measurement
- **THEN** the measurement SHALL be calculated between cursor positions

### Requirement: Real-time Streaming

The viewer SHALL update in real-time during simulation.

#### Scenario: Live update during simulation
- **GIVEN** a simulation is running
- **THEN** the waveform display SHALL:
  - Update as new data arrives
  - Auto-scroll to show latest data (if enabled)
  - Maintain smooth display at 30+ FPS

#### Scenario: Rolling mode
- **GIVEN** simulation is running with rolling mode enabled
- **THEN** the display SHALL:
  - Show a fixed time window
  - Scroll left as new data arrives
  - Discard old data outside the window (for display only)

#### Scenario: Triggered mode
- **GIVEN** a trigger condition is set
- **THEN** the display SHALL:
  - Wait for trigger condition
  - Display a fixed time window around the trigger
  - Re-arm automatically for next trigger

### Requirement: Multiple Scopes

The application SHALL support multiple scope windows.

#### Scenario: New scope window
- **GIVEN** the user selects View > New Scope Window
- **THEN** a new scope window SHALL open as a floating window

#### Scenario: Scope configuration save
- **GIVEN** a scope has been configured with signals and settings
- **WHEN** the user saves the scope configuration
- **THEN** the configuration SHALL be saved with the project

### Requirement: Signal Math

The viewer SHALL support mathematical operations on signals.

#### Scenario: Add math signal
- **GIVEN** signals exist
- **WHEN** the user opens Signal > Add Math Signal
- **THEN** a dialog SHALL allow entering expressions like:
  - `V(out) - V(in)` (difference)
  - `V(out) / V(in)` (gain)
  - `I(R1) * V(R1)` (power)
  - `abs(V(out))` (absolute value)
  - `fft(V(out))` (frequency spectrum)

#### Scenario: Expression validation
- **GIVEN** the user enters an expression
- **THEN** the dialog SHALL:
  - Validate signal names exist
  - Check expression syntax
  - Show preview of result if valid

### Requirement: FFT Analysis

The viewer SHALL support frequency domain analysis.

#### Scenario: FFT computation
- **GIVEN** a time-domain signal is selected
- **WHEN** the user selects "Show FFT" from the context menu
- **THEN** a new plot SHALL show the frequency spectrum with:
  - X axis in Hz (or kHz, MHz)
  - Y axis in dB or linear magnitude
  - Configurable window function (Hanning, Hamming, Blackman, etc.)

#### Scenario: FFT parameters
- **GIVEN** an FFT is displayed
- **WHEN** the user opens FFT settings
- **THEN** options SHALL include:
  - Number of points (power of 2)
  - Window function
  - Averaging count
  - Frequency range limits

### Requirement: Export and Printing

The viewer SHALL support exporting waveform data and images.

#### Scenario: Export to image
- **GIVEN** waveforms are displayed
- **WHEN** the user selects Export > Image
- **THEN** options SHALL include:
  - PNG, SVG, PDF formats
  - Resolution selection
  - Include/exclude legend
  - Include/exclude measurements

#### Scenario: Export to CSV
- **GIVEN** waveforms are displayed
- **WHEN** the user selects Export > CSV
- **THEN** the visible signals SHALL be exported with:
  - Time column
  - One column per signal
  - Decimation option for large datasets

#### Scenario: Copy to clipboard
- **GIVEN** waveforms are displayed
- **WHEN** the user presses Ctrl+C
- **THEN** the current view SHALL be copied as an image

### Requirement: Persistence and Eye Diagrams

The viewer SHALL support eye diagram display for communication signals.

#### Scenario: Enable persistence
- **GIVEN** a repetitive signal is displayed
- **WHEN** the user enables "Persistence" mode
- **THEN** multiple traces SHALL overlay with color intensity showing frequency

#### Scenario: Eye diagram
- **GIVEN** a PWM or data signal is displayed
- **WHEN** the user enables "Eye Diagram" mode
- **THEN**:
  - The signal SHALL be overlaid modulo one period
  - Jitter and noise SHALL be visible
  - Eye opening measurements SHALL be available

### Requirement: Annotations

The viewer SHALL support user annotations on waveforms.

#### Scenario: Add text annotation
- **GIVEN** the annotation tool is selected
- **WHEN** the user clicks on the plot and types
- **THEN** a text annotation SHALL be placed at that position

#### Scenario: Add marker
- **GIVEN** a specific event is visible
- **WHEN** the user right-clicks and selects "Add Marker"
- **THEN** a marker with label SHALL be placed at that time

### Requirement: Signal List

The viewer SHALL provide a list of all available signals.

#### Scenario: Signal list panel
- **GIVEN** simulation results are loaded
- **THEN** a signal list SHALL show:
  - All node voltages (V(node_name))
  - All branch currents (I(component_name))
  - Computed signals (power, etc.)

#### Scenario: Signal filtering
- **GIVEN** the signal list is visible
- **THEN** a search/filter box SHALL allow finding signals by name

#### Scenario: Signal grouping
- **GIVEN** signals exist
- **THEN** signals SHALL be groupable by:
  - Type (voltage, current, power)
  - Subcircuit
  - User-defined groups

### Requirement: Menu Bar and Toolbar Architecture
The professional scope workspace SHALL provide compact top-level chrome that separates application-style commands from high-frequency actions.

The `Menu Bar` SHALL contain at minimum:
- `File`
- `View`
- `Simulation`
- `Tools`
- `Window`
- `Help`

The `Main Toolbar` SHALL group actions into:
- `Simulation`
- `Navigation`
- `Analysis`
- `Workspace`

The toolbar SHALL prioritize frequently used actions and move lower-frequency actions into menus, overflow affordances, or secondary surfaces when necessary to preserve horizontal clarity.

#### Scenario: Compact top chrome hierarchy
- **GIVEN** the scope window is visible
- **THEN** menu bar and toolbar SHALL appear as separate rows with clear grouping
- **AND** the toolbar SHALL use separators or equivalent visual structure to communicate groups without consuming excessive height

#### Scenario: Prioritized visible actions
- **GIVEN** the toolbar is rendered at normal desktop widths
- **THEN** high-frequency actions such as transport, fit, cursor, measurements, grid, and panel toggles SHALL remain visually prioritized
- **AND** secondary actions SHALL NOT force the toolbar into a crowded, hard-to-scan strip

#### Scenario: Tooltip and shortcut disclosure
- **GIVEN** the user hovers a toolbar action or opens a matching menu item
- **THEN** the UI SHALL disclose the action name, a short description, and the shortcut when one exists

### Requirement: Central Workspace Tabs and Plot Composition
The central workspace SHALL provide tabbed analysis surfaces and a plot region capable of professional trace composition.

At minimum, the central workspace SHALL provide:
- `Scope` tab
- `FFT` tab
- `Compare` tab

The `Scope` tab SHALL support:
- overlay traces
- dual-axis traces
- stacked plots
- automatic mixed-scale trace separation
- plot context menu
- trace selection and emphasis

A navigator inset or minimap MAY be shown when it materially helps viewport context, but it SHALL NOT permanently obscure waveform readability.

#### Scenario: Independent tab state
- **GIVEN** the user changes zoom or settings in one analysis tab
- **WHEN** the user switches to another tab and back
- **THEN** each tab SHALL restore its own relevant visualization state

#### Scenario: Optional navigator visibility
- **GIVEN** the visible window is narrower than the full data range
- **WHEN** a navigator inset is shown
- **THEN** it SHALL indicate viewport context within the total domain
- **AND** it SHALL use the same trace identity colors as the main plot
- **AND** it SHALL avoid covering or competing with the primary waveform area

### Requirement: Inspector Panel
The professional scope workspace SHALL provide a contextual right-side inspector for the current selection.

The inspector SHALL contain collapsible sections for:
- `Trace`
- `Axis`
- `Style`
- `Cursor`
- `Measurements`

The inspector SHALL use a compact density appropriate for repeated waveform analysis and SHALL avoid consuming excessive permanent width when the plot area is constrained.

#### Scenario: Trace selection updates inspector
- **GIVEN** the user selects a trace from the plot or signals panel
- **THEN** the inspector SHALL show that trace as the active editing target
- **AND** editable fields SHALL reflect the current live state of the trace

#### Scenario: Inspector edits apply immediately
- **GIVEN** the user changes color, thickness, axis assignment, or measurement scope in the inspector
- **THEN** the plot, signals panel, and other dependent readouts SHALL update without requiring an explicit apply step

#### Scenario: Compact inspector under constrained space
- **GIVEN** the scope window width is limited and the inspector is opened
- **WHEN** full-width inspector rendering would significantly reduce the plot area
- **THEN** the inspector SHALL use a compact or overlay presentation instead of permanently starving the waveform

### Requirement: Bottom Drawer
The professional scope workspace SHALL provide an expandable bottom drawer for detailed analysis outputs that should not permanently consume plot space.

The drawer SHALL provide these tabs:
- `Measurements`
- `Events`
- `Console`

The drawer SHALL remember:
- whether it is expanded or collapsed
- its last height
- its last active tab

A fresh scope window and `Reset Layout` SHALL keep the drawer collapsed by default.

When expanded, the drawer SHALL fit its content up to a bounded cap and SHALL avoid leaving large regions of empty space around small measurement tables.

#### Scenario: Measurements tab in the drawer
- **GIVEN** the drawer is expanded and `Measurements` is active
- **THEN** the table SHALL present per-signal metrics with stable columns and row identity markers
- **AND** the drawer SHALL size itself to the active content up to its configured maximum height

#### Scenario: Default collapsed drawer
- **GIVEN** the user opens a fresh scope window or triggers `Reset Layout`
- **THEN** the bottom drawer SHALL remain collapsed until explicitly opened

#### Scenario: Events and console separation
- **GIVEN** simulation messages and technical logs are produced
- **THEN** user-facing events and lower-level console/log output SHALL remain in separate tabs rather than one mixed feed

### Requirement: Quick Metrics and Status Feedback
The professional scope workspace SHALL provide compact immediate analysis feedback without competing excessively with the main plot.

The quick metrics strip SHALL summarize the current signal or active cursor interval using compact, tabular-aligned values.

When the detailed drawer is expanded, quick metrics MAY collapse, merge, or partially hide as long as equivalent information remains available through the drawer or status bar.

The status bar SHALL show at minimum:
- simulation state
- active analysis mode
- sample rate when available
- cursor positions and deltas when active

#### Scenario: Quick metrics follow active selection
- **GIVEN** the user changes the selected trace or active interval
- **THEN** the quick metrics strip SHALL update to the corresponding summary without requiring the drawer to be opened

#### Scenario: Quick metrics yield to detailed drawer
- **GIVEN** the detailed bottom drawer is expanded
- **WHEN** showing both surfaces at full height would reduce the plot unnecessarily
- **THEN** the quick metrics strip SHALL compact, merge, or hide redundant values
- **AND** the user SHALL still retain access to the same analysis context elsewhere in the workspace

#### Scenario: Status bar reflects cursor state
- **GIVEN** cursors are active
- **THEN** the status bar SHALL surface `X1`, `X2`, `Δt`, and `ΔY` when meaningful
- **AND** these readouts SHALL clear or revert gracefully when cursors are removed

### Requirement: Visual Language and Accessibility
The professional scope workspace SHALL follow a technical visual language where chrome remains neutral and data remains vivid.

The UI SHALL provide:
- consistent trace colors across all surfaces
- tooltips on actionable controls
- visible hover and active states
- keyboard navigation across panels, tabs, tables, and inspector fields
- sufficient contrast for text and cursor labels
- a plot surface visually distinct from surrounding shell chrome

The active application theme provided by `ThemeService` SHALL remain the source of truth, but the plot SHALL use dedicated analysis-surface tokens derived from that theme so waveform readability remains strong in both light and dark shells.

#### Scenario: Signal identity consistency
- **GIVEN** a trace is visible in multiple surfaces
- **THEN** its color identity SHALL remain consistent in the tree, plot, quick metrics, measurement table, and inspector swatch

#### Scenario: Plot emphasis inside a light shell
- **GIVEN** the user is using a light application theme
- **WHEN** the scope plot is rendered
- **THEN** the plot SHALL remain visually distinct from the surrounding shell chrome
- **AND** traces, grid lines, text, overlays, and cursor labels SHALL remain easier to read than the surrounding non-plot surfaces

#### Scenario: Keyboard-driven operation
- **GIVEN** the user navigates without a mouse
- **WHEN** using documented shortcuts or focus traversal
- **THEN** core actions such as run/pause, stop, fit, cursor toggle, measurement toggle, grid toggle, and add expression SHALL remain accessible

