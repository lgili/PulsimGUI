"""Selection accent follows the theme token (redesign slice 4).

Component and wire selection previously hardcoded ``QColor(59, 130,
246)`` — the studio theme's ``schematic_selection`` (#4d9fff) never
reached the canvas. ``SchematicScene.set_selection_color`` now writes
the class attributes on both item families from the theme, and the
selected-component visual gained the mock's four corner handles.
"""

from __future__ import annotations

import pytest
from PySide6.QtGui import QColor

from pulsimgui.views.schematic.items import ComponentItem, WireItem
from pulsimgui.views.schematic.items import symbol_style as style
from pulsimgui.views.schematic.scene import SchematicScene


@pytest.fixture
def scene(qapp):
    return SchematicScene()


def test_set_selection_color_reaches_both_item_families(scene):
    accent = QColor("#4d9fff")
    scene.set_selection_color(accent)

    assert ComponentItem.SELECTED_COLOR.name() == "#4d9fff"
    assert WireItem.SELECTED_COLOR.name() == "#4d9fff"
    # Derived translucencies keep the established look.
    assert ComponentItem.SELECTED_FILL.name() == "#4d9fff"
    assert ComponentItem.SELECTED_FILL.alpha() == 30
    assert WireItem.SELECTED_GLOW.alpha() == 60


def test_set_selection_color_is_restylable(scene):
    scene.set_selection_color(QColor("#4d9fff"))
    scene.set_selection_color(QColor("#33b1ff"))
    assert ComponentItem.SELECTED_COLOR.name() == "#33b1ff"
    assert WireItem.SELECTED_COLOR.name() == "#33b1ff"


def test_selection_handle_token_exists():
    # The corner-handle size is a symbol_style token, not a magic
    # number inside the paint method.
    assert style.SELECTION_HANDLE > 0


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
