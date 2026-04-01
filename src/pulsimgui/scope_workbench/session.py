"""Standalone workspace/session controller for scope workbench."""

from __future__ import annotations

from dataclasses import replace

from .adapter import ScopeHostAdapter, ScopeSignalDescriptor
from .models import (
    DEFAULT_MEASUREMENT_KEYS,
    INTERVAL_TARGETS,
    SavedView,
    ScopeViewState,
    ScopeWorkspaceState,
    normalize_interval_target,
)


class ScopeWorkbenchSession:
    """Manage multi-scope workspace state without PulsimGui app-shell coupling."""

    def __init__(
        self,
        workspace_id: str,
        *,
        state: ScopeWorkspaceState | None = None,
    ) -> None:
        if state is None:
            state = ScopeWorkspaceState(workspace_id=workspace_id)

        self._workspace = replace(state, workspace_id=workspace_id)
        self._scopes_by_id: dict[str, ScopeViewState] = {
            scope.scope_id: replace(scope) for scope in self._workspace.scopes if scope.scope_id
        }
        if not self._scopes_by_id:
            default_scope = ScopeViewState(scope_id="scope-1", name="Scope 1")
            self._scopes_by_id[default_scope.scope_id] = default_scope

        self._workspace.scopes = list(self._scopes_by_id.values())
        if self._workspace.active_scope_id not in self._scopes_by_id:
            self._workspace.active_scope_id = next(iter(self._scopes_by_id))

        self._signal_catalog: list[ScopeSignalDescriptor] = []

    @property
    def workspace_id(self) -> str:
        return self._workspace.workspace_id

    @property
    def active_scope_id(self) -> str:
        return str(self._workspace.active_scope_id)

    @property
    def sidebar_collapsed(self) -> bool:
        return bool(self._workspace.sidebar_collapsed)

    def list_scopes(self) -> list[ScopeViewState]:
        """Return scopes ordered by insertion."""
        return [replace(scope) for scope in self._workspace.scopes]

    def get_scope(self, scope_id: str) -> ScopeViewState:
        """Return a copy of scope state."""
        scope = self._scopes_by_id.get(scope_id)
        if scope is None:
            raise KeyError(f"Unknown scope id: {scope_id}")
        return replace(scope)

    def add_scope(self, name: str | None = None) -> ScopeViewState:
        """Create a new scope with generated ID."""
        existing = set(self._scopes_by_id)
        index = 1
        while True:
            scope_id = f"scope-{index}"
            if scope_id not in existing:
                break
            index += 1

        scope_name = str(name or f"Scope {index}").strip() or f"Scope {index}"
        scope = ScopeViewState(scope_id=scope_id, name=scope_name)
        self._scopes_by_id[scope_id] = scope
        self._workspace.scopes.append(scope)
        self._workspace.active_scope_id = scope_id
        return replace(scope)

    def ensure_scope(self, scope_id: str, name: str | None = None) -> ScopeViewState:
        """Ensure one scope exists with the explicit identifier."""
        clean_id = str(scope_id).strip()
        if not clean_id:
            raise ValueError("Scope id cannot be empty")

        existing = self._scopes_by_id.get(clean_id)
        if existing is not None:
            if name:
                clean_name = str(name).strip()
                if clean_name:
                    existing.name = clean_name
            return replace(existing)

        scope_name = str(name or clean_id).strip() or clean_id
        scope = ScopeViewState(scope_id=clean_id, name=scope_name)
        self._scopes_by_id[clean_id] = scope
        self._workspace.scopes.append(scope)
        self._workspace.active_scope_id = clean_id
        return replace(scope)

    def remove_scope(self, scope_id: str) -> None:
        """Remove an existing scope and keep workspace valid."""
        if scope_id not in self._scopes_by_id:
            raise KeyError(f"Unknown scope id: {scope_id}")
        if len(self._scopes_by_id) == 1:
            raise ValueError("At least one scope must remain in the workspace")

        del self._scopes_by_id[scope_id]
        self._workspace.scopes = [scope for scope in self._workspace.scopes if scope.scope_id != scope_id]
        if self._workspace.active_scope_id == scope_id:
            self._workspace.active_scope_id = self._workspace.scopes[0].scope_id

    def discard_scope(self, scope_id: str) -> None:
        """Best-effort removal used when host components are deleted."""
        if scope_id not in self._scopes_by_id:
            return
        if len(self._scopes_by_id) == 1:
            only_scope = self._scopes_by_id.get(scope_id)
            if only_scope is not None:
                only_scope.name = "Scope 1"
                only_scope.signal_keys = []
                only_scope.measurement_keys = list(DEFAULT_MEASUREMENT_KEYS)
                only_scope.cursors_enabled = False
                only_scope.cursor_a = None
                only_scope.cursor_b = None
                self._workspace.active_scope_id = only_scope.scope_id
            return
        self.remove_scope(scope_id)

    def duplicate_scope(self, scope_id: str, name: str | None = None) -> ScopeViewState:
        """Duplicate a scope and copy its analysis configuration."""
        source = self._require_scope(scope_id)
        duplicate_name = str(name or f"{source.name} Copy").strip() or f"{source.name} Copy"
        duplicated = self.add_scope(duplicate_name)
        target = self._require_scope(duplicated.scope_id)
        target.signal_keys = list(source.signal_keys)
        target.plot_groups = dict(source.plot_groups)
        target.measurement_keys = list(source.measurement_keys)
        target.cursors_enabled = source.cursors_enabled
        target.cursor_a = source.cursor_a
        target.cursor_b = source.cursor_b
        return replace(target)

    def rename_scope(self, scope_id: str, name: str) -> None:
        """Rename an existing scope."""
        scope = self._require_scope(scope_id)
        clean_name = str(name).strip()
        if not clean_name:
            raise ValueError("Scope name cannot be empty")
        scope.name = clean_name

    def set_active_scope(self, scope_id: str) -> None:
        """Set active scope for workspace-level selection."""
        self._require_scope(scope_id)
        self._workspace.active_scope_id = scope_id

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        """Persist sidebar collapsed/expanded state at workspace level."""
        self._workspace.sidebar_collapsed = bool(collapsed)

    def set_scope_signals(self, scope_id: str, signal_keys: list[str]) -> None:
        """Assign signals to one scope."""
        scope = self._require_scope(scope_id)
        unique: list[str] = []
        seen: set[str] = set()
        for raw in signal_keys:
            key = str(raw).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(key)
        scope.signal_keys = unique
        if scope.plot_groups:
            scope.plot_groups = {
                signal_name: leader_name
                for signal_name, leader_name in scope.plot_groups.items()
                if signal_name in seen and leader_name in seen
            }

    def set_scope_plot_groups(self, scope_id: str, plot_groups: dict[str, str]) -> None:
        """Persist per-signal plot grouping for one scope."""
        scope = self._require_scope(scope_id)
        valid = set(scope.signal_keys)
        normalized: dict[str, str] = {}
        for signal_raw, leader_raw in plot_groups.items():
            signal_name = str(signal_raw).strip()
            leader_name = str(leader_raw).strip()
            if not signal_name or not leader_name:
                continue
            if signal_name not in valid or leader_name not in valid:
                continue
            normalized[signal_name] = leader_name
        scope.plot_groups = normalized

    def set_scope_measurements(self, scope_id: str, measurement_keys: list[str]) -> None:
        """Set visible measurement columns for one scope."""
        scope = self._require_scope(scope_id)
        filtered = [
            str(key)
            for key in measurement_keys
            if str(key) in DEFAULT_MEASUREMENT_KEYS
        ]
        scope.measurement_keys = filtered or list(DEFAULT_MEASUREMENT_KEYS)

    def set_scope_cursors(
        self,
        scope_id: str,
        *,
        enabled: bool,
        cursor_a: float | None = None,
        cursor_b: float | None = None,
    ) -> None:
        """Persist cursor state for one scope."""
        scope = self._require_scope(scope_id)
        scope.cursors_enabled = bool(enabled)
        scope.cursor_a = float(cursor_a) if isinstance(cursor_a, (int, float)) else None
        scope.cursor_b = float(cursor_b) if isinstance(cursor_b, (int, float)) else None

    def set_scope_interval_target(self, scope_id: str, target: str) -> None:
        """Set interval target for statistics computation in one scope."""
        scope = self._require_scope(scope_id)
        normalized = normalize_interval_target(target)
        if normalized not in INTERVAL_TARGETS:
            raise ValueError(f"Invalid interval target: {target!r}. Must be one of {INTERVAL_TARGETS}")
        scope.interval_target = normalized

    def add_saved_view(
        self,
        scope_id: str,
        name: str,
        time_start: float,
        time_end: float,
        y_min: float | None = None,
        y_max: float | None = None,
    ) -> SavedView:
        """Add a named saved view to a scope."""
        scope = self._require_scope(scope_id)
        existing_ids = {v.view_id for v in scope.saved_views}
        index = 1
        while True:
            view_id = f"view-{index}"
            if view_id not in existing_ids:
                break
            index += 1
        clean_name = str(name).strip() or f"View {index}"
        view = SavedView(
            view_id=view_id,
            name=clean_name,
            time_start=float(time_start),
            time_end=float(time_end),
            y_min=float(y_min) if isinstance(y_min, (int, float)) else None,
            y_max=float(y_max) if isinstance(y_max, (int, float)) else None,
        )
        scope.saved_views.append(view)
        return replace(view)

    def remove_saved_view(self, scope_id: str, view_id: str) -> None:
        """Remove a saved view from a scope."""
        scope = self._require_scope(scope_id)
        before = len(scope.saved_views)
        scope.saved_views = [v for v in scope.saved_views if v.view_id != view_id]
        if len(scope.saved_views) == before:
            raise KeyError(f"Unknown view id: {view_id}")

    def list_saved_views(self, scope_id: str) -> list[SavedView]:
        """Return saved views for a scope."""
        scope = self._require_scope(scope_id)
        return [replace(v) for v in scope.saved_views]

    def set_signal_catalog(self, signals: list[ScopeSignalDescriptor]) -> None:
        """Replace available signal catalog published by host."""
        self._signal_catalog = [replace(item) for item in signals]

    def list_signal_catalog(self) -> list[ScopeSignalDescriptor]:
        """Return published signal catalog."""
        return [replace(item) for item in self._signal_catalog]

    def export_state(self) -> ScopeWorkspaceState:
        """Return workspace snapshot for persistence/export."""
        scopes = [replace(scope) for scope in self._workspace.scopes]
        return ScopeWorkspaceState(
            workspace_id=self.workspace_id,
            scopes=scopes,
            active_scope_id=self._workspace.active_scope_id,
            sidebar_collapsed=self._workspace.sidebar_collapsed,
        )

    def export_state_dict(self) -> dict[str, object]:
        """Serialize workspace snapshot to plain dictionary."""
        return self.export_state().to_dict()

    def save_via_adapter(self, adapter: ScopeHostAdapter) -> None:
        """Persist workspace using host adapter."""
        adapter.save_workspace_state(self.workspace_id, self.export_state_dict())

    @classmethod
    def from_adapter(
        cls,
        workspace_id: str,
        adapter: ScopeHostAdapter,
    ) -> "ScopeWorkbenchSession":
        """Load session state from adapter, creating defaults on first run."""
        payload = adapter.load_workspace_state(workspace_id)
        state = ScopeWorkspaceState.from_dict(payload) if isinstance(payload, dict) else None
        session = cls(workspace_id, state=state)
        session.set_signal_catalog(adapter.list_signals(workspace_id))
        return session

    def _require_scope(self, scope_id: str) -> ScopeViewState:
        scope = self._scopes_by_id.get(scope_id)
        if scope is None:
            raise KeyError(f"Unknown scope id: {scope_id}")
        return scope
