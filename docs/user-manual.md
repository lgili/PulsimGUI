# PulsimGui User Manual

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Quick Start](#quick-start)
4. [User Interface](#user-interface)
5. [Schematic Editor](#schematic-editor)
6. [Component Library](#component-library)
7. [Simulation](#simulation)
8. [Waveform Viewer](#waveform-viewer)
9. [Project Management](#project-management)
10. [Keyboard Shortcuts](#keyboard-shortcuts)
11. [Troubleshooting](#troubleshooting)

---

## Introduction

PulsimGui is a cross-platform graphical user interface for the Pulsim power electronics simulator. It provides an intuitive schematic editor for designing, simulating, and analyzing power converter circuits.

### Key Features

- **Schematic Editor**: Drag-and-drop component placement with orthogonal wire routing
- **Component Library**: Comprehensive library of power electronics devices (MOSFETs, IGBTs, diodes, etc.)
- **Simulation**: Transient, DC operating point, and AC analysis
- **Waveform Viewer**: Real-time plotting with cursors and measurements
- **Templates**: Pre-built converter topologies (Buck, Boost, Full-Bridge)
- **Export**: SPICE netlist, PNG/SVG images, CSV waveforms

---

## Installation

### From Release Package

#### Windows
1. Download `PulsimGui-x.x.x-setup.exe` from the releases page
2. Run the installer and follow the prompts
3. Launch PulsimGui from the Start Menu

#### macOS
1. Download `PulsimGui-x.x.x-macos.dmg` from the releases page
2. Open the DMG and drag PulsimGui to Applications
3. First launch: Right-click the app and select "Open" to bypass Gatekeeper

#### Linux
1. Download `PulsimGui-x.x.x-x86_64.AppImage` from the releases page
2. Make executable: `chmod +x PulsimGui-*.AppImage`
3. Run: `./PulsimGui-*.AppImage`

### From Source

```bash
# Clone the repository
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# or: .venv\Scripts\activate  # Windows

# Install
pip install -e .

# Run
pulsimgui
```

---

## Quick Start

### Creating Your First Circuit

1. **Start PulsimGui** - Launch the application
2. **Add Components** - Drag components from the library panel or use keyboard shortcuts:
   - `R` - Resistor
   - `C` - Capacitor
   - `L` - Inductor
   - `V` - Voltage Source
   - `G` - Ground
3. **Connect Components** - Press `W` to enter wire mode, click on pins to connect
4. **Set Parameters** - Select a component and edit values in the Properties panel
5. **Run Simulation** - Press `F5` or click Run in the toolbar
6. **View Results** - Waveforms appear in the bottom panel

### Using Templates

For common converter topologies:

1. Go to **File > New from Template** (or press `Ctrl+Shift+N`)
2. Select a template (Buck Converter, Boost Converter, or Full-Bridge)
3. Click **Create Project**
4. Modify parameters as needed
5. Run simulation

---

## User Interface

### Main Window Layout

```
+--------------------------------------------------+
|  Menu Bar                                        |
+--------------------------------------------------+
|  Toolbar                                         |
+--------+--------------------------------+--------+
|        |                                |        |
|Library |     Schematic Editor           |Props   |
| Panel  |                                |Panel   |
|        |                                |        |
+--------+--------------------------------+--------+
|              Waveform Viewer                     |
+--------------------------------------------------+
|  Status Bar                                      |
+--------------------------------------------------+
```

### Panels

- **Component Library** (Left): Browse and search for components
- **Schematic Editor** (Center): Design your circuit
- **Properties Panel** (Right): Edit selected component parameters
- **Waveform Viewer** (Bottom): View simulation results

### Toolbar

| Button | Action |
|--------|--------|
| New | Create new project |
| Open | Open existing project |
| Save | Save current project |
| Undo/Redo | Undo/redo actions |
| Zoom +/- | Zoom in/out |
| Fit | Zoom to fit all |
| Run | Start simulation |
| Stop | Stop simulation |

---

## Schematic Editor

### Navigation

| Action | Mouse | Keyboard |
|--------|-------|----------|
| Pan | Middle-click drag | Arrow keys |
| Zoom | Scroll wheel | `Ctrl++` / `Ctrl+-` |
| Zoom to fit | - | `Ctrl+0` |
| Toggle grid | - | `G` |

### Component Placement

#### From Library Panel
1. Find component in the library tree
2. Drag component to the schematic
3. Release to place

#### Using Keyboard Shortcuts
Press the shortcut key to enter placement mode:
- `R` - Resistor
- `C` - Capacitor
- `L` - Inductor
- `V` - Voltage Source
- `I` - Current Source
- `G` - Ground
- `D` - Diode
- `M` - MOSFET

Click on the schematic to place the component.

### Component Manipulation

| Action | Method |
|--------|--------|
| Select | Click on component |
| Multi-select | `Ctrl+Click` or box select |
| Move | Drag selected component |
| Rotate | Press `R` while selected |
| Mirror | Press `X` (horizontal) or `Y` (vertical) |
| Delete | Press `Delete` or `Backspace` |

### Wire Routing

1. Press `W` to enter wire mode (or click on a component pin)
2. Click on the starting pin
3. Click to place intermediate points (orthogonal routing)
4. Click on the destination pin to complete
5. Press `Escape` to cancel

Wires automatically connect when they touch component pins or other wires at junction points.

---

## Component Library

### Categories

#### Passive Components
- **Resistor** - Fixed resistance
- **Capacitor** - Capacitance with optional initial voltage
- **Inductor** - Inductance with optional initial current

#### Sources
- **Voltage Source** - DC, Pulse, Sine, PWL, or PWM waveforms
- **Current Source** - DC, Pulse, Sine, PWL waveforms
- **Ground** - Reference node (0V)

#### Semiconductors
- **Diode** - PN junction diode
- **MOSFET (N-channel)** - Enhancement mode NMOS
- **MOSFET (P-channel)** - Enhancement mode PMOS
- **IGBT** - Insulated Gate Bipolar Transistor

#### Switches
- **Switch** - Ideal switch with on/off resistance

#### Magnetics
- **Transformer** - Ideal transformer with turns ratio

### Component Parameters

Select a component to view and edit its parameters in the Properties panel:

#### Resistor
- `resistance` - Resistance in Ohms (supports SI prefixes: k, M, m, u)

#### Capacitor
- `capacitance` - Capacitance in Farads
- `initial_voltage` - Initial voltage across capacitor

#### Inductor
- `inductance` - Inductance in Henries
- `initial_current` - Initial current through inductor

#### Voltage Source
- `waveform.type` - dc, pulse, sine, pwl, or pwm
- Additional parameters depend on waveform type

---

## Simulation

### Transient Analysis

Simulates circuit behavior over time.

1. Configure simulation settings: **Simulation > Simulation Settings**
2. Set:
   - **Stop Time** - Simulation duration
   - **Time Step** - Maximum integration step
3. Click **Run** or press `F5`

### DC Operating Point

Calculates steady-state DC voltages and currents.

1. Go to **Simulation > DC Operating Point** or press `F6`
2. Results appear in a dialog and optionally as overlays on the schematic

### AC Analysis

Performs frequency-domain analysis (Bode plots).

1. Go to **Simulation > AC Analysis** or press `F7`
2. Configure frequency range and number of points
3. View magnitude and phase plots

### Simulation Settings

Access via **Simulation > Simulation Settings** (`Ctrl+Alt+S`):

**Transient Tab:**
- Stop Time
- Time Step
- Start Time

**Solver Tab:**
- Solver Type (RK4, etc.)
- Relative Tolerance
- Absolute Tolerance

---

## Waveform Viewer

### Adding Signals

- Signals are automatically added during simulation
- Drag signals from the Signal List to add to plot
- Click signal visibility checkbox to show/hide

### Navigation

| Action | Method |
|--------|--------|
| Zoom X | Scroll wheel |
| Zoom Y | `Ctrl+Scroll` |
| Pan | Right-click drag |
| Zoom rectangle | `Shift+Drag` |
| Zoom to fit | Double-click |

### Cursors

1. Click on a trace to place Cursor 1
2. `Ctrl+Click` to place Cursor 2
3. Delta measurements appear between cursors

### Measurements

The Measurements panel shows:
- **Min/Max** - Minimum and maximum values
- **Mean** - Average value
- **RMS** - Root Mean Square
- **Peak-to-Peak** - Difference between max and min

---

## Project Management

### File Operations

| Action | Shortcut |
|--------|----------|
| New Project | `Ctrl+N` |
| New from Template | `Ctrl+Shift+N` |
| Open Project | `Ctrl+O` |
| Save | `Ctrl+S` |
| Save As | `Ctrl+Shift+S` |
| Close Project | `Ctrl+W` |

### File Format

Projects are saved as `.pulsim` files (JSON format containing circuit topology, component parameters, and simulation settings).

### Export Options

**File > Export:**
- **SPICE Netlist** - Export to .sp/.cir for use in other simulators
- **JSON Netlist** - Pulsim-native format
- **PNG/SVG** - Export schematic as image
- **CSV** - Export waveform data

### Auto-Save

PulsimGui automatically saves backup copies. Configure in:
**Edit > Preferences > General:**
- Enable/disable auto-save
- Set auto-save interval (minutes)

---

## Keyboard Shortcuts

### File
| Shortcut | Action |
|----------|--------|
| `Ctrl+N` | New Project |
| `Ctrl+Shift+N` | New from Template |
| `Ctrl+O` | Open Project |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As |
| `Ctrl+W` | Close Project |
| `Ctrl+Q` | Exit |

### Edit
| Shortcut | Action |
|----------|--------|
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+X` | Cut |
| `Ctrl+C` | Copy |
| `Ctrl+V` | Paste |
| `Delete` | Delete selected |
| `Ctrl+A` | Select All |

### View
| Shortcut | Action |
|----------|--------|
| `Ctrl++` | Zoom In |
| `Ctrl+-` | Zoom Out |
| `Ctrl+0` | Zoom to Fit |
| `G` | Toggle Grid |
| `D` | Toggle DC Values |

### Components
| Shortcut | Component |
|----------|-----------|
| `R` | Resistor |
| `C` | Capacitor |
| `L` | Inductor |
| `V` | Voltage Source |
| `I` | Current Source |
| `G` | Ground |
| `D` | Diode |
| `M` | MOSFET |
| `W` | Wire Mode |

### Simulation
| Shortcut | Action |
|----------|--------|
| `F5` | Run Simulation |
| `Shift+F5` | Stop Simulation |
| `F6` | DC Operating Point |
| `F7` | AC Analysis |
| `F8` | Pause/Resume |

---

## Troubleshooting

### Common Issues

#### Application won't start
- Ensure you have the required system libraries (OpenGL, etc.)
- On Linux, try: `QT_QPA_PLATFORM=xcb ./PulsimGui-*.AppImage`

#### Simulation fails to converge
- Check for floating nodes (unconnected pins)
- Ensure there's a ground reference
- Try reducing time step
- Add small parasitic resistances to ideal switches

#### Components not visible
- Check if you're zoomed out too far (`Ctrl+0` to fit)
- Verify the component was actually placed (check component count in status bar)

#### Waveforms not appearing
- Ensure simulation completed successfully
- Check that signals are visible in the Signal List
- Try "Zoom to Fit" in waveform viewer

### Getting Help

- **GitHub Issues**: https://github.com/lgili/PulsimGui/issues
- **Documentation**: https://github.com/lgili/PulsimGui/docs

---

## Appendix: SI Prefixes

PulsimGui supports SI prefixes for parameter entry:

| Prefix | Symbol | Factor |
|--------|--------|--------|
| femto | f | 10^-15 |
| pico | p | 10^-12 |
| nano | n | 10^-9 |
| micro | u | 10^-6 |
| milli | m | 10^-3 |
| kilo | k | 10^3 |
| mega | M | 10^6 |
| giga | G | 10^9 |

**Examples:**
- `1k` = 1000
- `10u` = 0.00001
- `4.7n` = 4.7e-9
