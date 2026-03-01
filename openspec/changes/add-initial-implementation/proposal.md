## Why

This proposal defines the initial implementation of PulsimGui, a cross-platform graphical user interface for the Pulsim power electronics simulator. The goal is to create an open-source alternative to commercial tools like PLECS with excellent usability and performance.

## What Changes

This is a greenfield implementation. Key deliverables:

1. **Application Shell**
   - Main window with dockable panels
   - Menu bar, toolbar, and status bar
   - Theme support (light/dark)
   - Preferences system

2. **Schematic Editor**
   - Canvas with pan/zoom
   - Grid system with snap
   - Component placement and rotation
   - Wire routing (orthogonal)
   - Undo/redo support

3. **Component Library**
   - Hierarchical component browser
   - Search functionality
   - Drag-and-drop placement
   - Favorites and recent items

4. **Properties Panel**
   - Parameter editing with validation
   - SI prefix support
   - Waveform editors for sources

5. **Waveform Viewer**
   - Multi-trace plotting
   - Interactive cursors
   - Measurements
   - Real-time streaming during simulation

6. **Simulation Control**
   - Run/stop/pause controls
   - Progress feedback
   - DC/AC/Transient analysis
   - Parameter sweeps

7. **Project Management**
   - File save/load
   - Auto-save and backup
   - SPICE import/export

## Impact

- New project: PulsimGui
- Depends on: Pulsim core library
- Framework: Qt 6 / PySide6
- Target platforms: Windows, macOS, Linux
