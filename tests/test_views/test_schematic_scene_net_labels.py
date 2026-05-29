"""Tests for Goto/From label navigation in schematic scene."""

from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.schematic.scene import SchematicScene


def test_net_label_navigation_prefers_opposite_label_type(qapp) -> None:
    scene = SchematicScene()
    circuit = Circuit(name="net-label-nav")

    goto = Component(type=ComponentType.GOTO_LABEL, name="G_BUS", x=100.0, y=100.0)
    goto.parameters["net_label"] = "BUS_A"
    from_near = Component(type=ComponentType.FROM_LABEL, name="F_NEAR", x=200.0, y=100.0)
    from_near.parameters["net_label"] = "BUS_A"
    from_far = Component(type=ComponentType.FROM_LABEL, name="F_FAR", x=460.0, y=100.0)
    from_far.parameters["net_label"] = "BUS_A"

    circuit.add_component(goto)
    circuit.add_component(from_near)
    circuit.add_component(from_far)
    scene.circuit = circuit

    captured: list[tuple[str, str, str]] = []
    scene.net_label_navigation_requested.connect(
        lambda src, dst, label: captured.append((src, dst, label))
    )

    scene.request_net_label_navigation(goto)

    assert captured
    src_id, dst_id, label = captured[-1]
    assert src_id == str(goto.id)
    assert dst_id == str(from_near.id)
    assert label == "BUS_A"


def test_net_label_navigation_uses_component_name_when_net_label_is_blank(qapp) -> None:
    scene = SchematicScene()
    circuit = Circuit(name="net-label-nav-name-fallback")

    goto = Component(type=ComponentType.GOTO_LABEL, name="CTRL_BUS", x=120.0, y=120.0)
    from_label = Component(type=ComponentType.FROM_LABEL, name="CTRL_BUS", x=260.0, y=120.0)
    goto.parameters["net_label"] = ""
    from_label.parameters["net_label"] = ""

    circuit.add_component(goto)
    circuit.add_component(from_label)
    scene.circuit = circuit

    captured: list[tuple[str, str, str]] = []
    scene.net_label_navigation_requested.connect(
        lambda src, dst, label: captured.append((src, dst, label))
    )

    scene.request_net_label_navigation(goto)

    assert captured
    _src_id, dst_id, label = captured[-1]
    assert dst_id == str(from_label.id)
    assert label == "CTRL_BUS"
