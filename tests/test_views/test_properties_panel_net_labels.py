"""Tests for Goto/From pair navigation actions in properties UI."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.dialogs.component_properties_dialog import ComponentPropertiesDialog
from pulsimgui.views.properties import PropertiesPanel


def test_properties_panel_emits_pair_navigation_for_goto_label(qapp) -> None:
    panel = PropertiesPanel()
    component = Component(type=ComponentType.GOTO_LABEL, name="G1")
    component.parameters["net_label"] = "BUS_CTRL"
    panel.set_component(component)

    assert panel._net_label_pair_btn is not None
    assert not panel._net_label_pair_btn.isHidden()

    captured: list[tuple[str, str]] = []
    panel.net_label_pair_requested.connect(lambda cid, label: captured.append((cid, label)))
    panel._net_label_pair_btn.click()

    assert captured == [(str(component.id), "BUS_CTRL")]
    assert panel._name_field_label is not None
    assert panel._name_field_label.text() == "Net Label:"
    assert panel._name_edit.text() == "BUS_CTRL"
    assert "net_label" not in panel._widgets


def test_properties_panel_hides_pair_navigation_for_non_router_components(qapp) -> None:
    panel = PropertiesPanel()
    component = Component(type=ComponentType.RESISTOR, name="R1")
    panel.set_component(component)

    assert panel._net_label_pair_btn is not None
    assert panel._net_label_pair_btn.isHidden()
    assert not panel._params_container.isHidden()


def test_component_properties_dialog_records_pair_navigation_request(qapp) -> None:
    component = Component(type=ComponentType.FROM_LABEL, name="F1")
    component.parameters["net_label"] = "BUS_A"
    dialog = ComponentPropertiesDialog(component=component)

    assert dialog._panel._net_label_pair_btn is not None
    dialog._panel._net_label_pair_btn.click()

    assert dialog.pair_navigation_request == (str(component.id), "BUS_A")
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_properties_panel_name_field_updates_net_label_for_router_components(qapp) -> None:
    panel = PropertiesPanel()
    component = Component(type=ComponentType.GOTO_LABEL, name="G1")
    component.parameters["net_label"] = "OLD"
    panel.set_component(component)

    panel._name_edit.setText("NEW_BUS")
    panel._on_name_changed()

    assert component.parameters["net_label"] == "NEW_BUS"
    assert component.name == "NEW_BUS"


def test_properties_panel_hides_empty_params_section_for_router_labels(qapp) -> None:
    panel = PropertiesPanel()
    component = Component(type=ComponentType.GOTO_LABEL, name="G1")
    component.parameters["net_label"] = "BUS_CTRL"
    panel.set_component(component)

    assert panel._params_container.isHidden()
