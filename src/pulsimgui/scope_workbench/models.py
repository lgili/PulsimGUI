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

# Valid interval targets for statistics computation.
INTERVAL_TARGETS: tuple[str, ...] = ("full", "window", "a_to_b")
_INTERVAL_TARGET_ALIASES: dict[str, str] = {
    "full_range": "full",
    "visible_range": "window",
    "between_cursors": "a_to_b",
    "cursor_a": "a_to_b",
    "cursor_b": "a_to_b",
}


def normalize_interval_target(target: str | None) -> str:
    """Normalize legacy or user-facing interval target aliases."""
    value = str(target or "full").strip().lower() or "full"
    value = _INTERVAL_TARGET_ALIASES.get(value, value)
    return value


def _clean_string_list(values: object) -> list[str]:
    """Normalize one serialized list of identifiers into unique non-empty strings."""
    if not isinstance(values, list):
        return []
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        cleaned.append(value)
    return cleaned


@dataclass(slots=True)
class ScopeSelectionState:
    """Selection ownership shared by the scope tree, plots, inspector, and views."""

    active_signal_id: str | None = None
    selected_signal_ids: list[str] = field(default_factory=list)
    active_plot_group_id: str | None = None
    active_saved_view_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "active_signal_id": self.active_signal_id,
            "selected_signal_ids": list(self.selected_signal_ids),
            "active_plot_group_id": self.active_plot_group_id,
            "active_saved_view_id": self.active_saved_view_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "ScopeSelectionState":
        if not isinstance(payload, dict):
            return cls()
        active_signal_id = str(payload.get("active_signal_id") or "").strip() or None
        selected_signal_ids = _clean_string_list(payload.get("selected_signal_ids"))
        if active_signal_id and active_signal_id not in selected_signal_ids:
            selected_signal_ids.insert(0, active_signal_id)
        active_plot_group_id = str(payload.get("active_plot_group_id") or "").strip() or None
        active_saved_view_id = str(payload.get("active_saved_view_id") or "").strip() or None
        return cls(
            active_signal_id=active_signal_id,
            selected_signal_ids=selected_signal_ids,
            active_plot_group_id=active_plot_group_id,
            active_saved_view_id=active_saved_view_id,
        )


@dataclass(slots=True)
class ScopeCursorState:
    """Cursor ownership shared by the plot, inspector, and measurement surfaces."""

    enabled: bool = False
    cursor_a: float | None = None
    cursor_b: float | None = None
    y1: float | None = None
    y2: float | None = None
    snap_mode: str = "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": bool(self.enabled),
            "cursor_a": self.cursor_a,
            "cursor_b": self.cursor_b,
            "y1": self.y1,
            "y2": self.y2,
            "snap_mode": self.snap_mode,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "ScopeCursorState":
        if not isinstance(payload, dict):
            return cls()
        cursor_a_raw = payload.get("cursor_a")
        cursor_b_raw = payload.get("cursor_b")
        y1_raw = payload.get("y1")
        y2_raw = payload.get("y2")
        snap_mode = str(payload.get("snap_mode") or "none").strip().lower() or "none"
        return cls(
            enabled=bool(payload.get("enabled", False)),
            cursor_a=float(cursor_a_raw) if isinstance(cursor_a_raw, (int, float)) else None,
            cursor_b=float(cursor_b_raw) if isinstance(cursor_b_raw, (int, float)) else None,
            y1=float(y1_raw) if isinstance(y1_raw, (int, float)) else None,
            y2=float(y2_raw) if isinstance(y2_raw, (int, float)) else None,
            snap_mode=snap_mode,
        )


@dataclass(slots=True)
class ScopeMeasurementState:
    """Measurement ownership shared by quick metrics, inspector, and bottom drawer."""

    interval_target: str = "full"
    measurement_keys: list[str] = field(default_factory=lambda: list(DEFAULT_MEASUREMENT_KEYS))
    target_signal_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "interval_target": self.interval_target,
            "measurement_keys": list(self.measurement_keys),
            "target_signal_id": self.target_signal_id,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "ScopeMeasurementState":
        if not isinstance(payload, dict):
            return cls()
        raw_measurements = payload.get("measurement_keys", [])
        measurement_keys = [
            str(item)
            for item in raw_measurements
            if str(item) in DEFAULT_MEASUREMENT_KEYS
        ]
        if not measurement_keys:
            measurement_keys = list(DEFAULT_MEASUREMENT_KEYS)
        interval_target = normalize_interval_target(
            str(payload.get("interval_target") or "full").strip()
        )
        if interval_target not in INTERVAL_TARGETS:
            interval_target = "full"
        target_signal_id = str(payload.get("target_signal_id") or "").strip() or None
        return cls(
            interval_target=interval_target,
            measurement_keys=measurement_keys,
            target_signal_id=target_signal_id,
        )


@dataclass(slots=True)
class ScopePanelState:
    """Panel and tab ownership for one scope workspace."""

    left_panel_visible: bool = True
    right_panel_visible: bool = True
    bottom_drawer_expanded: bool = False
    left_panel_width: int | None = None
    right_panel_width: int | None = None
    bottom_drawer_height: int | None = None
    sidebar_tab_index: int = 0
    analysis_tab_index: int = 0
    bottom_drawer_tab_index: int = 0

    def to_dict(self) -> dict[str, object]:
        return {
            "left_panel_visible": bool(self.left_panel_visible),
            "right_panel_visible": bool(self.right_panel_visible),
            "bottom_drawer_expanded": bool(self.bottom_drawer_expanded),
            "left_panel_width": self.left_panel_width,
            "right_panel_width": self.right_panel_width,
            "bottom_drawer_height": self.bottom_drawer_height,
            "sidebar_tab_index": int(self.sidebar_tab_index),
            "analysis_tab_index": int(self.analysis_tab_index),
            "bottom_drawer_tab_index": int(self.bottom_drawer_tab_index),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object] | None) -> "ScopePanelState":
        if not isinstance(payload, dict):
            return cls()
        left_panel_width = payload.get("left_panel_width")
        right_panel_width = payload.get("right_panel_width")
        bottom_drawer_height = payload.get("bottom_drawer_height")
        sidebar_tab_index = payload.get("sidebar_tab_index", 0)
        analysis_tab_index = payload.get("analysis_tab_index", 0)
        bottom_drawer_tab_index = payload.get("bottom_drawer_tab_index", 0)
        return cls(
            left_panel_visible=bool(payload.get("left_panel_visible", True)),
            right_panel_visible=bool(payload.get("right_panel_visible", True)),
            bottom_drawer_expanded=bool(payload.get("bottom_drawer_expanded", False)),
            left_panel_width=int(left_panel_width) if isinstance(left_panel_width, (int, float)) else None,
            right_panel_width=int(right_panel_width) if isinstance(right_panel_width, (int, float)) else None,
            bottom_drawer_height=int(bottom_drawer_height) if isinstance(bottom_drawer_height, (int, float)) else None,
            sidebar_tab_index=int(sidebar_tab_index) if isinstance(sidebar_tab_index, (int, float)) else 0,
            analysis_tab_index=int(analysis_tab_index) if isinstance(analysis_tab_index, (int, float)) else 0,
            bottom_drawer_tab_index=int(bottom_drawer_tab_index) if isinstance(bottom_drawer_tab_index, (int, float)) else 0,
        )


@dataclass(slots=True)
class SavedView:
    """A named snapshot of a zoom/time-window range inside a scope."""

    view_id: str
    name: str
    time_start: float
    time_end: float
    y_min: float | None = None
    y_max: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "view_id": self.view_id,
            "name": self.name,
            "time_start": self.time_start,
            "time_end": self.time_end,
            "y_min": self.y_min,
            "y_max": self.y_max,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SavedView":
        view_id = str(payload.get("view_id") or "").strip()
        name = str(payload.get("name") or view_id or "View").strip()
        time_start_raw = payload.get("time_start", 0.0)
        time_end_raw = payload.get("time_end", 1.0)
        y_min_raw = payload.get("y_min")
        y_max_raw = payload.get("y_max")
        return cls(
            view_id=view_id,
            name=name,
            time_start=float(time_start_raw) if isinstance(time_start_raw, (int, float)) else 0.0,
            time_end=float(time_end_raw) if isinstance(time_end_raw, (int, float)) else 1.0,
            y_min=float(y_min_raw) if isinstance(y_min_raw, (int, float)) else None,
            y_max=float(y_max_raw) if isinstance(y_max_raw, (int, float)) else None,
        )


@dataclass(slots=True)
class ScopeViewState:
    """State for one scope view inside a scope workspace."""

    scope_id: str
    name: str
    signal_keys: list[str] = field(default_factory=list)
    plot_groups: dict[str, str] = field(default_factory=dict)
    selection_state: ScopeSelectionState = field(default_factory=ScopeSelectionState)
    cursor_state: ScopeCursorState = field(default_factory=ScopeCursorState)
    measurement_state: ScopeMeasurementState = field(default_factory=ScopeMeasurementState)
    panel_state: ScopePanelState = field(default_factory=ScopePanelState)
    saved_views: list[SavedView] = field(default_factory=list)

    @property
    def measurement_keys(self) -> list[str]:
        return self.measurement_state.measurement_keys

    @measurement_keys.setter
    def measurement_keys(self, values: list[str]) -> None:
        self.measurement_state.measurement_keys = list(values)

    @property
    def cursors_enabled(self) -> bool:
        return self.cursor_state.enabled

    @cursors_enabled.setter
    def cursors_enabled(self, enabled: bool) -> None:
        self.cursor_state.enabled = bool(enabled)

    @property
    def cursor_a(self) -> float | None:
        return self.cursor_state.cursor_a

    @cursor_a.setter
    def cursor_a(self, value: float | None) -> None:
        self.cursor_state.cursor_a = value

    @property
    def cursor_b(self) -> float | None:
        return self.cursor_state.cursor_b

    @cursor_b.setter
    def cursor_b(self, value: float | None) -> None:
        self.cursor_state.cursor_b = value

    @property
    def interval_target(self) -> str:
        return self.measurement_state.interval_target

    @interval_target.setter
    def interval_target(self, value: str) -> None:
        self.measurement_state.interval_target = value

    @property
    def active_signal_id(self) -> str | None:
        return self.selection_state.active_signal_id

    @active_signal_id.setter
    def active_signal_id(self, value: str | None) -> None:
        self.selection_state.active_signal_id = str(value).strip() or None if value else None

    def to_dict(self) -> dict[str, object]:
        """Serialize scope state to a host-agnostic dictionary."""
        return {
            "scope_id": self.scope_id,
            "name": self.name,
            "signal_keys": list(self.signal_keys),
            "plot_groups": {str(signal): str(leader) for signal, leader in self.plot_groups.items()},
            "selection_state": self.selection_state.to_dict(),
            "cursor_state": self.cursor_state.to_dict(),
            "measurement_state": self.measurement_state.to_dict(),
            "panel_state": self.panel_state.to_dict(),
            "measurement_keys": list(self.measurement_keys),
            "cursors_enabled": bool(self.cursors_enabled),
            "cursor_a": self.cursor_a,
            "cursor_b": self.cursor_b,
            "interval_target": self.interval_target,
            "saved_views": [v.to_dict() for v in self.saved_views],
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
        legacy_selection = ScopeSelectionState(
            active_signal_id=str(payload.get("active_signal") or "").strip() or None,
        )
        selection_state = ScopeSelectionState.from_dict(
            payload.get("selection_state") if isinstance(payload.get("selection_state"), dict) else legacy_selection.to_dict()
        )
        cursor_state = ScopeCursorState.from_dict(
            payload.get("cursor_state") if isinstance(payload.get("cursor_state"), dict) else {
                "enabled": payload.get("cursors_enabled", False),
                "cursor_a": payload.get("cursor_a"),
                "cursor_b": payload.get("cursor_b"),
            }
        )
        measurement_state = ScopeMeasurementState.from_dict(
            payload.get("measurement_state") if isinstance(payload.get("measurement_state"), dict) else {
                "measurement_keys": payload.get("measurement_keys", []),
                "interval_target": payload.get("interval_target", "full"),
                "target_signal_id": selection_state.active_signal_id,
            }
        )
        panel_state = ScopePanelState.from_dict(
            payload.get("panel_state") if isinstance(payload.get("panel_state"), dict) else {
                "left_panel_visible": payload.get("left_panel_visible", True),
                "right_panel_visible": payload.get("right_panel_visible", True),
                "bottom_drawer_expanded": payload.get("bottom_drawer_expanded", False),
                "left_panel_width": payload.get("left_panel_width"),
                "right_panel_width": payload.get("right_panel_width"),
                "bottom_drawer_height": payload.get("bottom_drawer_height"),
                "sidebar_tab_index": payload.get("sidebar_tab_index", 0),
                "analysis_tab_index": payload.get("analysis_tab_index", 0),
                "bottom_drawer_tab_index": payload.get("bottom_drawer_tab", 0),
            }
        )

        saved_views_raw = payload.get("saved_views", [])
        saved_views: list[SavedView] = []
        if isinstance(saved_views_raw, list):
            for entry in saved_views_raw:
                if isinstance(entry, dict):
                    view = SavedView.from_dict(entry)
                    if view.view_id:
                        saved_views.append(view)

        return cls(
            scope_id=scope_id,
            name=name,
            signal_keys=signal_keys,
            plot_groups=plot_groups,
            selection_state=selection_state,
            cursor_state=cursor_state,
            measurement_state=measurement_state,
            panel_state=panel_state,
            saved_views=saved_views,
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
