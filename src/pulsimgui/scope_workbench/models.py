"""Portable models for standalone scope workbench state."""

from __future__ import annotations

from dataclasses import dataclass, field


# Supported metric keys used by the measurements table.
DEFAULT_MEASUREMENT_KEYS: tuple[str, ...] = (
    "c1",
    "c2",
    "dv",
    "min",
    "max",
    "mean",
    "rms",
    "pkpk",
)


@dataclass(slots=True)
class ScopeViewState:
    """State for one scope view inside a scope workspace."""

    scope_id: str
    name: str
    signal_keys: list[str] = field(default_factory=list)
    plot_groups: dict[str, str] = field(default_factory=dict)
    measurement_keys: list[str] = field(default_factory=lambda: list(DEFAULT_MEASUREMENT_KEYS))
    cursors_enabled: bool = False
    cursor_a: float | None = None
    cursor_b: float | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize scope state to a host-agnostic dictionary."""
        return {
            "scope_id": self.scope_id,
            "name": self.name,
            "signal_keys": list(self.signal_keys),
            "plot_groups": {str(signal): str(leader) for signal, leader in self.plot_groups.items()},
            "measurement_keys": list(self.measurement_keys),
            "cursors_enabled": bool(self.cursors_enabled),
            "cursor_a": self.cursor_a,
            "cursor_b": self.cursor_b,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ScopeViewState":
        """Build scope state from serialized data."""
        scope_id = str(payload.get("scope_id") or "").strip()
        name = str(payload.get("name") or scope_id or "Scope").strip()
        signal_keys = [str(item) for item in payload.get("signal_keys", []) if str(item).strip()]
        plot_groups_raw = payload.get("plot_groups")
        plot_groups: dict[str, str] = {}
        if isinstance(plot_groups_raw, dict):
            for signal_raw, leader_raw in plot_groups_raw.items():
                signal_name = str(signal_raw).strip()
                leader_name = str(leader_raw).strip()
                if signal_name and leader_name:
                    plot_groups[signal_name] = leader_name
        raw_measurements = payload.get("measurement_keys", [])
        measurement_keys = [
            str(item)
            for item in raw_measurements
            if str(item) in DEFAULT_MEASUREMENT_KEYS
        ]
        if not measurement_keys:
            measurement_keys = list(DEFAULT_MEASUREMENT_KEYS)

        cursor_a_raw = payload.get("cursor_a")
        cursor_b_raw = payload.get("cursor_b")

        return cls(
            scope_id=scope_id,
            name=name,
            signal_keys=signal_keys,
            plot_groups=plot_groups,
            measurement_keys=measurement_keys,
            cursors_enabled=bool(payload.get("cursors_enabled", False)),
            cursor_a=float(cursor_a_raw) if isinstance(cursor_a_raw, (int, float)) else None,
            cursor_b=float(cursor_b_raw) if isinstance(cursor_b_raw, (int, float)) else None,
        )


@dataclass(slots=True)
class ScopeWorkspaceState:
    """Workspace state containing multiple independent scopes."""

    workspace_id: str
    scopes: list[ScopeViewState] = field(default_factory=list)
    active_scope_id: str | None = None
    sidebar_collapsed: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize workspace state to a host-agnostic dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "scopes": [scope.to_dict() for scope in self.scopes],
            "active_scope_id": self.active_scope_id,
            "sidebar_collapsed": bool(self.sidebar_collapsed),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ScopeWorkspaceState":
        """Build workspace state from serialized data."""
        workspace_id = str(payload.get("workspace_id") or "scope-workspace").strip()
        scopes_payload = payload.get("scopes")
        scopes: list[ScopeViewState] = []
        if isinstance(scopes_payload, list):
            for entry in scopes_payload:
                if isinstance(entry, dict):
                    scope = ScopeViewState.from_dict(entry)
                    if scope.scope_id:
                        scopes.append(scope)
        active_scope_id = str(payload.get("active_scope_id") or "").strip() or None
        if active_scope_id is None and scopes:
            active_scope_id = scopes[0].scope_id

        return cls(
            workspace_id=workspace_id,
            scopes=scopes,
            active_scope_id=active_scope_id,
            sidebar_collapsed=bool(payload.get("sidebar_collapsed", False)),
        )
