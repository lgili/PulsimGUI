# Implementation Design

## Context

This document captures technical design decisions for the initial PulsimGui implementation. See `openspec/specs/application-shell/design.md` for the high-level architecture.

## Goals

- Deliver a usable MVP within a reasonable timeframe
- Establish solid foundations for future extensions
- Ensure maintainable, testable code

## Non-Goals

- Complete feature parity with PLECS (deferred to later phases)
- Plugin system (deferred)
- Web-based deployment (out of scope)

## Key Technical Decisions

### 1. Project Structure

```
pulsim-gui/
├── pyproject.toml          # Project configuration (PEP 621)
├── src/
│   └── pulsimgui/
│       ├── __init__.py
│       ├── __main__.py     # Entry point
│       ├── app.py          # QApplication setup
│       ├── version.py      # Version info
│       │
│       ├── models/         # Data models
│       │   ├── __init__.py
│       │   ├── component.py
│       │   ├── wire.py
│       │   ├── circuit.py
│       │   └── project.py
│       │
│       ├── views/          # Qt widgets
│       │   ├── __init__.py
│       │   ├── main_window.py
│       │   ├── schematic/
│       │   │   ├── scene.py
│       │   │   ├── view.py
│       │   │   └── items/
│       │   ├── library/
│       │   ├── properties/
│       │   ├── waveform/
│       │   └── dialogs/
│       │
│       ├── presenters/     # Business logic
│       │   ├── __init__.py
│       │   ├── schematic_presenter.py
│       │   ├── simulation_presenter.py
│       │   └── project_presenter.py
│       │
│       ├── commands/       # Undo/redo commands
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── component_commands.py
│       │   └── wire_commands.py
│       │
│       ├── services/       # Application services
│       │   ├── __init__.py
│       │   ├── simulation_service.py
│       │   ├── file_service.py
│       │   └── settings_service.py
│       │
│       ├── resources/      # Assets
│       │   ├── icons/
│       │   ├── themes/
│       │   └── symbols/
│       │
│       └── utils/          # Utilities
│           ├── __init__.py
│           ├── si_prefix.py
│           └── geometry.py
│
├── tests/
│   ├── conftest.py
│   ├── test_models/
│   ├── test_commands/
│   └── test_services/
│
├── resources/
│   └── pulsimgui.qrc       # Qt resource file
│
└── scripts/
    ├── build.py
    └── package.py
```

### 2. Component Symbol Rendering

Strategy: Programmatic SVG-like rendering with QPainter

```python
class ComponentItem(QGraphicsItem):
    def __init__(self, component: Component):
        super().__init__()
        self.component = component
        self.symbol = get_symbol(component.type)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setFlag(QGraphicsItem.ItemIsSelectable)

    def boundingRect(self) -> QRectF:
        return self.symbol.bounding_rect()

    def paint(self, painter: QPainter, option, widget):
        self.symbol.render(painter, self.component)
        if self.isSelected():
            self._draw_selection_highlight(painter)

    def _draw_pins(self, painter: QPainter):
        for pin in self.symbol.pins:
            # Draw pin marker (small circle)
            painter.drawEllipse(pin.position, 3, 3)
```

Symbol definitions stored in code (not external SVG files) for:
- Easier customization
- Better integration with Qt styling
- No external file dependencies

### 3. Wire Routing Algorithm

Simple orthogonal router (initial implementation):

```python
def calculate_orthogonal_path(start: QPointF, end: QPointF) -> QPainterPath:
    """Create an L-shaped or Z-shaped path between two points."""
    path = QPainterPath(start)

    dx = end.x() - start.x()
    dy = end.y() - start.y()

    # Determine routing direction based on pin orientations
    if abs(dx) > abs(dy):
        # Horizontal first
        mid_x = start.x() + dx / 2
        path.lineTo(mid_x, start.y())
        path.lineTo(mid_x, end.y())
        path.lineTo(end)
    else:
        # Vertical first
        mid_y = start.y() + dy / 2
        path.lineTo(start.x(), mid_y)
        path.lineTo(end.x(), mid_y)
        path.lineTo(end)

    return path
```

Future enhancement: A* based auto-router for obstacle avoidance.

### 4. Pulsim Integration

Circuit conversion layer:

```python
class CircuitConverter:
    """Convert GUI CircuitModel to Pulsim Circuit."""

    def to_pulsim(self, model: CircuitModel) -> pulsim.Circuit:
        circuit = pulsim.Circuit()

        for comp in model.components:
            self._add_component(circuit, comp)

        return circuit

    def _add_component(self, circuit: pulsim.Circuit, comp: Component):
        match comp.type:
            case ComponentType.RESISTOR:
                circuit.add_resistor(
                    comp.name,
                    comp.connections[0],
                    comp.connections[1],
                    comp.parameters['resistance']
                )
            case ComponentType.MOSFET:
                params = pulsim.MOSFETParams()
                params.type = pulsim.MOSFETType.NMOS
                params.vth = comp.parameters.get('vth', 2.0)
                # ... more parameters
                circuit.add_mosfet(
                    comp.name,
                    comp.connections[0],  # drain
                    comp.connections[1],  # gate
                    comp.connections[2],  # source
                    params
                )
```

### 5. Settings Persistence

Use QSettings for cross-platform settings:

```python
class SettingsService:
    def __init__(self):
        self.settings = QSettings("Pulsim", "PulsimGui")

    def get_recent_projects(self) -> List[str]:
        return self.settings.value("recent_projects", [])

    def add_recent_project(self, path: str):
        recent = self.get_recent_projects()
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]  # Keep last 10
        self.settings.setValue("recent_projects", recent)

    def get_theme(self) -> str:
        return self.settings.value("theme", "system")

    def set_theme(self, theme: str):
        self.settings.setValue("theme", theme)
```

### 6. Threading for Simulation

```python
class SimulationWorker(QObject):
    progress = Signal(float, float, int)  # time, total, newton_iters
    finished = Signal(SimulationResult)
    error = Signal(str)

    def __init__(self, circuit: pulsim.Circuit, options: pulsim.SimulationOptions):
        super().__init__()
        self.circuit = circuit
        self.options = options
        self._stop_requested = False

    def run(self):
        try:
            simulator = pulsim.Simulator(self.circuit, self.options)

            def callback(time, state):
                if self._stop_requested:
                    return False  # Signal to stop
                self.progress.emit(time, self.options.tstop, 0)
                return True

            result = simulator.run_transient_with_callback(callback)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))

    def request_stop(self):
        self._stop_requested = True


class SimulationService(QObject):
    progress_updated = Signal(float, float, int)
    simulation_completed = Signal(object)
    simulation_error = Signal(str)

    def run(self, circuit: pulsim.Circuit, options: pulsim.SimulationOptions):
        self.thread = QThread()
        self.worker = SimulationWorker(circuit, options)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self.progress_updated)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self.simulation_error)

        self.thread.start()

    def stop(self):
        if hasattr(self, 'worker'):
            self.worker.request_stop()

    def _on_finished(self, result):
        self.simulation_completed.emit(result)
        self.thread.quit()
        self.thread.wait()
```

## Migration Plan

N/A - Greenfield project.

## Risks and Trade-offs

| Decision | Trade-off | Mitigation |
|----------|-----------|------------|
| Python for GUI | Slower than C++ Qt | Bottlenecks are in C++ Pulsim; Python is fast enough for UI |
| Programmatic symbols | More code than SVG files | Better control, no I/O, easier theming |
| Simple wire router | May produce suboptimal routes | Good enough for MVP; improve later |
| QSettings for config | Platform-specific storage | Cross-platform abstraction; portable export option |

## Open Questions

1. Should we support saving results alongside project?
   - Decision: Yes, optional. Results folder in project directory.

2. How to handle very long simulations (hours)?
   - Decision: Implement result decimation and streaming. Allow background run.

3. Support for multiple monitors?
   - Decision: Standard Qt behavior. Test docking across monitors.
