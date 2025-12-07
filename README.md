# PulsimGui

Cross-platform GUI for the [Pulsim](https://github.com/lgili/pulsimcore) power electronics simulator.

## Features

- **Schematic Editor**: Drag-and-drop circuit design with component rotation and wire routing
- **Component Library**: Hierarchical library with power electronics components (MOSFETs, IGBTs, diodes, etc.)
- **Waveform Viewer**: Interactive oscilloscope-like display with cursors and measurements
- **Simulation Control**: Run transient, DC, and AC analysis with real-time progress
- **Project Management**: Save/load projects with auto-save and backup

## Installation

### From Source

```bash
# Clone the repository
git clone https://github.com/lgili/PulsimGui.git
cd PulsimGui

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run the application
pulsimgui
```

### Requirements

- Python 3.10 or later
- PySide6 >= 6.5.0
- PyQtGraph >= 0.13.0
- NumPy >= 1.24.0

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
