## ADDED Requirements

### Requirement: Scope Panel Structure

The waveform viewer SHALL be displayed as a dockable panel with multiple plot areas.

#### Scenario: Default position
- **GIVEN** the application is running
- **THEN** the waveform viewer SHALL be dockable at the bottom of the main window

### Requirement: Signal Display

The viewer SHALL display voltage and current waveforms from simulation results.

#### Scenario: Add signal to plot
- **GIVEN** simulation results are available
- **WHEN** the user drags a signal from the signal list to a plot area
- **THEN** the signal SHALL be displayed as a trace with a unique color

### Requirement: Axis Control

The viewer SHALL provide flexible axis configuration.

#### Scenario: Auto-scale Y axis
- **GIVEN** signals are displayed
- **WHEN** the user double-clicks the Y axis
- **THEN** the Y axis SHALL auto-scale to fit all visible signals

### Requirement: Zoom and Pan

The viewer SHALL provide intuitive navigation of waveform data.

#### Scenario: Zoom with scroll wheel
- **GIVEN** the cursor is over the plot area
- **WHEN** the user scrolls the mouse wheel
- **THEN** the view SHALL zoom in/out horizontally centered on the cursor

### Requirement: Cursors

The viewer SHALL provide measurement cursors like a real oscilloscope.

#### Scenario: Two-cursor measurement
- **GIVEN** the user places two cursors
- **THEN** the viewer SHALL display time at each cursor, delta time, and signal values

### Requirement: Measurements

The viewer SHALL provide automatic measurements on displayed signals.

#### Scenario: Measurement panel
- **GIVEN** signals are displayed
- **WHEN** the user opens the Measurements panel
- **THEN** available measurements SHALL include min, max, mean, RMS, rise time, frequency, and duty cycle

### Requirement: Real-time Streaming

The viewer SHALL update in real-time during simulation.

#### Scenario: Live update during simulation
- **GIVEN** a simulation is running
- **THEN** the waveform display SHALL update as new data arrives

### Requirement: Multiple Scopes

The application SHALL support multiple scope windows.

#### Scenario: New scope window
- **GIVEN** the user selects View > New Scope Window
- **THEN** a new scope window SHALL open as a floating window

### Requirement: Signal Math

The viewer SHALL support mathematical operations on signals.

#### Scenario: Add math signal
- **GIVEN** signals exist
- **WHEN** the user opens Signal > Add Math Signal
- **THEN** a dialog SHALL allow entering expressions like V(out) - V(in)

### Requirement: FFT Analysis

The viewer SHALL support frequency domain analysis.

#### Scenario: FFT computation
- **GIVEN** a time-domain signal is selected
- **WHEN** the user selects "Show FFT"
- **THEN** a new plot SHALL show the frequency spectrum

### Requirement: Export and Printing

The viewer SHALL support exporting waveform data and images.

#### Scenario: Export to CSV
- **GIVEN** waveforms are displayed
- **WHEN** the user selects Export > CSV
- **THEN** the visible signals SHALL be exported with time and signal columns

### Requirement: Persistence and Eye Diagrams

The viewer SHALL support eye diagram display for communication signals.

#### Scenario: Enable persistence
- **GIVEN** a repetitive signal is displayed
- **WHEN** the user enables "Persistence" mode
- **THEN** multiple traces SHALL overlay with color intensity showing frequency

### Requirement: Annotations

The viewer SHALL support user annotations on waveforms.

#### Scenario: Add text annotation
- **GIVEN** the annotation tool is selected
- **WHEN** the user clicks on the plot and types
- **THEN** a text annotation SHALL be placed at that position

### Requirement: Signal List

The viewer SHALL provide a list of all available signals.

#### Scenario: Signal list panel
- **GIVEN** simulation results are loaded
- **THEN** a signal list SHALL show all node voltages and branch currents
