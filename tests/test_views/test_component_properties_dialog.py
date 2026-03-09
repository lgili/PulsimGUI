"""Tests for ComponentPropertiesDialog sizing behavior."""

from PySide6.QtWidgets import QAbstractButton

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.dialogs.component_properties_dialog import ComponentPropertiesDialog


def test_cblock_dialog_uses_double_width_layout(qapp) -> None:
    component = Component(type=ComponentType.C_BLOCK, name="CB1")
    dialog = ComponentPropertiesDialog(component=component)

    assert dialog.width() == 900
    assert dialog.minimumWidth() == 840


def test_non_cblock_dialog_keeps_default_size(qapp) -> None:
    component = Component(type=ComponentType.RESISTOR, name="R1")
    dialog = ComponentPropertiesDialog(component=component)

    assert dialog.width() == 450
    assert dialog.minimumWidth() == 420


def test_dialog_includes_help_button(qapp) -> None:
    component = Component(type=ComponentType.RESISTOR, name="R1")
    dialog = ComponentPropertiesDialog(component=component)

    labels = {button.text() for button in dialog.findChildren(QAbstractButton)}
    assert "Help" in labels
