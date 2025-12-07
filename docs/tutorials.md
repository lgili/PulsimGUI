# PulsimGui Video Tutorials

This document contains outlines and scripts for tutorial videos covering PulsimGui usage.

---

## Tutorial 1: Getting Started with PulsimGui

**Duration:** ~5 minutes
**Level:** Beginner

### Outline

1. **Introduction** (0:30)
   - Welcome and overview
   - What PulsimGui is and what it's used for
   - Show the main interface

2. **Interface Tour** (1:00)
   - Main window layout
   - Component Library panel (left)
   - Schematic Editor (center)
   - Properties Panel (right)
   - Waveform Viewer (bottom)
   - Toolbar and menus

3. **Creating Your First Circuit** (2:00)
   - Create a new project (Ctrl+N)
   - Add a voltage source (press V, click to place)
   - Add a resistor (press R, click to place)
   - Add ground (press G, click to place)
   - Rotate components as needed (R key)

4. **Connecting Components** (1:00)
   - Enter wire mode (W key)
   - Click on first pin
   - Route wire orthogonally
   - Click on destination pin
   - Verify connections

5. **Running Your First Simulation** (0:30)
   - Press F5 to run
   - View waveforms in the bottom panel
   - Basic navigation (zoom, pan)

### Script Notes

- Keep mouse movements slow and deliberate for visibility
- Highlight keyboard shortcuts as they're used
- Pause briefly after each major action

---

## Tutorial 2: Building a Buck Converter

**Duration:** ~10 minutes
**Level:** Intermediate

### Outline

1. **Introduction** (0:30)
   - What is a buck converter?
   - Target specifications: 12V to 5V, 1A output

2. **Using Templates** (1:00)
   - File > New from Template (Ctrl+Shift+N)
   - Select "Buck Converter"
   - Overview of the generated circuit

3. **Understanding the Topology** (2:00)
   - Input voltage source
   - MOSFET switch
   - Diode (freewheeling)
   - Inductor
   - Output capacitor
   - Load resistor
   - PWM control signal

4. **Modifying Component Values** (2:00)
   - Select components and use Properties panel
   - Input voltage: 12V DC
   - Inductor: 100µH
   - Capacitor: 100µF
   - Load: 5Ω (for 1A at 5V)
   - PWM: 100kHz, 41.7% duty cycle

5. **Configuring Simulation** (1:00)
   - Simulation > Simulation Settings
   - Set stop time: 10ms
   - Set time step: 100ns
   - Discuss why these values matter

6. **Running and Analyzing** (2:30)
   - Run simulation (F5)
   - Add output voltage to waveform viewer
   - Add inductor current
   - Use cursors to measure ripple
   - Measure average output voltage

7. **Design Iteration** (1:00)
   - Adjust duty cycle for exact 5V output
   - Increase capacitance to reduce ripple
   - Re-run and verify improvements

### Key Teaching Points

- Relationship between duty cycle and output voltage
- Effect of inductance on current ripple
- Effect of capacitance on voltage ripple
- Importance of time step for switching circuits

---

## Tutorial 3: Building a Boost Converter

**Duration:** ~10 minutes
**Level:** Intermediate

### Outline

1. **Introduction** (0:30)
   - What is a boost converter?
   - Target: 5V to 12V conversion

2. **Circuit Construction** (3:00)
   - Start with template or build from scratch
   - Place input source (5V)
   - Add inductor
   - Add MOSFET switch to ground
   - Add diode to output
   - Add output capacitor
   - Add load resistor

3. **PWM Configuration** (2:00)
   - Calculate required duty cycle: D = 1 - (Vin/Vout) = 58.3%
   - Configure PWM source
   - Set frequency (100kHz)
   - Set duty cycle

4. **Simulation and Analysis** (3:00)
   - Configure transient analysis
   - Run simulation
   - Observe startup transient
   - Measure steady-state output
   - Analyze inductor current (continuous vs discontinuous mode)

5. **Efficiency Considerations** (1:30)
   - Add current measurements
   - Calculate input/output power
   - Discuss loss mechanisms (ideal vs real components)

---

## Tutorial 4: Full-Bridge Inverter

**Duration:** ~12 minutes
**Level:** Advanced

### Outline

1. **Introduction** (1:00)
   - Full-bridge topology overview
   - Applications: Motor drives, UPS, solar inverters
   - Bipolar vs unipolar modulation

2. **Building the Circuit** (3:00)
   - Use full-bridge template
   - Four MOSFETs in H-bridge configuration
   - DC bus capacitors
   - Output LC filter
   - Load resistor

3. **Understanding PWM Strategies** (2:00)
   - Bipolar switching: diagonal pairs switch together
   - Unipolar switching: each leg switches independently
   - Set up PWM sources for bipolar modulation

4. **Simulation Setup** (2:00)
   - Longer simulation time for AC waveforms
   - Appropriate time step for switching frequency
   - Configure carrier and reference signals

5. **Results Analysis** (3:00)
   - Output voltage waveform
   - FFT analysis (if available)
   - THD measurement
   - Current analysis

6. **Design Optimization** (1:00)
   - Filter design for THD reduction
   - Dead-time considerations
   - Switching frequency selection

---

## Tutorial 5: Waveform Viewer Deep Dive

**Duration:** ~8 minutes
**Level:** Beginner to Intermediate

### Outline

1. **Adding Signals** (1:30)
   - Signal list panel
   - Drag signals to plot
   - Multiple traces on same plot
   - Removing signals

2. **Navigation** (2:00)
   - Zoom with scroll wheel
   - Pan with right-click drag
   - Zoom rectangle with Shift+drag
   - Zoom to fit (double-click)
   - Zoom history (back/forward)

3. **Using Cursors** (2:00)
   - Place cursor 1 (click on trace)
   - Place cursor 2 (Ctrl+click)
   - Read values at cursor positions
   - Delta measurements
   - Drag cursors to new positions

4. **Measurements Panel** (1:30)
   - Min/Max values
   - Mean (average)
   - RMS value
   - Peak-to-peak
   - Understanding when each is useful

5. **Exporting Data** (1:00)
   - Export as CSV
   - Copy to clipboard
   - Use in external analysis tools

---

## Tutorial 6: Project Management

**Duration:** ~5 minutes
**Level:** Beginner

### Outline

1. **Creating Projects** (1:00)
   - New project (Ctrl+N)
   - New from template (Ctrl+Shift+N)
   - Project file format (.pulsim)

2. **Saving and Loading** (1:30)
   - Save (Ctrl+S)
   - Save As (Ctrl+Shift+S)
   - Open existing project (Ctrl+O)
   - Recent files menu

3. **Auto-Save and Recovery** (1:00)
   - Auto-save feature
   - Finding backup files
   - Crash recovery

4. **Exporting** (1:30)
   - Export to SPICE netlist
   - Export schematic as image (PNG/SVG)
   - Export waveforms as CSV
   - Export JSON netlist

---

## Tutorial 7: Keyboard Shortcuts and Productivity

**Duration:** ~5 minutes
**Level:** All Levels

### Outline

1. **Component Shortcuts** (1:30)
   - R - Resistor
   - C - Capacitor
   - L - Inductor
   - V - Voltage Source
   - G - Ground
   - D - Diode
   - M - MOSFET
   - W - Wire mode

2. **Editing Shortcuts** (1:00)
   - Ctrl+Z / Ctrl+Y - Undo/Redo
   - Delete - Remove selected
   - R (with selection) - Rotate
   - X/Y - Mirror

3. **View Navigation** (1:00)
   - Ctrl++ / Ctrl+- - Zoom
   - Ctrl+0 - Fit to view
   - Middle-click drag - Pan
   - G - Toggle grid

4. **Simulation Shortcuts** (1:00)
   - F5 - Run simulation
   - Shift+F5 - Stop simulation
   - F6 - DC operating point
   - F7 - AC analysis

5. **Customization** (0:30)
   - Edit > Preferences > Shortcuts
   - Setting custom shortcuts

---

## Production Notes

### Recording Setup

- Screen resolution: 1920x1080 minimum
- Use dark theme for better visibility in recordings
- Enable cursor highlighting
- Record keyboard shortcuts overlay if possible

### Post-Production

- Add intro/outro with PulsimGui branding
- Include chapter markers for YouTube
- Add closed captions for accessibility
- Include download links for example projects

### Distribution

- Upload to YouTube
- Embed in documentation website
- Link from application Help menu

---

## Quick Reference Card

A printable quick reference card should accompany the tutorials:

```
╔══════════════════════════════════════════════════════════════╗
║                    PulsimGui Quick Reference                  ║
╠══════════════════════════════════════════════════════════════╣
║ COMPONENTS          │ EDITING             │ VIEW              ║
║ R - Resistor        │ Ctrl+Z - Undo       │ Ctrl++ - Zoom In  ║
║ C - Capacitor       │ Ctrl+Y - Redo       │ Ctrl+- - Zoom Out ║
║ L - Inductor        │ Del - Delete        │ Ctrl+0 - Fit      ║
║ V - Voltage Source  │ Ctrl+A - Select All │ G - Grid Toggle   ║
║ I - Current Source  │ Ctrl+C - Copy       │                   ║
║ G - Ground          │ Ctrl+V - Paste      │ SIMULATION        ║
║ D - Diode           │                     │ F5 - Run          ║
║ M - MOSFET          │ TRANSFORM           │ Shift+F5 - Stop   ║
║ W - Wire Mode       │ R - Rotate          │ F6 - DC Analysis  ║
║                     │ X - Mirror X        │ F7 - AC Analysis  ║
║                     │ Y - Mirror Y        │ F8 - Pause        ║
╚══════════════════════════════════════════════════════════════╝
```
