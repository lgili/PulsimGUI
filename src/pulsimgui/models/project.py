"""Project model for managing multiple schematics and settings."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.subcircuit import SubcircuitDefinition


@dataclass
class SimulationSettings:
    """Settings for transient simulation."""

    tstop: float = 1e-3
    dt: float = 1e-6
    max_step: float = 1e-6
    tstart: float = 0.0
    abstol: float = 1e-12
    reltol: float = 1e-3
    solver: str = "auto"
    step_mode: str = "fixed"
    output_points: int = 10000
    enable_events: bool = True
    max_step_retries: int = 8
    max_iterations: int = 50
    enable_voltage_limiting: bool = False
    max_voltage_step: float = 5.0
    dc_strategy: str = "auto"
    gmin_initial: float = 1e-3
    gmin_final: float = 1e-12
    dc_source_steps: int = 10
    transient_robust_mode: bool = True
    transient_auto_regularize: bool = True

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "tstop": self.tstop,
            "dt": self.dt,
            "max_step": self.max_step,
            "tstart": self.tstart,
            "abstol": self.abstol,
            "reltol": self.reltol,
            "solver": self.solver,
            "step_mode": self.step_mode,
            "output_points": self.output_points,
            "enable_events": self.enable_events,
            "max_step_retries": self.max_step_retries,
            "max_iterations": self.max_iterations,
            "enable_voltage_limiting": self.enable_voltage_limiting,
            "max_voltage_step": self.max_voltage_step,
            "dc_strategy": self.dc_strategy,
            "gmin_initial": self.gmin_initial,
            "gmin_final": self.gmin_final,
            "dc_source_steps": self.dc_source_steps,
            "transient_robust_mode": self.transient_robust_mode,
            "transient_auto_regularize": self.transient_auto_regularize,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationSettings":
        """Deserialize from dictionary."""
        return cls(
            tstop=data.get("tstop", 1e-3),
            dt=data.get("dt", 1e-6),
            max_step=float(data.get("max_step", data.get("dt", 1e-6))),
            tstart=data.get("tstart", 0.0),
            abstol=data.get("abstol", 1e-12),
            reltol=data.get("reltol", 1e-3),
            solver=str(data.get("solver", "auto")),
            step_mode=str(data.get("step_mode", "fixed")),
            output_points=int(data.get("output_points", 10000)),
            enable_events=bool(data.get("enable_events", True)),
            max_step_retries=int(data.get("max_step_retries", 8)),
            max_iterations=data.get("max_iterations", 50),
            enable_voltage_limiting=bool(data.get("enable_voltage_limiting", False)),
            max_voltage_step=float(data.get("max_voltage_step", 5.0)),
            dc_strategy=str(data.get("dc_strategy", "auto")),
            gmin_initial=float(data.get("gmin_initial", 1e-3)),
            gmin_final=float(data.get("gmin_final", 1e-12)),
            dc_source_steps=int(data.get("dc_source_steps", 10)),
            transient_robust_mode=bool(data.get("transient_robust_mode", True)),
            transient_auto_regularize=bool(data.get("transient_auto_regularize", True)),
        )


@dataclass
class ScopeWindowState:
    """Persisted UI state for a per-scope window."""

    component_id: str
    is_open: bool = False
    geometry: list[int] | None = None  # [x, y, width, height]

    def to_dict(self) -> dict:
        """Serialize the window state."""
        return {
            "component_id": self.component_id,
            "is_open": self.is_open,
            "geometry": self.geometry,
        }

    @classmethod
    def from_dict(cls, data: dict, fallback_id: str | None = None) -> "ScopeWindowState":
        """Deserialize window state."""
        return cls(
            component_id=data.get("component_id") or fallback_id or "",
            is_open=data.get("is_open", False),
            geometry=data.get("geometry"),
        )


@dataclass
class Project:
    """A project containing one or more circuit schematics."""

    name: str = "Untitled Project"
    path: Path | None = None
    circuits: dict[str, Circuit] = field(default_factory=dict)
    active_circuit: str = "main"
    subcircuits: dict[UUID, SubcircuitDefinition] = field(default_factory=dict)
    simulation_settings: SimulationSettings = field(default_factory=SimulationSettings)
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
    scope_windows: dict[str, ScopeWindowState] = field(default_factory=dict)
    _dirty: bool = field(default=False, repr=False)

    def __post_init__(self):
        """Ensure there's at least one circuit."""
        if not self.circuits:
            self.circuits["main"] = Circuit(name="main")

    @property
    def is_dirty(self) -> bool:
        """Check if project has unsaved changes."""
        return self._dirty

    def mark_dirty(self) -> None:
        """Mark project as having unsaved changes."""
        self._dirty = True
        self.modified = datetime.now()

    def mark_clean(self) -> None:
        """Mark project as saved."""
        self._dirty = False

    def get_active_circuit(self) -> Circuit:
        """Get the currently active circuit."""
        if self.active_circuit not in self.circuits:
            self.active_circuit = list(self.circuits.keys())[0]
        return self.circuits[self.active_circuit]

    def add_circuit(self, name: str) -> Circuit:
        """Add a new circuit to the project."""
        if name in self.circuits:
            raise ValueError(f"Circuit '{name}' already exists")
        circuit = Circuit(name=name)
        self.circuits[name] = circuit
        self.mark_dirty()
        return circuit

    def remove_circuit(self, name: str) -> None:
        """Remove a circuit from the project."""
        if name not in self.circuits:
            raise ValueError(f"Circuit '{name}' not found")
        if len(self.circuits) <= 1:
            raise ValueError("Cannot remove the last circuit")
        del self.circuits[name]
        if self.active_circuit == name:
            self.active_circuit = list(self.circuits.keys())[0]
        self.mark_dirty()

    def to_dict(self) -> dict:
        """Serialize project to dictionary."""
        return {
            "version": "1.0",
            "name": self.name,
            "created": self.created.isoformat(),
            "modified": self.modified.isoformat(),
            "active_circuit": self.active_circuit,
            "simulation_settings": self.simulation_settings.to_dict(),
            "circuits": {name: c.to_dict() for name, c in self.circuits.items()},
            "subcircuits": [definition.to_dict() for definition in self.subcircuits.values()],
            "scope_windows": {
                component_id: state.to_dict()
                for component_id, state in self.scope_windows.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> "Project":
        """Deserialize project from dictionary."""
        circuits = {}
        for name, circuit_data in data.get("circuits", {}).items():
            circuits[name] = Circuit.from_dict(circuit_data)

        subcircuits: dict[UUID, SubcircuitDefinition] = {}
        for definition_data in data.get("subcircuits", []):
            definition = SubcircuitDefinition.from_dict(definition_data)
            subcircuits[definition.id] = definition

        scope_windows: dict[str, ScopeWindowState] = {}
        for component_id, state_data in data.get("scope_windows", {}).items():
            state = ScopeWindowState.from_dict(state_data, component_id)
            if state.component_id:
                scope_windows[state.component_id] = state

        return cls(
            name=data.get("name", "Untitled Project"),
            path=path,
            circuits=circuits,
            active_circuit=data.get("active_circuit", "main"),
            simulation_settings=SimulationSettings.from_dict(
                data.get("simulation_settings", {})
            ),
            created=datetime.fromisoformat(data["created"]) if "created" in data else datetime.now(),
            modified=datetime.fromisoformat(data["modified"]) if "modified" in data else datetime.now(),
            subcircuits=subcircuits,
            scope_windows=scope_windows,
        )

    def save(self, path: Path | None = None) -> None:
        """Save project to file."""
        save_path = path or self.path
        if save_path is None:
            raise ValueError("No path specified for saving")

        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        self.path = save_path
        self.mark_clean()

    @classmethod
    def load(cls, path: Path) -> "Project":
        """Load project from file."""
        path = Path(path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        project = cls.from_dict(data, path)
        project.mark_clean()
        return project

    # Subcircuit helpers

    def add_subcircuit(self, definition: SubcircuitDefinition) -> None:
        """Add a subcircuit definition to the project."""
        self.subcircuits[definition.id] = definition
        self.mark_dirty()

    def get_subcircuit(self, definition_id: UUID) -> SubcircuitDefinition | None:
        """Retrieve a subcircuit definition by ID."""
        return self.subcircuits.get(definition_id)

    def remove_subcircuit(self, definition_id: UUID) -> None:
        """Remove a subcircuit definition if present."""
        if definition_id in self.subcircuits:
            del self.subcircuits[definition_id]
            self.mark_dirty()

    def scope_state_for(self, component_id: str) -> ScopeWindowState:
        """Return (and create if needed) the window state for a scope component."""
        state = self.scope_windows.get(component_id)
        if state is None:
            state = ScopeWindowState(component_id=component_id)
            self.scope_windows[component_id] = state
        return state
