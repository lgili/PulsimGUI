# Implementation Tasks

## Phase 1: Foundation (MVP)

### 1.1 Project Setup
- [x] 1.1.1 Initialize Python project structure (pyproject.toml, src layout)
- [x] 1.1.2 Configure development environment (venv, requirements)
- [x] 1.1.3 Set up PySide6 and PyQtGraph dependencies
- [x] 1.1.4 Create basic application entry point (main.py)
- [x] 1.1.5 Set up pytest with pytest-qt for testing
- [x] 1.1.6 Configure black, ruff for code formatting/linting
- [x] 1.1.7 Set up GitHub Actions CI pipeline

### 1.2 Application Shell
- [x] 1.2.1 Create QMainWindow subclass with basic layout
- [x] 1.2.2 Implement docking panel infrastructure
- [x] 1.2.3 Create menu bar with File, Edit, View, Simulation menus
- [x] 1.2.4 Create main toolbar with placeholder buttons
- [x] 1.2.5 Implement status bar with coordinate display
- [x] 1.2.6 Add basic keyboard shortcut framework
- [x] 1.2.7 Implement light/dark theme switching
- [ ] 1.2.8 Create preferences dialog skeleton

### 1.3 Core Data Models
- [x] 1.3.1 Define Component model class
- [x] 1.3.2 Define Wire model class
- [x] 1.3.3 Define Circuit model (collection of components/wires)
- [x] 1.3.4 Define Project model (multiple schematics)
- [x] 1.3.5 Implement JSON serialization for models
- [x] 1.3.6 Unit tests for all models

### 1.4 Command Infrastructure
- [x] 1.4.1 Implement Command base class
- [x] 1.4.2 Implement CommandStack (undo/redo)
- [x] 1.4.3 Create AddComponentCommand
- [x] 1.4.4 Create DeleteComponentCommand
- [x] 1.4.5 Create MoveComponentCommand
- [x] 1.4.6 Create AddWireCommand
- [x] 1.4.7 Connect to Edit menu undo/redo actions
- [x] 1.4.8 Unit tests for command system

## Phase 2: Schematic Editor

### 2.1 Canvas and Viewport
- [x] 2.1.1 Create SchematicScene (QGraphicsScene)
- [x] 2.1.2 Create SchematicView (QGraphicsView) with pan/zoom
- [x] 2.1.3 Implement mouse wheel zoom to cursor
- [x] 2.1.4 Implement middle-button pan
- [x] 2.1.5 Implement zoom to fit
- [x] 2.1.6 Add zoom level display to status bar

### 2.2 Grid System
- [x] 2.2.1 Implement grid rendering (dots or lines)
- [x] 2.2.2 Implement snap-to-grid functionality
- [x] 2.2.3 Add grid size configuration
- [x] 2.2.4 Scale grid dots with zoom level

### 2.3 Component Graphics
- [x] 2.3.1 Create ComponentItem base class (QGraphicsItem)
- [x] 2.3.2 Implement resistor symbol
- [x] 2.3.3 Implement capacitor symbol
- [x] 2.3.4 Implement inductor symbol
- [x] 2.3.5 Implement voltage source symbol
- [x] 2.3.6 Implement current source symbol
- [x] 2.3.7 Implement ground symbol
- [x] 2.3.8 Implement diode symbol
- [x] 2.3.9 Implement MOSFET symbol (N and P)
- [x] 2.3.10 Implement IGBT symbol
- [x] 2.3.11 Implement switch symbol
- [x] 2.3.12 Implement transformer symbol
- [x] 2.3.13 Add pin markers to all symbols
- [x] 2.3.14 Implement component rotation (90° increments)
- [x] 2.3.15 Implement component mirroring

### 2.4 Component Placement
- [x] 2.4.1 Implement drag-and-drop from library
- [x] 2.4.2 Show ghost preview during placement
- [x] 2.4.3 Implement keyboard shortcuts for components (R, C, L, etc.)
- [x] 2.4.4 Auto-generate unique component names
- [x] 2.4.5 Implement component selection (click, box select)
- [x] 2.4.6 Implement multi-select with Ctrl+click
- [x] 2.4.7 Implement component moving

### 2.5 Wire Routing
- [x] 2.5.1 Create WireItem class (QGraphicsPathItem)
- [x] 2.5.2 Implement wire tool activation
- [x] 2.5.3 Implement click-to-start-wire on pin
- [x] 2.5.4 Implement orthogonal routing preview
- [x] 2.5.5 Implement wire completion on pin click
- [x] 2.5.6 Implement wire junction creation
- [x] 2.5.7 Implement wire cancellation (Escape)
- [x] 2.5.8 Show connection dots on connected pins

### 2.6 Labels and Annotations
- [x] 2.6.1 Display component names
- [x] 2.6.2 Display component values
- [x] 2.6.3 Allow label position adjustment
- [x] 2.6.4 Implement label visibility toggle

## Phase 3: Component Library & Properties

### 3.1 Library Panel
- [ ] 3.1.1 Create LibraryPanel widget
- [ ] 3.1.2 Implement category tree structure
- [ ] 3.1.3 Add component icons to tree items
- [ ] 3.1.4 Implement drag from library
- [ ] 3.1.5 Implement search/filter functionality
- [ ] 3.1.6 Add favorites category
- [ ] 3.1.7 Add recently used category
- [ ] 3.1.8 Implement tooltips with descriptions

### 3.2 Properties Panel
- [ ] 3.2.1 Create PropertiesPanel widget
- [ ] 3.2.2 Display component name (editable)
- [ ] 3.2.3 Implement numeric input with SI prefixes
- [ ] 3.2.4 Implement dropdown for enum parameters
- [ ] 3.2.5 Implement checkbox for boolean parameters
- [ ] 3.2.6 Show parameters for selected component
- [ ] 3.2.7 Handle multi-selection (common parameters)
- [ ] 3.2.8 Input validation with error display

### 3.3 Waveform Editors
- [ ] 3.3.1 Create DC source editor
- [ ] 3.3.2 Create pulse waveform editor with preview
- [ ] 3.3.3 Create sine waveform editor with preview
- [ ] 3.3.4 Create PWL editor with point table
- [ ] 3.3.5 Create PWM waveform editor

### 3.4 Device Library
- [ ] 3.4.1 Create device library dialog
- [ ] 3.4.2 Import Pulsim's pre-defined devices
- [ ] 3.4.3 Display device specifications
- [ ] 3.4.4 Apply device parameters to component

## Phase 4: Simulation Integration

### 4.1 Simulation Service
- [ ] 4.1.1 Create SimulationService class
- [ ] 4.1.2 Convert GUI circuit to Pulsim Circuit
- [ ] 4.1.3 Run simulation in worker thread
- [ ] 4.1.4 Emit progress signals during simulation
- [ ] 4.1.5 Handle simulation errors gracefully
- [ ] 4.1.6 Implement simulation cancellation

### 4.2 Simulation Control UI
- [ ] 4.2.1 Create simulation settings dialog
- [ ] 4.2.2 Implement transient settings tab
- [ ] 4.2.3 Implement solver settings tab
- [ ] 4.2.4 Add Run button to toolbar
- [ ] 4.2.5 Add Stop button to toolbar
- [ ] 4.2.6 Implement Pause/Resume
- [ ] 4.2.7 Show progress bar during simulation
- [ ] 4.2.8 Display simulation statistics after completion

### 4.3 DC Analysis
- [ ] 4.3.1 Implement DC operating point analysis
- [ ] 4.3.2 Display DC results in table
- [ ] 4.3.3 Show DC values on schematic (optional overlay)

### 4.4 AC Analysis
- [ ] 4.4.1 Implement AC analysis settings
- [ ] 4.4.2 Run AC sweep
- [ ] 4.4.3 Display Bode plots

## Phase 5: Waveform Viewer

### 5.1 Basic Plotting
- [ ] 5.1.1 Create WaveformViewer widget
- [ ] 5.1.2 Integrate PyQtGraph PlotWidget
- [ ] 5.1.3 Display simulation time on X axis
- [ ] 5.1.4 Display signal value on Y axis
- [ ] 5.1.5 Add signal to plot from result
- [ ] 5.1.6 Support multiple traces with colors
- [ ] 5.1.7 Implement legend

### 5.2 Navigation
- [ ] 5.2.1 Implement zoom with scroll wheel
- [ ] 5.2.2 Implement pan with drag
- [ ] 5.2.3 Implement zoom rectangle
- [ ] 5.2.4 Implement zoom to fit
- [ ] 5.2.5 Implement zoom history (back/forward)

### 5.3 Cursors and Measurements
- [ ] 5.3.1 Implement cursor placement
- [ ] 5.3.2 Implement two-cursor measurement
- [ ] 5.3.3 Display delta time and values
- [ ] 5.3.4 Implement cursor drag
- [ ] 5.3.5 Create measurements panel
- [ ] 5.3.6 Implement min/max/mean/RMS measurements

### 5.4 Real-time Streaming
- [ ] 5.4.1 Update plot during simulation
- [ ] 5.4.2 Implement auto-scroll mode
- [ ] 5.4.3 Implement data decimation for display

### 5.5 Signal List
- [ ] 5.5.1 Create signal list panel
- [ ] 5.5.2 Show all available signals
- [ ] 5.5.3 Drag signal to add to plot
- [ ] 5.5.4 Toggle signal visibility

## Phase 6: Project Management

### 6.1 File Operations
- [ ] 6.1.1 Implement Save Project (Ctrl+S)
- [ ] 6.1.2 Implement Save As (Ctrl+Shift+S)
- [ ] 6.1.3 Implement Open Project (Ctrl+O)
- [ ] 6.1.4 Implement New Project (Ctrl+N)
- [ ] 6.1.5 Implement Close Project
- [ ] 6.1.6 Track unsaved changes
- [ ] 6.1.7 Prompt to save on close

### 6.2 Recent Files
- [ ] 6.2.1 Track recently opened projects
- [ ] 6.2.2 Display in File menu
- [ ] 6.2.3 Persist recent files list

### 6.3 Auto-Save
- [ ] 6.3.1 Implement auto-save timer
- [ ] 6.3.2 Save backup copies
- [ ] 6.3.3 Add auto-save settings

### 6.4 Import/Export
- [ ] 6.4.1 Export to SPICE netlist
- [ ] 6.4.2 Export to JSON netlist (Pulsim format)
- [ ] 6.4.3 Export schematic as PNG/SVG
- [ ] 6.4.4 Export waveforms as CSV

## Phase 7: Polish and Distribution

### 7.1 User Experience
- [ ] 7.1.1 Refine keyboard shortcuts
- [ ] 7.1.2 Add keyboard shortcut customization
- [ ] 7.1.3 Improve error messages
- [ ] 7.1.4 Add loading indicators
- [ ] 7.1.5 Implement crash recovery

### 7.2 Templates
- [ ] 7.2.1 Create buck converter template
- [ ] 7.2.2 Create boost converter template
- [ ] 7.2.3 Create full-bridge template
- [ ] 7.2.4 Implement "New from Template" dialog

### 7.3 Packaging
- [ ] 7.3.1 Configure PyInstaller for Windows
- [ ] 7.3.2 Configure PyInstaller for macOS
- [ ] 7.3.3 Configure PyInstaller for Linux (AppImage)
- [ ] 7.3.4 Create Windows installer (NSIS)
- [ ] 7.3.5 Create macOS DMG
- [ ] 7.3.6 Set up release automation

### 7.4 Documentation
- [ ] 7.4.1 Write user manual
- [ ] 7.4.2 Create tutorial videos
- [ ] 7.4.3 Write developer documentation
- [ ] 7.4.4 Create example projects

## Phase 8: Advanced Features (Post-MVP)

### 8.1 Hierarchical Schematics
- [ ] 8.1.1 Create subcircuit from selection
- [ ] 8.1.2 Navigate into subcircuits
- [ ] 8.1.3 Breadcrumb navigation

### 8.2 Parameter Sweeps
- [ ] 8.2.1 Parameter sweep configuration dialog
- [ ] 8.2.2 Run parallel sweeps
- [ ] 8.2.3 Display sweep results

### 8.3 Thermal Viewer
- [ ] 8.3.1 Display thermal network
- [ ] 8.3.2 Show temperature vs time
- [ ] 8.3.3 Loss breakdown charts

### 8.4 Control Blocks
- [ ] 8.4.1 Add PI controller symbol
- [ ] 8.4.2 Add PID controller symbol
- [ ] 8.4.3 Add math block symbols
- [ ] 8.4.4 Add PWM generator symbol
