"""Tests for SchematicView keyboard shortcut behaviors."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.schematic.items import create_component_item
from pulsimgui.views.schematic.scene import SchematicScene
from pulsimgui.views.schematic.view import SchematicView


def _build_view_with_selected_component() -> tuple[SchematicView, Component]:
    scene = SchematicScene()
    view = SchematicView(scene)
    component = Component(type=ComponentType.RESISTOR, name="R1")
    item = create_component_item(component)
    scene.addItem(item)
    item.setSelected(True)
    return view, component


def test_space_rotates_selected_component_clockwise(qapp) -> None:
    """Space should rotate selected components clockwise."""
    view, component = _build_view_with_selected_component()
    try:
        rotations: list[tuple[str, int]] = []
        view.component_rotate_requested.connect(
            lambda component_id, degrees: rotations.append((component_id, degrees))
        )

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        view.keyPressEvent(event)

        assert rotations == [(str(component.id), 90)]
    finally:
        view.close()


def test_space_prefers_wire_preview_toggle_over_rotation(qapp, monkeypatch) -> None:
    """Space should keep wire preview behavior when drawing a wire."""
    view, _component = _build_view_with_selected_component()
    try:
        rotations: list[tuple[str, int]] = []
        view.component_rotate_requested.connect(
            lambda component_id, degrees: rotations.append((component_id, degrees))
        )

        toggles: list[bool] = []

        class _Preview:
            def toggle_direction(self) -> None:
                toggles.append(True)

        monkeypatch.setattr(view, "_get_wire_preview", lambda: _Preview())

        event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)
        view.keyPressEvent(event)

        assert toggles == [True]
        assert rotations == []
    finally:
        view.close()
