# Application Architecture Design

## Context

PulsimGui is a cross-platform GUI for the Pulsim power electronics simulator. The application must:
- Run on Windows, macOS, and Linux
- Provide a professional schematic editor similar to PLECS
- Display real-time waveforms during simulation
- Be open-source with permissive licensing
- Maintain high performance for large circuits

## Framework Decision: Qt 6 with PySide6

### Decision
Use **Qt 6 with PySide6** (Python bindings) as the GUI framework.

### Alternatives Considered

| Framework | Pros | Cons |
|-----------|------|------|
| **Qt/PySide6** | Native performance, mature ecosystem, excellent graphics support, LGPL license, Python integration | Larger binary size (~80MB), learning curve for Qt patterns |
| **Tauri** | Tiny binaries (~3MB), modern web stack, Rust backend | WebView inconsistencies across platforms, Rust learning curve, limited native graphics |
| **Electron** | Large ecosystem, easy web development | Huge memory footprint (200-400MB), large binaries (~85MB), sluggish performance |
| **Qt/C++** | Best performance, smallest binary | Slower development, harder maintenance, C++ complexity |
| **wxPython** | Free, native look | Fewer features, less modern, smaller community |

### Rationale

1. **Python + Pulsim Integration**: Pulsim already has excellent pybind11 bindings. Using Python for the GUI allows seamless integration without IPC overhead.

2. **Performance**: Qt's native rendering is essential for:
   - Smooth schematic editing at 60 FPS
   - Real-time waveform updates
   - Responsive UI with 1000+ components

3. **Graphics Capabilities**: Qt Graphics View Framework provides:
   - Hardware-accelerated rendering
   - Scene graph for complex schematics
   - Efficient culling and caching

4. **Cross-Platform**: Qt 6 provides consistent experience on all platforms without WebView inconsistencies.

5. **Licensing**: LGPL allows commercial use when dynamically linked. MIT license for our code.

6. **Ecosystem**: Qt has battle-tested widgets for:
   - Dockable panels
   - Property editors
   - Tree views
   - Plotting (PyQtGraph integration)

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PulsimGui Application                       │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │   Views     │  │ Presenters  │  │        Models           │ │
│  │  (Qt Widgets│  │  (Business  │  │    (Data Objects)       │ │
│  │   & QML)    │  │   Logic)    │  │                         │ │
│  └──────┬──────┘  └──────┬──────┘  └───────────┬─────────────┘ │
│         │                │                      │               │
│         │    Signals/Slots (Qt)                │               │
│         ▼                ▼                      ▼               │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    Service Layer                            ││
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   ││
│  │  │Simulation│ │  File    │ │  Undo    │ │   Settings   │   ││
│  │  │ Service  │ │  Service │ │  Stack   │ │   Service    │   ││
│  │  └────┬─────┘ └──────────┘ └──────────┘ └──────────────┘   ││
│  └───────┼─────────────────────────────────────────────────────┘│
│          │                                                       │
│          ▼                                                       │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                  Pulsim Python Bindings                      ││
│  │           (pulsim module via pybind11)                       ││
│  └─────────────────────────────────────────────────────────────┘│
├─────────────────────────────────────────────────────────────────┤
│                     Pulsim Core (C++)                            │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │  Circuit │ │   MNA    │ │  Solver  │ │   Device Models  │   │
│  │  Parser  │ │Assembler │ │ (Newton) │ │ (MOSFET, Diode)  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Design Patterns

### Model-View-Presenter (MVP)

Each major feature follows MVP to separate concerns:

```python
# Model - Data structure
class CircuitModel:
    components: List[Component]
    wires: List[Wire]
    nodes: Dict[str, Node]

# View - Qt Widget
class SchematicView(QGraphicsView):
    component_clicked = Signal(str)
    wire_drawn = Signal(str, str)

    def display_circuit(self, circuit: CircuitModel): ...
    def highlight_component(self, name: str): ...

# Presenter - Logic
class SchematicPresenter:
    def __init__(self, view: SchematicView, model: CircuitModel):
        self.view = view
        self.model = model
        self.view.component_clicked.connect(self.on_component_clicked)

    def on_component_clicked(self, name: str):
        component = self.model.get_component(name)
        self.view.highlight_component(name)
        self.properties_presenter.show(component)
```

### Command Pattern for Undo/Redo

All user actions are commands:

```python
class Command(ABC):
    @abstractmethod
    def execute(self) -> None: ...

    @abstractmethod
    def undo(self) -> None: ...

    @property
    @abstractmethod
    def description(self) -> str: ...

class AddComponentCommand(Command):
    def __init__(self, circuit: CircuitModel, component: Component):
        self.circuit = circuit
        self.component = component

    def execute(self):
        self.circuit.add_component(self.component)

    def undo(self):
        self.circuit.remove_component(self.component.name)

    @property
    def description(self) -> str:
        return f"Add {self.component.name}"

class CommandStack:
    def execute(self, command: Command): ...
    def undo(self): ...
    def redo(self): ...
```

### Observer Pattern with Qt Signals

Use Qt signals for loose coupling:

```python
class SimulationService(QObject):
    progress_updated = Signal(float, float)  # current_time, total_time
    simulation_completed = Signal(SimulationResult)
    simulation_error = Signal(str)

    def run_simulation(self, circuit: CircuitModel, options: SimulationOptions):
        # Run in thread, emit signals
        ...
```

## Key Components Design

### Schematic Editor

Uses Qt Graphics View Framework:

```
QGraphicsView (SchematicView)
    └── QGraphicsScene (SchematicScene)
            ├── ComponentItem (QGraphicsItem)
            │       ├── Symbol rendering
            │       ├── Pin positions
            │       └── Label items
            ├── WireItem (QGraphicsPathItem)
            │       ├── Orthogonal path
            │       └── Junction handling
            └── ProbeItem (QGraphicsItem)
```

### Waveform Viewer

Uses PyQtGraph for high-performance plotting:

```
WaveformViewer (QWidget)
    ├── PlotWidget (pyqtgraph.PlotWidget)
    │       ├── PlotDataItem per signal
    │       ├── InfiniteLine (cursors)
    │       └── LegendItem
    ├── SignalList (QListWidget)
    └── MeasurementPanel (QWidget)
```

### Component Library

```
LibraryPanel (QWidget)
    ├── SearchBox (QLineEdit)
    └── LibraryTree (QTreeWidget)
            ├── Category nodes
            └── Component items (draggable)
```

## Threading Model

```
┌─────────────────────────────────────────────────────────────┐
│                     Main Thread (Qt Event Loop)              │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐│
│  │   UI    │  │ Events  │  │ Signals │  │  Light Updates  ││
│  │ Render  │  │ Handle  │  │ Process │  │  (< 16ms)       ││
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘│
└────────────────────────────┬────────────────────────────────┘
                             │ Signals/Slots
                             ▼
┌─────────────────────────────────────────────────────────────┐
│                     Worker Threads (QThread)                 │
│  ┌─────────────────┐  ┌─────────────────┐                   │
│  │ Simulation      │  │ File I/O        │                   │
│  │ Worker          │  │ Worker          │                   │
│  │ (pulsim.run)    │  │ (load/save)     │                   │
│  └─────────────────┘  └─────────────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

Key threading rules:
1. **Never block main thread** - All simulation runs in workers
2. **Signals for cross-thread communication** - Qt handles thread safety
3. **Result streaming** - Emit partial results during simulation
4. **Graceful cancellation** - Workers check stop flag periodically

## File Format Design

### Project File (.pulsim)

```json
{
  "version": "1.0",
  "name": "Buck Converter",
  "created": "2024-01-15T10:30:00Z",
  "modified": "2024-01-15T14:22:00Z",
  "schematics": [
    {"name": "main", "file": "schematics/main.sch"}
  ],
  "simulations": [
    {"name": "default", "file": "simulations/default.sim"}
  ],
  "settings": {
    "default_simulation": "default"
  }
}
```

### Schematic File (.sch)

```json
{
  "version": "1.0",
  "components": [
    {
      "name": "R1",
      "type": "resistor",
      "position": {"x": 100, "y": 200},
      "orientation": 0,
      "parameters": {
        "resistance": "10k"
      }
    }
  ],
  "wires": [
    {
      "points": [[100, 200], [100, 300], [200, 300]],
      "start_pin": {"component": "R1", "pin": 0},
      "end_pin": {"component": "C1", "pin": 0}
    }
  ],
  "probes": [
    {
      "name": "Vout",
      "node": "out",
      "position": {"x": 250, "y": 200}
    }
  ],
  "viewport": {
    "center": [150, 250],
    "zoom": 1.0
  }
}
```

## Performance Considerations

### Schematic Rendering
- Use QGraphicsScene item caching
- Implement level-of-detail for zoomed-out views
- Batch paint operations
- Cull off-screen items

### Waveform Display
- Decimate data for display (1000 points max visible)
- Use OpenGL backend in PyQtGraph
- Implement data chunking for very long simulations
- Background thread for FFT computation

### Memory Management
- Lazy load result data
- Implement result file pagination for large datasets
- Use numpy arrays for efficient data storage
- Clear simulation results when closing project

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| PySide6 packaging complexity | Medium | Use PyInstaller with tested recipes; consider Nuitka |
| Qt learning curve | Medium | Provide code examples; follow Qt best practices |
| Performance with large circuits | High | Profile early; implement LOD; use caching |
| Cross-platform testing | Medium | CI/CD with matrix builds; virtual machines |
| Pulsim API limitations | Medium | Propose core changes; implement GUI-specific wrappers |

## Dependencies

### Required (bundled)
- PySide6 >= 6.5.0
- PyQtGraph >= 0.13.0
- NumPy >= 1.24.0
- pulsim (local build)

### Optional
- scipy (advanced analysis)
- h5py (HDF5 results)
- matplotlib (publication plots)

## Open Questions

1. **QML vs Widgets**: Should modern features use QML or stick with widgets?
   - *Recommendation*: Widgets for main UI, consider QML for animations

2. **Plugin System**: Should the app support third-party plugins?
   - *Recommendation*: Design for it but defer implementation

3. **Localization**: Support multiple languages from the start?
   - *Recommendation*: Use Qt i18n infrastructure, English-only initial release
