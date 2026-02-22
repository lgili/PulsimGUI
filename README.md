# PulsimGui

Cross-platform GUI for the [Pulsim](https://github.com/lgili/pulsimcore) power electronics simulator.

## Features

- **Schematic Editor**: Drag-and-drop circuit design with component rotation and wire routing
- **Component Library**: Hierarchical library with power electronics components (MOSFETs, IGBTs, diodes, etc.)
- **Waveform Viewer**: Interactive oscilloscope-like display with cursors and measurements
- **Simulation Control**: Run transient, DC, and AC analysis with real-time progress
- **Project Management**: Save/load projects with auto-save and backup

## Prerequisites

Before installing PulsimGui, you need to install some system dependencies required by PySide6 (Qt6).

### macOS

```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python 3.10+ (if not already installed)
brew install python@3.12

# Install Qt6 dependencies (optional, PySide6 includes Qt binaries)
brew install qt6
```

### Windows

1. **Install Python 3.10+**
   - Download from [python.org](https://www.python.org/downloads/windows/)
   - During installation, check "Add Python to PATH"
   - Check "Install pip"

2. **Install Visual C++ Redistributable** (required for PySide6)
   - Download and install [Microsoft Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe)

3. **Optional: Install Git**
   - Download from [git-scm.com](https://git-scm.com/download/win)

### Linux (Ubuntu/Debian)

```bash
# Update package list
sudo apt update

# Install Python 3.10+ and pip
sudo apt install python3 python3-pip python3-venv

# Install Qt6 dependencies required by PySide6
sudo apt install -y \
    libgl1-mesa-glx \
    libegl1-mesa \
    libxkbcommon0 \
    libxcb-xinerama0 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxcb-xinput0 \
    libfontconfig1 \
    libfreetype6 \
    libx11-xcb1 \
    libdbus-1-3

# For OpenGL support (required for some visualizations)
sudo apt install -y libgl1-mesa-dev
```

### Linux (Fedora/RHEL/CentOS)

```bash
# Install Python 3.10+ and pip
sudo dnf install python3 python3-pip

# Install Qt6 dependencies
sudo dnf install -y \
    mesa-libGL \
    mesa-libEGL \
    libxkbcommon \
    xcb-util-wm \
    xcb-util-image \
    xcb-util-keysyms \
    xcb-util-renderutil \
    xcb-util-cursor \
    fontconfig \
    freetype \
    dbus-libs
```

### Linux (Arch Linux)

```bash
# Install Python and pip
sudo pacman -S python python-pip

# Install Qt6 dependencies
sudo pacman -S \
    qt6-base \
    libxcb \
    xcb-util-wm \
    xcb-util-image \
    xcb-util-keysyms \
    xcb-util-renderutil \
    xcb-util-cursor
```

## Installation

### Option 1: Install from PyPI (Recommended)

```bash
pip install pulsimgui
```

### Option 2: Install from Source

```bash
# Clone the repository
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui

# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows (Command Prompt):
.venv\Scripts\activate.bat
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# Install in development mode
pip install -e ".[dev]"
```

### Option 3: Install from GitHub directly

```bash
pip install git+https://github.com/lgili/PulsimGui.git
```

## Running the Application

After installation, run PulsimGui with:

```bash
pulsimgui
```

Or as a Python module:

```bash
python -m pulsimgui
```

## Documentation Website

The project now includes a MkDocs Material site for user-facing documentation.

- GitHub Pages deploy runs automatically when pushing a version tag (`v*`).
- Local docs build:

```bash
python3 -m pip install -r docs/requirements.txt
mkdocs serve
```

Static build:

```bash
mkdocs build --strict
```

## Troubleshooting

### PySide6 Import Errors

If you get errors importing PySide6, ensure you have all Qt6 dependencies installed (see Prerequisites above).

**Linux specific**: If you see `libGL` or `libEGL` errors:
```bash
# Ubuntu/Debian
sudo apt install libgl1-mesa-glx libegl1-mesa

# Fedora
sudo dnf install mesa-libGL mesa-libEGL
```

### XCB Plugin Errors (Linux)

If you see `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`:
```bash
# Install missing xcb libraries
sudo apt install libxcb-xinerama0 libxcb-cursor0
```

### Display Issues on Linux

If running on a headless server or via SSH, set the display:
```bash
export QT_QPA_PLATFORM=offscreen  # For headless
# or
export DISPLAY=:0  # If X server is available
```

### Windows: Missing DLLs

If you get DLL errors on Windows, install the Visual C++ Redistributable:
- Download: https://aka.ms/vs/17/release/vc_redist.x64.exe

## Python Dependencies

PulsimGui requires:

| Package | Version | Description |
|---------|---------|-------------|
| Python | >= 3.10 | Programming language |
| PySide6 | >= 6.5.0 | Qt6 bindings for Python |
| pyqtgraph | >= 0.13.0 | Scientific graphics library |
| numpy | >= 1.24.0 | Numerical computing |
| qtawesome | >= 1.3.0 | Icon fonts for Qt |
| pulsim | >= 0.1.11 | Power electronics simulation engine |

## Development

### Running Tests

```bash
pytest
```

### Code Formatting

```bash
black src tests
ruff check src tests
```

### Building Standalone Executables

```bash
# Install build dependencies
pip install -e ".[build]"

# Build with PyInstaller
pyinstaller --name PulsimGui --windowed src/pulsimgui/__main__.py
```

### Project Structure

```
PulsimGui/
├── src/pulsimgui/
│   ├── models/          # Data models (Component, Wire, Circuit, Project)
│   ├── views/           # Qt widgets and UI components
│   ├── presenters/      # Business logic (MVP pattern)
│   ├── commands/        # Undo/redo command system
│   ├── services/        # Application services
│   └── utils/           # Utilities (SI prefix parsing, etc.)
├── tests/               # Unit tests
└── openspec/            # Specifications and requirements
```

## License

MIT License - see LICENSE file for details.

## Author

Luiz Gili (luizcarlosgili@gmail.com)
