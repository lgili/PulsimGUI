"""Tests for standalone scope workbench session state."""

from __future__ import annotations

from pulsimgui.scope_workbench import (
    ScopeSampleBatch,
    ScopeSignalDescriptor,
    ScopeWorkbenchSession,
    ScopeWorkspaceState,
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


def test_session_can_persist_and_restore_through_adapter() -> None:
    adapter = _FakeAdapter()
    session = ScopeWorkbenchSession.from_adapter("ws-1", adapter)

    assert [sig.signal_key for sig in session.list_signal_catalog()] == ["V(out)", "I(L)"]

    added = session.add_scope("Thermal")
    session.set_scope_signals(added.scope_id, ["V(out)"])
    session.save_via_adapter(adapter)

    reloaded = ScopeWorkbenchSession.from_adapter("ws-1", adapter)
    assert any(scope.name == "Thermal" for scope in reloaded.list_scopes())
