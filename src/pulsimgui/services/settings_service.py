"""Application settings service using QSettings."""

from pathlib import Path

from PySide6.QtCore import QSettings


class SettingsService:
    """Service for managing application settings."""

    def __init__(self):
        self._settings = QSettings("Pulsim", "PulsimGui")

    # Recent projects
    def get_recent_projects(self) -> list[str]:
        """Get list of recently opened projects."""
        return self._settings.value("recent_projects", []) or []

    def add_recent_project(self, path: str) -> None:
        """Add a project to the recent list."""
        recent = self.get_recent_projects()
        path = str(Path(path).resolve())
        if path in recent:
            recent.remove(path)
        recent.insert(0, path)
        recent = recent[:10]  # Keep last 10
        self._settings.setValue("recent_projects", recent)

    def clear_recent_projects(self) -> None:
        """Clear the recent projects list."""
        self._settings.setValue("recent_projects", [])

    # Theme
    def get_theme(self) -> str:
        """Get current theme name."""
        return self._settings.value("theme", "light")

    def set_theme(self, theme: str) -> None:
        """Set the theme."""
        self._settings.setValue("theme", theme)

    # Window geometry
    def get_window_geometry(self) -> bytes | None:
        """Get saved window geometry."""
        return self._settings.value("window_geometry")

    def set_window_geometry(self, geometry: bytes) -> None:
        """Save window geometry."""
        self._settings.setValue("window_geometry", geometry)

    def get_window_state(self) -> bytes | None:
        """Get saved window state (dock positions, etc.)."""
        return self._settings.value("window_state")

    def set_window_state(self, state: bytes) -> None:
        """Save window state."""
        self._settings.setValue("window_state", state)

    # Grid settings
    def get_grid_size(self) -> float:
        """Get grid size in mm."""
        return float(self._settings.value("grid_size", 2.5))

    def set_grid_size(self, size: float) -> None:
        """Set grid size."""
        self._settings.setValue("grid_size", size)

    def get_snap_to_grid(self) -> bool:
        """Get snap-to-grid setting."""
        return self._settings.value("snap_to_grid", True, type=bool)

    def set_snap_to_grid(self, enabled: bool) -> None:
        """Set snap-to-grid setting."""
        self._settings.setValue("snap_to_grid", enabled)

    def get_show_grid(self) -> bool:
        """Get show grid setting."""
        return self._settings.value("show_grid", True, type=bool)

    def set_show_grid(self, enabled: bool) -> None:
        """Set show grid setting."""
        self._settings.setValue("show_grid", enabled)

    # Auto-save
    def get_auto_save_enabled(self) -> bool:
        """Get auto-save enabled setting."""
        return self._settings.value("auto_save_enabled", True, type=bool)

    def set_auto_save_enabled(self, enabled: bool) -> None:
        """Set auto-save enabled setting."""
        self._settings.setValue("auto_save_enabled", enabled)

    def get_auto_save_interval(self) -> int:
        """Get auto-save interval in minutes."""
        return int(self._settings.value("auto_save_interval", 5))

    def set_auto_save_interval(self, minutes: int) -> None:
        """Set auto-save interval."""
        self._settings.setValue("auto_save_interval", minutes)

    # Default project location
    def get_default_project_location(self) -> str:
        """Get default location for new projects."""
        return self._settings.value("default_project_location", str(Path.home() / "PulsimProjects"))

    def set_default_project_location(self, path: str) -> None:
        """Set default location for new projects."""
        self._settings.setValue("default_project_location", path)

    # Backend preference
    def get_backend_preference(self) -> str | None:
        """Return the preferred backend identifier (if any)."""
        value = self._settings.value("backend/preference", "")
        return value or None

    def set_backend_preference(self, identifier: str | None) -> None:
        """Persist the preferred backend identifier."""
        if identifier:
            self._settings.setValue("backend/preference", identifier)
        else:
            self._settings.remove("backend/preference")

    # Component value labels
    def get_show_value_labels(self) -> bool:
        """Get show value labels setting."""
        return self._settings.value("show_value_labels", True, type=bool)

    def set_show_value_labels(self, enabled: bool) -> None:
        """Set show value labels setting."""
        self._settings.setValue("show_value_labels", enabled)

    # Simulation settings
    def get_simulation_settings(self) -> dict:
        """Get saved simulation settings."""
        return {
            "t_stop": float(self._settings.value("simulation/t_stop", 1e-3)),
            "t_step": float(self._settings.value("simulation/t_step", 1e-6)),
            "solver": self._settings.value("simulation/solver", "auto"),
            "max_step": float(self._settings.value("simulation/max_step", 1e-6)),
            "rel_tol": float(self._settings.value("simulation/rel_tol", 1e-4)),
            "abs_tol": float(self._settings.value("simulation/abs_tol", 1e-6)),
            "output_points": int(self._settings.value("simulation/output_points", 10000)),
        }

    def set_simulation_settings(self, settings: dict) -> None:
        """Save simulation settings."""
        for key, value in settings.items():
            self._settings.setValue(f"simulation/{key}", value)

    # Solver settings (Newton solver, DC strategies)
    def get_solver_settings(self) -> dict:
        """Get saved solver settings."""
        return {
            "max_newton_iterations": int(self._settings.value("solver/max_newton_iterations", 50)),
            "enable_voltage_limiting": self._settings.value("solver/enable_voltage_limiting", True, type=bool),
            "max_voltage_step": float(self._settings.value("solver/max_voltage_step", 5.0)),
            "dc_strategy": self._settings.value("solver/dc_strategy", "auto"),
            "gmin_initial": float(self._settings.value("solver/gmin_initial", 1e-3)),
            "gmin_final": float(self._settings.value("solver/gmin_final", 1e-12)),
        }

    def set_solver_settings(self, settings: dict) -> None:
        """Save solver settings."""
        for key, value in settings.items():
            self._settings.setValue(f"solver/{key}", value)
