"""Project model for managing multiple schematics and settings."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pulsimgui.models.circuit import Circuit


@dataclass
class SimulationSettings:
    """Settings for transient simulation."""

    tstop: float = 1e-3
    dt: float = 1e-6
    tstart: float = 0.0
    abstol: float = 1e-12
    reltol: float = 1e-3
    max_iterations: int = 50

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "tstop": self.tstop,
            "dt": self.dt,
            "tstart": self.tstart,
            "abstol": self.abstol,
            "reltol": self.reltol,
            "max_iterations": self.max_iterations,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationSettings":
        """Deserialize from dictionary."""
        return cls(
            tstop=data.get("tstop", 1e-3),
            dt=data.get("dt", 1e-6),
            tstart=data.get("tstart", 0.0),
            abstol=data.get("abstol", 1e-12),
            reltol=data.get("reltol", 1e-3),
            max_iterations=data.get("max_iterations", 50),
        )


@dataclass
class Project:
    """A project containing one or more circuit schematics."""

    name: str = "Untitled Project"
    path: Path | None = None
    circuits: dict[str, Circuit] = field(default_factory=dict)
    active_circuit: str = "main"
    simulation_settings: SimulationSettings = field(default_factory=SimulationSettings)
    created: datetime = field(default_factory=datetime.now)
    modified: datetime = field(default_factory=datetime.now)
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
        }

    @classmethod
    def from_dict(cls, data: dict, path: Path | None = None) -> "Project":
        """Deserialize project from dictionary."""
        circuits = {}
        for name, circuit_data in data.get("circuits", {}).items():
            circuits[name] = Circuit.from_dict(circuit_data)

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
