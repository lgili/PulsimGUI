# PulsimGui Developer Guide

This guide provides an overview of the PulsimGui architecture and codebase for developers who want to contribute or extend the application.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Project Structure](#project-structure)
3. [Core Concepts](#core-concepts)
4. [Data Models](#data-models)
5. [Command System](#command-system)
6. [Views and Widgets](#views-and-widgets)
7. [Services](#services)
8. [Adding New Components](#adding-new-components)
9. [Testing](#testing)
10. [Building and Packaging](#building-and-packaging)

---

## Architecture Overview

PulsimGui follows a Model-View architecture with a Command pattern for undo/redo support:

```
┌─────────────────────────────────────────────────────────────┐
│                        MainWindow                            │
│  ┌─────────┐  ┌──────────────────┐  ┌──────────────────┐   │
│  │ Library │  │  SchematicView   │  │  PropertiesPanel │   │
│  │  Panel  │  │  ┌────────────┐  │  │                  │   │
│  │         │  │  │  Scene     │  │  │                  │   │
│  │         │  │  │            │  │  │                  │   │
│  └─────────┘  │  └────────────┘  │  └──────────────────┘   │
│               └──────────────────┘                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │                 WaveformViewer                        │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         CommandStack          │
              │    (Undo/Redo Management)     │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │         Data Models           │
              │  Project → Circuit → Components│
              │                    → Wires     │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │      SimulationService        │
              │    (Worker Thread)            │
              └───────────────────────────────┘
```

### Key Design Principles

1. **Separation of Concerns**: Data models are independent of UI representation
2. **Command Pattern**: All state mutations go through commands for undo/redo
3. **Signal/Slot Communication**: Qt signals for loose coupling between components
4. **Worker Threads**: Long-running operations (simulation) run in background threads

---

## Project Structure

```
PulsimGui/
├── src/pulsimgui/
│   ├── __init__.py
│   ├── __main__.py           # Application entry point
│   ├── models/               # Data models
│   │   ├── __init__.py
│   │   ├── component.py      # Component model
│   │   ├── wire.py           # Wire model
│   │   ├── circuit.py        # Circuit container
│   │   └── project.py        # Project container
│   ├── views/                # UI components
│   │   ├── __init__.py
│   │   ├── main_window.py    # Main application window
│   │   ├── schematic/        # Schematic editor widgets
│   │   │   ├── scene.py      # QGraphicsScene
│   │   │   ├── view.py       # QGraphicsView
│   │   │   ├── component_item.py  # Component graphics
│   │   │   └── wire_item.py  # Wire graphics
│   │   ├── panels/           # Dockable panels
│   │   │   ├── library_panel.py
│   │   │   ├── properties_panel.py
│   │   │   └── waveform_viewer.py
│   │   └── dialogs/          # Modal dialogs
│   │       ├── simulation_settings.py
│   │       ├── preferences_dialog.py
│   │       └── template_dialog.py
│   ├── commands/             # Undo/redo commands
│   │   ├── __init__.py
│   │   ├── base.py           # Command base class
│   │   ├── command_stack.py  # Undo/redo stack
│   │   └── component_commands.py
│   ├── services/             # Business logic
│   │   ├── __init__.py
│   │   ├── simulation_service.py
│   │   ├── export_service.py
│   │   └── template_service.py
│   └── resources/            # Icons, themes, etc.
│       └── themes/
├── tests/                    # Test suite
├── docs/                     # Documentation
├── packaging/                # Platform-specific packaging
└── examples/                 # Example projects
```

---

## Core Concepts

### Qt Framework

PulsimGui uses PySide6 (Qt 6 for Python). Key Qt concepts:

- **QApplication**: Main application instance
- **QMainWindow**: Main window with menus, toolbars, docks
- **QGraphicsScene/View**: 2D graphics framework for schematic
- **Signals/Slots**: Event-driven communication
- **QThread**: Background thread support

### Graphics System

The schematic editor uses Qt's Graphics View Framework:

- **SchematicScene** (`QGraphicsScene`): Contains all graphical items
- **SchematicView** (`QGraphicsView`): Viewport with pan/zoom
- **ComponentItem** (`QGraphicsItem`): Individual component graphics
- **WireItem** (`QGraphicsPathItem`): Wire connections

---

## Data Models

### Component Model

Located in `src/pulsimgui/models/component.py`:

```python
@dataclass
class Component:
    id: str                      # Unique identifier (UUID)
    type: ComponentType          # Enum: RESISTOR, CAPACITOR, etc.
    name: str                    # Display name (R1, C1, etc.)
    position: tuple[float, float]  # Position in scene coordinates
    rotation: int                # Rotation in degrees (0, 90, 180, 270)
    mirrored: bool              # Horizontal mirror
    parameters: dict            # Type-specific parameters

    def to_dict(self) -> dict:
        """Serialize to dictionary for JSON export."""

    @classmethod
    def from_dict(cls, data: dict) -> Component:
        """Deserialize from dictionary."""
```

### Wire Model

Located in `src/pulsimgui/models/wire.py`:

```python
@dataclass
class Wire:
    id: str
    points: list[tuple[float, float]]  # Routing points
    connections: list[Connection]       # Connected pins

@dataclass
class Connection:
    component_id: str
    pin_index: int
```

### Circuit Model

Located in `src/pulsimgui/models/circuit.py`:

```python
@dataclass
class Circuit:
    id: str
    name: str
    components: dict[str, Component]
    wires: dict[str, Wire]

    def add_component(self, component: Component) -> None
    def remove_component(self, component_id: str) -> None
    def add_wire(self, wire: Wire) -> None
    def remove_wire(self, wire_id: str) -> None
```

### Project Model

Located in `src/pulsimgui/models/project.py`:

```python
@dataclass
class Project:
    name: str
    path: Optional[Path]
    circuits: dict[str, Circuit]
    simulation_settings: SimulationSettings

    def save(self, path: Path) -> None
    @classmethod
    def load(cls, path: Path) -> Project
```

---

## Command System

All operations that modify state use the Command pattern for undo/redo.

### Command Base Class

```python
class Command(ABC):
    @abstractmethod
    def execute(self) -> None:
        """Execute the command."""

    @abstractmethod
    def undo(self) -> None:
        """Reverse the command."""

    @property
    def description(self) -> str:
        """Human-readable description for UI."""
```

### CommandStack

```python
class CommandStack:
    def push(self, command: Command) -> None:
        """Execute command and add to stack."""

    def undo(self) -> None:
        """Undo last command."""

    def redo(self) -> None:
        """Redo last undone command."""

    def can_undo(self) -> bool
    def can_redo(self) -> bool

    # Signals
    can_undo_changed: Signal
    can_redo_changed: Signal
```

### Example Command

```python
class AddComponentCommand(Command):
    def __init__(self, circuit: Circuit, component: Component):
        self._circuit = circuit
        self._component = component

    def execute(self) -> None:
        self._circuit.add_component(self._component)

    def undo(self) -> None:
        self._circuit.remove_component(self._component.id)

    @property
    def description(self) -> str:
        return f"Add {self._component.name}"
```

---

## Views and Widgets

### SchematicScene

The scene manages all graphical items:

```python
class SchematicScene(QGraphicsScene):
    # Signals
    component_added: Signal
    component_removed: Signal
    selection_changed: Signal

    def add_component_item(self, component: Component) -> ComponentItem
    def remove_component_item(self, component_id: str) -> None
    def get_component_at(self, pos: QPointF) -> Optional[ComponentItem]
```

### ComponentItem

Base class for all component graphics:

```python
class ComponentItem(QGraphicsItem):
    def __init__(self, component: Component):
        self._component = component

    @abstractmethod
    def paint(self, painter: QPainter, option, widget) -> None:
        """Draw the component symbol."""

    def get_pin_positions(self) -> list[QPointF]:
        """Return pin positions in scene coordinates."""
```

### Properties Panel

Dynamic property editing:

```python
class PropertiesPanel(QDockWidget):
    # Signal emitted when a property changes
    property_changed: Signal  # (component_id, property_name, new_value)

    def set_component(self, component: Optional[Component]) -> None:
        """Update panel to show component properties."""
```

---

## Services

### SimulationService

Runs simulations in a worker thread:

```python
class SimulationService(QObject):
    # Signals
    progress: Signal      # (percent: int, message: str)
    completed: Signal     # (results: SimulationResults)
    error: Signal         # (error_message: str)

    def run_transient(self, circuit: Circuit, settings: TransientSettings) -> None
    def run_dc_analysis(self, circuit: Circuit) -> None
    def run_ac_analysis(self, circuit: Circuit, settings: ACSettings) -> None
    def cancel(self) -> None
```

### ExportService

Handles various export formats:

```python
class ExportService:
    @staticmethod
    def to_spice_netlist(circuit: Circuit) -> str

    @staticmethod
    def to_json_netlist(circuit: Circuit) -> str

    @staticmethod
    def to_png(scene: SchematicScene, path: Path) -> None

    @staticmethod
    def to_svg(scene: SchematicScene, path: Path) -> None

    @staticmethod
    def waveforms_to_csv(results: SimulationResults, path: Path) -> None
```

---

## Adding New Components

### Step 1: Add Component Type

In `src/pulsimgui/models/component.py`:

```python
class ComponentType(Enum):
    # ... existing types
    MY_NEW_COMPONENT = "my_new_component"
```

### Step 2: Define Default Parameters

In component factory or component module:

```python
DEFAULT_PARAMETERS = {
    ComponentType.MY_NEW_COMPONENT: {
        "param1": 1.0,
        "param2": "default",
    },
}
```

### Step 3: Create Graphics Item

In `src/pulsimgui/views/schematic/component_items/`:

```python
class MyNewComponentItem(ComponentItem):
    def __init__(self, component: Component):
        super().__init__(component)
        self._pins = [
            QPointF(-30, 0),   # Pin 1
            QPointF(30, 0),    # Pin 2
        ]

    def boundingRect(self) -> QRectF:
        return QRectF(-40, -20, 80, 40)

    def paint(self, painter: QPainter, option, widget) -> None:
        # Draw component symbol
        painter.setPen(self._get_pen())
        # ... drawing code

    def get_pin_positions(self) -> list[QPointF]:
        return [self.mapToScene(p) for p in self._pins]
```

### Step 4: Register in Factory

In component item factory:

```python
def create_component_item(component: Component) -> ComponentItem:
    item_classes = {
        # ... existing mappings
        ComponentType.MY_NEW_COMPONENT: MyNewComponentItem,
    }
    return item_classes[component.type](component)
```

### Step 5: Add to Library Panel

In library panel configuration:

```python
LIBRARY_STRUCTURE = {
    "My Category": [
        ("My New Component", ComponentType.MY_NEW_COMPONENT, "M"),
    ],
}
```

### Step 6: Add Simulation Support

In simulation service, add conversion to Pulsim circuit format:

```python
def _convert_component(self, component: Component) -> PulsimComponent:
    if component.type == ComponentType.MY_NEW_COMPONENT:
        return MyPulsimComponent(**component.parameters)
```

---

## Testing

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/pulsimgui

# Run specific test file
pytest tests/test_models.py

# Run tests matching pattern
pytest -k "test_component"
```

### Test Structure

```python
# tests/test_models.py
import pytest
from pulsimgui.models import Component, ComponentType

class TestComponent:
    def test_create_resistor(self):
        comp = Component(
            id="test-id",
            type=ComponentType.RESISTOR,
            name="R1",
            position=(0, 0),
            rotation=0,
            mirrored=False,
            parameters={"resistance": 1000},
        )
        assert comp.name == "R1"
        assert comp.parameters["resistance"] == 1000

    def test_serialization(self):
        comp = Component(...)
        data = comp.to_dict()
        restored = Component.from_dict(data)
        assert comp == restored
```

### GUI Testing with pytest-qt

```python
# tests/test_main_window.py
import pytest
from pytestqt.qtbot import QtBot
from pulsimgui.views import MainWindow

@pytest.fixture
def main_window(qtbot: QtBot) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    return window

def test_new_project(main_window: MainWindow, qtbot: QtBot):
    # Trigger action
    main_window.action_new.trigger()

    # Verify state
    assert main_window._project is not None
```

---

## Building and Packaging

### Development Build

```bash
# Install in development mode
pip install -e ".[dev]"

# Run from source
pulsimgui
# or
python -m pulsimgui
```

### Creating Executables

```bash
# Install build dependencies
pip install -e ".[build]"

# Build with PyInstaller
python -m PyInstaller --clean --noconfirm pulsimgui.spec

# Output:
# - Windows: dist/PulsimGui.exe
# - macOS: dist/PulsimGui.app
# - Linux: dist/pulsimgui
```

### Platform-Specific Packaging

**Windows Installer (NSIS):**
```bash
makensis packaging/windows/installer.nsi
```

**macOS DMG:**
```bash
hdiutil create -volname "PulsimGui" -srcfolder dist/PulsimGui.app -ov -format UDZO PulsimGui.dmg
```

**Linux AppImage:**
```bash
# See packaging/linux/ for AppImage creation scripts
```

### Release Process

1. Update version in `pyproject.toml`
2. Update CHANGELOG.md
3. Create and push a version tag: `git tag v0.1.0 && git push origin v0.1.0`
4. GitHub Actions automatically builds and creates a release

---

## Debugging Tips

### Enable Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Qt Debugging

```python
# Print widget hierarchy
def print_widget_tree(widget, indent=0):
    print(" " * indent + widget.__class__.__name__)
    for child in widget.children():
        if isinstance(child, QWidget):
            print_widget_tree(child, indent + 2)
```

### Graphics Scene Debugging

```python
# Enable bounding rect visualization
scene.setItemIndexMethod(QGraphicsScene.NoIndex)
for item in scene.items():
    item.setFlag(QGraphicsItem.ItemClipsToShape, False)
```

---

## Code Style

PulsimGui follows these style guidelines:

- **Formatter**: Black (line length 100)
- **Linter**: Ruff
- **Type Hints**: Required for public APIs
- **Docstrings**: Google style

Run formatting and linting:

```bash
# Format code
black src/ tests/

# Lint
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/
```

---

## Resources

- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/)
- [Qt Graphics View Framework](https://doc.qt.io/qt-6/graphicsview.html)
- [PyQtGraph Documentation](https://pyqtgraph.readthedocs.io/)
- [Python Packaging Guide](https://packaging.python.org/)
