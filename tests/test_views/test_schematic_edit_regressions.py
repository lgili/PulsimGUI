"""Regression tests for schematic-editing bugs caught in the pre-release
QA audit.

1. Quick-add (Ctrl+K palette / keyboard) built ``Component(comp_type, ...)``
   positionally — but Component's first field is ``id: UUID``, so the type
   landed in ``id`` and every quick-added part was silently a RESISTOR with
   a non-UUID id (which then broke right-click edit/delete and collided on
   the dict key). Masked because tests only ever quick-added RESISTOR.

2. Copy/paste added the pasted item to the QGraphicsScene only, never to
   ``circuit.components`` — so it vanished on the next scene reload / tab
   switch / save / simulate (silent data loss).

3. ``SettingsService.remove_recent_project`` was called but never defined,
   so stale-recent-file pruning was dead (swallowed by a bare except).
"""
from __future__ import annotations

from uuid import UUID

import pytest

from pulsimgui.models.component import ComponentType
from pulsimgui.services.settings_service import SettingsService
from pulsimgui.views.main_window import MainWindow


@pytest.fixture(autouse=True)
def _no_close_prompt(monkeypatch):
    """Stub the save-on-close prompt so dirty windows tear down headlessly."""
    monkeypatch.setattr(MainWindow, "_check_save_all", lambda self: True)


# ---------------------------------------------------------------------------
# 1. Quick-add component type/id
# ---------------------------------------------------------------------------
def test_quick_add_uses_requested_type_and_valid_uuid(qapp) -> None:
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.CAPACITOR, 0.0, 0.0)
        comps = list(window._current_circuit().components.values())
        assert len(comps) == 1
        added = comps[0]
        # The bug bound comp_type to `id` and left `type` defaulted to RESISTOR.
        assert added.type == ComponentType.CAPACITOR
        assert isinstance(added.id, UUID)
        assert added.name  # a name like "C1" was generated, not left blank
    finally:
        window.close()


def test_quick_add_same_type_twice_does_not_collide(qapp) -> None:
    """Two quick-adds of the same type must yield two distinct components
    (the bug gave both the same non-UUID id → second overwrote the first)."""
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.INDUCTOR, 0.0, 0.0)
        window._add_component_at(ComponentType.INDUCTOR, 100.0, 0.0)
        comps = list(window._current_circuit().components.values())
        assert len(comps) == 2
        ids = {c.id for c in comps}
        assert len(ids) == 2  # distinct UUIDs
        assert all(isinstance(c.id, UUID) for c in comps)
        assert all(c.type == ComponentType.INDUCTOR for c in comps)
    finally:
        window.close()


# ---------------------------------------------------------------------------
# 2. Paste persists into the circuit model
# ---------------------------------------------------------------------------
def _component_items(scene):
    from pulsimgui.views.schematic.items import ComponentItem

    return [it for it in scene.items() if isinstance(it, ComponentItem)]


def test_paste_adds_component_to_model_and_survives_reload(qapp) -> None:
    from PySide6.QtCore import QPointF

    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        assert len(window._current_circuit().components) == 1

        view = window._schematic_view
        scene = window._schematic_scene
        items = _component_items(scene)
        assert len(items) == 1

        # Copy the existing component, then paste at a new position.
        view._copy_component(items[0])
        view._paste_component(QPointF(120.0, 40.0))

        # Pasted component must be in the MODEL (not a scene-only orphan).
        assert len(window._current_circuit().components) == 2

        # ...and it must survive a scene rebuild (tab switch / save / sim all
        # reload the scene from the model).
        window._load_project_to_scene()
        assert len(window._current_circuit().components) == 2
        assert len(_component_items(window._schematic_scene)) == 2
    finally:
        window.close()


def test_paste_is_undoable(qapp) -> None:
    from PySide6.QtCore import QPointF

    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        view = window._schematic_view
        items = _component_items(window._schematic_scene)
        view._copy_component(items[0])
        view._paste_component(QPointF(120.0, 40.0))
        assert len(window._current_circuit().components) == 2

        # Paste went through the command stack, so undo removes it.
        assert window._command_stack.can_undo
        window._on_undo()
        assert len(window._current_circuit().components) == 1
    finally:
        window.close()


# ---------------------------------------------------------------------------
# 3. SettingsService.remove_recent_project
# ---------------------------------------------------------------------------
def test_remove_recent_project(tmp_path) -> None:
    settings = SettingsService()
    saved = settings.get_recent_projects()  # snapshot to restore after
    try:
        settings.clear_recent_projects()
        a = tmp_path / "a.pulsim"
        b = tmp_path / "b.pulsim"
        settings.add_recent_project(str(a))
        settings.add_recent_project(str(b))
        assert len(settings.get_recent_projects()) == 2

        settings.remove_recent_project(str(a))
        remaining = settings.get_recent_projects()
        assert str(a.resolve()) not in remaining
        assert str(b.resolve()) in remaining

        # Removing a path that isn't present is a harmless no-op.
        settings.remove_recent_project(str(tmp_path / "never.pulsim"))
        assert settings.get_recent_projects() == remaining
    finally:
        settings.clear_recent_projects()
        for p in saved:
            settings.add_recent_project(p)
