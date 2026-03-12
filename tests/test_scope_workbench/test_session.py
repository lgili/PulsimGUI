"""Tests for standalone scope workbench session state."""

from __future__ import annotations

import pytest

from pulsimgui.scope_workbench import (
    DEFAULT_MEASUREMENT_KEYS,
    INTERVAL_TARGETS,
    ScopeSampleBatch,
    ScopeSignalDescriptor,
    ScopeWorkbenchSession,
    ScopeWorkspaceState,
    SavedView,
)


class _FakeAdapter:
    def __init__(self) -> None:
        self._state: dict[str, object] | None = None

    def list_signals(self, workspace_id: str) -> list[ScopeSignalDescriptor]:
        assert workspace_id == "ws-1"
        return [
            ScopeSignalDescriptor(signal_key="V(out)", label="Vout", unit="V", domain="electrical"),
            ScopeSignalDescriptor(signal_key="I(L)", label="IL", unit="A", domain="electrical"),
        ]

    def get_scope_samples(
        self,
        workspace_id: str,
        scope_id: str,
        signal_keys: list[str],
    ) -> ScopeSampleBatch:
        assert workspace_id == "ws-1"
        assert scope_id
        return ScopeSampleBatch(
            time=[0.0, 1e-6, 2e-6],
            signals={key: [0.0, 0.5, 1.0] for key in signal_keys},
        )

    def save_workspace_state(self, workspace_id: str, state: dict[str, object]) -> None:
        assert workspace_id == "ws-1"
        self._state = dict(state)

    def load_workspace_state(self, workspace_id: str) -> dict[str, object] | None:
        assert workspace_id == "ws-1"
        return dict(self._state) if isinstance(self._state, dict) else None


def test_session_bootstraps_default_scope() -> None:
    session = ScopeWorkbenchSession("ws-1")

    scopes = session.list_scopes()
    assert len(scopes) == 1
    assert scopes[0].scope_id == "scope-1"
    assert session.active_scope_id == "scope-1"


def test_session_add_scope_and_assign_signals() -> None:
    session = ScopeWorkbenchSession("ws-1")

    new_scope = session.add_scope("Control Scope")
    session.set_scope_signals(new_scope.scope_id, ["V(out)", "I(L)", "I(L)"])

    loaded = session.get_scope(new_scope.scope_id)
    assert loaded.name == "Control Scope"
    assert loaded.signal_keys == ["V(out)", "I(L)"]


def test_session_can_duplicate_scope_configuration() -> None:
    session = ScopeWorkbenchSession("ws-1")
    source_id = session.active_scope_id
    session.set_scope_signals(source_id, ["V(out)"])
    session.set_scope_plot_groups(source_id, {"V(out)": "V(out)"})
    session.set_scope_measurements(source_id, ["rms", "max"])
    session.set_scope_cursors(source_id, enabled=True, cursor_a=1e-6, cursor_b=2e-6)

    duplicated = session.duplicate_scope(source_id)
    loaded = session.get_scope(duplicated.scope_id)

    assert loaded.scope_id != source_id
    assert loaded.signal_keys == ["V(out)"]
    assert loaded.plot_groups == {"V(out)": "V(out)"}
    assert loaded.measurement_keys == ["rms", "max"]
    assert loaded.cursors_enabled is True
    assert loaded.cursor_a == 1e-6
    assert loaded.cursor_b == 2e-6


def test_session_can_ensure_explicit_scope_ids() -> None:
    session = ScopeWorkbenchSession("ws-1")
    ensured = session.ensure_scope("scope-explicit", "Explicit")

    assert ensured.scope_id == "scope-explicit"
    assert session.get_scope("scope-explicit").name == "Explicit"


def test_session_discard_scope_resets_last_scope_instead_of_removing() -> None:
    session = ScopeWorkbenchSession("ws-1")
    only_scope = session.active_scope_id
    session.set_scope_signals(only_scope, ["V(out)"])
    session.discard_scope(only_scope)

    restored = session.get_scope(only_scope)
    assert restored.signal_keys == []
    assert restored.name == "Scope 1"


def test_session_measurement_filter_and_fallback_defaults() -> None:
    session = ScopeWorkbenchSession("ws-1")
    scope_id = session.active_scope_id

    session.set_scope_measurements(scope_id, ["rms", "max", "invalid"])
    assert session.get_scope(scope_id).measurement_keys == ["rms", "max"]

    # Empty effective selection should restore default measurement set.
    session.set_scope_measurements(scope_id, ["invalid-only"])
    assert "rms" in session.get_scope(scope_id).measurement_keys
    assert "pkpk" in session.get_scope(scope_id).measurement_keys


def test_session_can_roundtrip_workspace_state() -> None:
    session = ScopeWorkbenchSession("ws-1")
    extra_scope = session.add_scope("Plant")
    session.set_scope_signals(extra_scope.scope_id, ["V(out)"])
    session.set_scope_plot_groups(extra_scope.scope_id, {"V(out)": "V(out)"})
    session.set_sidebar_collapsed(True)

    payload = session.export_state_dict()
    restored = ScopeWorkspaceState.from_dict(payload)

    assert restored.workspace_id == "ws-1"
    assert restored.sidebar_collapsed is True
    roundtrip_scope = next(
        scope for scope in restored.scopes if scope.scope_id == extra_scope.scope_id
    )
    assert roundtrip_scope.plot_groups == {"V(out)": "V(out)"}


def test_session_plot_groups_filter_unknown_signals() -> None:
    session = ScopeWorkbenchSession("ws-1")
    scope_id = session.active_scope_id
    session.set_scope_signals(scope_id, ["V(out)", "I(L)"])

    session.set_scope_plot_groups(
        scope_id,
        {
            "V(out)": "V(out)",
            "I(L)": "V(out)",
            "ghost": "V(out)",
            "V(out)-bad": "ghost",
        },
    )

    loaded = session.get_scope(scope_id)
    assert loaded.plot_groups == {"V(out)": "V(out)", "I(L)": "V(out)"}


def test_session_interval_target_valid_and_invalid() -> None:
    session = ScopeWorkbenchSession("ws-1")
    scope_id = session.active_scope_id

    for target in INTERVAL_TARGETS:
        session.set_scope_interval_target(scope_id, target)
        assert session.get_scope(scope_id).interval_target == target

    with pytest.raises(ValueError, match="Invalid interval target"):
        session.set_scope_interval_target(scope_id, "bad_target")


def test_session_saved_view_lifecycle() -> None:
    session = ScopeWorkbenchSession("ws-1")
    scope_id = session.active_scope_id

    assert session.list_saved_views(scope_id) == []

    view = session.add_saved_view(scope_id, "Startup", 0.0, 1e-3, y_min=-5.0, y_max=5.0)
    assert view.view_id == "view-1"
    assert view.name == "Startup"
    assert view.time_start == 0.0
    assert view.time_end == 1e-3
    assert view.y_min == -5.0
    assert view.y_max == 5.0

    view2 = session.add_saved_view(scope_id, "Steady State", 5e-3, 10e-3)
    assert view2.view_id == "view-2"
    assert view2.y_min is None

    listed = session.list_saved_views(scope_id)
    assert len(listed) == 2
    assert listed[0].view_id == "view-1"
    assert listed[1].view_id == "view-2"

    session.remove_saved_view(scope_id, "view-1")
    listed = session.list_saved_views(scope_id)
    assert len(listed) == 1
    assert listed[0].view_id == "view-2"

    with pytest.raises(KeyError):
        session.remove_saved_view(scope_id, "view-1")


def test_saved_view_roundtrip_serialization() -> None:
    view = SavedView(
        view_id="view-42",
        name="Test View",
        time_start=1.5e-3,
        time_end=3.0e-3,
        y_min=-10.0,
        y_max=10.0,
    )
    payload = view.to_dict()
    restored = SavedView.from_dict(payload)

    assert restored.view_id == view.view_id
    assert restored.name == view.name
    assert restored.time_start == view.time_start
    assert restored.time_end == view.time_end
    assert restored.y_min == view.y_min
    assert restored.y_max == view.y_max


def test_saved_view_roundtrip_without_y_bounds() -> None:
    view = SavedView(view_id="v1", name="NoY", time_start=0.0, time_end=1.0)
    restored = SavedView.from_dict(view.to_dict())
    assert restored.y_min is None
    assert restored.y_max is None


def test_saved_views_survive_workspace_roundtrip() -> None:
    session = ScopeWorkbenchSession("ws-2")
    scope_id = session.active_scope_id
    session.add_saved_view(scope_id, "View A", 0.0, 1e-3)
    session.add_saved_view(scope_id, "View B", 2e-3, 4e-3, y_min=-1.0, y_max=1.0)

    payload = session.export_state_dict()
    restored_ws = ScopeWorkspaceState.from_dict(payload)
    restored_scope = restored_ws.scopes[0]

    assert len(restored_scope.saved_views) == 2
    assert restored_scope.saved_views[0].name == "View A"
    assert restored_scope.saved_views[1].y_min == -1.0


def test_interval_target_survives_workspace_roundtrip() -> None:
    session = ScopeWorkbenchSession("ws-3")
    scope_id = session.active_scope_id
    session.set_scope_interval_target(scope_id, "cursor_a")

    payload = session.export_state_dict()
    restored = ScopeWorkspaceState.from_dict(payload)
    assert restored.scopes[0].interval_target == "cursor_a"


def test_default_measurement_keys_are_exported() -> None:
    assert "rms" in DEFAULT_MEASUREMENT_KEYS
    assert "min" in DEFAULT_MEASUREMENT_KEYS
    assert "max" in DEFAULT_MEASUREMENT_KEYS
    assert "pkpk" in DEFAULT_MEASUREMENT_KEYS


def test_session_can_persist_and_restore_through_adapter() -> None:
    adapter = _FakeAdapter()
    session = ScopeWorkbenchSession.from_adapter("ws-1", adapter)

    assert [sig.signal_key for sig in session.list_signal_catalog()] == ["V(out)", "I(L)"]

    added = session.add_scope("Thermal")
    session.set_scope_signals(added.scope_id, ["V(out)"])
    session.save_via_adapter(adapter)

    reloaded = ScopeWorkbenchSession.from_adapter("ws-1", adapter)
    assert any(scope.name == "Thermal" for scope in reloaded.list_scopes())
