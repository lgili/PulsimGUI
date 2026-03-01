# Project Context

## Purpose
PulsimGui is a cross-platform graphical user interface for the Pulsim power electronics circuit simulator. The goal is to provide an intuitive, professional-grade schematic editor and simulation environment similar to PLECS, but open-source and with improved usability.

**Core Goals:**
- Intuitive schematic editor with drag-and-drop components
- Real-time waveform visualization during simulation
- Seamless integration with Pulsim core simulation engine
- Cross-platform support: Windows, macOS, Linux
- Modern, responsive UI with excellent user experience
- Open-source and community-driven development

## Tech Stack

### Frontend (UI Layer)
- **Framework**: Qt 6.x with PySide6 (Python bindings)
- **Language**: Python 3.10+ with type hints
- **Graphics**: Qt Graphics View Framework for schematic editor
- **Plotting**: PyQtGraph for high-performance waveform display
- **Styling**: Qt Style Sheets (QSS) with custom theme support

### Backend Integration
- **Simulation Engine**: Pulsim core (C++ library via pybind11)
- **File Format**: JSON for schematics and projects
- **Configuration**: TOML for user preferences
- **Logging**: Python logging with structured output

### Build & Distribution
- **Packaging**: PyInstaller / cx_Freeze for standalone executables
- **Installer**: NSIS (Windows), DMG (macOS), AppImage (Linux)
- **CI/CD**: GitHub Actions for automated builds
- **Testing**: pytest with Qt test helpers

## Project Conventions

### Code Style
- Python: PEP 8, formatted with `black`, linted with `ruff`
- Type hints required for all public APIs
- Docstrings in Google format
- Max line length: 100 characters
- Naming: `snake_case` for functions/variables, `PascalCase` for classes

### Architecture Patterns
- **MVC/MVP**: Model-View-Presenter for main application windows
- **Command Pattern**: All user actions as undoable commands
- **Observer Pattern**: Signal/slot connections for UI updates
- **Factory Pattern**: Component creation and instantiation
- **Singleton**: Application-wide services (settings, theme manager)

### Directory Structure
```
pulsim-gui/
├── src/pulsimgui/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── app.py               # QApplication setup
│   ├── models/              # Data models (circuit, components)
│   ├── views/               # Qt widgets and windows
│   ├── presenters/          # Business logic / controllers
│   ├── commands/            # Undo/redo command classes
│   ├── services/            # Simulation, file I/O, etc.
│   ├── resources/           # Icons, themes, translations
│   └── utils/               # Helper functions
├── tests/
├── docs/
└── scripts/
```

### Testing Strategy
- Unit tests for models and business logic
- Integration tests for simulation workflows
- GUI tests using pytest-qt
- Minimum 80% code coverage for core modules
- Visual regression tests for schematic rendering

### Git Workflow
- Main branch: `main`
- Feature branches: `feature/<name>`
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- PRs require passing CI and code review

## Domain Context

### Circuit Simulation Concepts
- **Schematic**: Visual representation of an electrical circuit
- **Component**: Circuit element (resistor, capacitor, MOSFET, etc.)
- **Node**: Connection point between components
- **Wire**: Visual connection between component pins
- **Netlist**: Text representation of circuit topology
- **Simulation**: Time-domain or frequency-domain analysis

### Power Electronics Specifics
- **Switching devices**: MOSFETs, IGBTs, diodes with on/off states
- **PWM**: Pulse-width modulation for power control
- **Dead-time**: Protection delay between complementary switches
- **Losses**: Conduction and switching losses in semiconductors
- **Thermal**: Junction temperature modeling

### PLECS-Inspired Features
- Drag-and-drop component placement
- Scope-like waveform viewer with cursors and measurements
- Parameter sweep with automatic plotting
- Multi-domain simulation (electrical + thermal)
- Hierarchical schematics with subcircuits

## Important Constraints

### Technical
- Must work offline without internet connection
- Support circuits with 1000+ nodes
- Simulation results must stream in real-time
- Undo/redo for all user actions
- Auto-save and crash recovery

### Licensing
- GUI code: MIT License
- Must be compatible with Pulsim's license
- No GPL-only dependencies (LGPL allowed)
- Qt: LGPL usage (dynamic linking)

### Performance
- Schematic editing at 60 FPS even with large circuits
- Waveform display update during simulation
- Application startup under 3 seconds
- Memory usage under 500MB for typical circuits

## External Dependencies

### Required
- **Pulsim**: Core simulation engine (MIT License)
- **Qt 6 / PySide6**: GUI framework (LGPL)
- **PyQtGraph**: Waveform plotting (MIT)
- **NumPy**: Numerical operations (BSD)

### Optional
- **SciPy**: Advanced signal processing (BSD)
- **Matplotlib**: Publication-quality plots (PSF)
- **HDF5/h5py**: Large result storage (BSD)
