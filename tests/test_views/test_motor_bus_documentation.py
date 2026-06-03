"""The motor SIG signal-bus channel list (order + key) is surfaced in three
discoverable places so the user can wire a SIGNAL_DEMUX → scope without
guessing:

  1. The PMSM canvas tooltip lists every output lane.
  2. The component Help dialog renders a bus table above the parameters.
  3. The wired SIGNAL_DEMUX is graphically labelled per output pin
     (rendered, asserted indirectly via the labelling helper).
"""
from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import (
    Component,
    ComponentType,
    MOTOR_SIGNAL_BUS_CHANNELS,
    MOTOR_SIGNAL_BUS_PIN_NAME,
)
from pulsimgui.models.wire import Wire, WireConnection, WireSegment


def test_pmsm_canvas_tooltip_lists_bus_order(qapp) -> None:
    from pulsimgui.views.schematic.items.component_item import create_component_item

    motor = Component(type=ComponentType.PMSM, name="M1")
    item = create_component_item(motor)
    tip = item.toolTip()

    assert MOTOR_SIGNAL_BUS_PIN_NAME in tip
    # Every channel suffix shows up in the tooltip.
    for suffix, _label in MOTOR_SIGNAL_BUS_CHANNELS:
        assert f"M1.{suffix}" in tip
    # First lane is OUT1, last is the highest.
    assert tip.index("OUT1") < tip.index(f"OUT{len(MOTOR_SIGNAL_BUS_CHANNELS)}")


def test_help_dialog_renders_motor_bus_table() -> None:
    from pulsimgui.views.dialogs.component_parameter_help_dialog import (
        _motor_signal_bus_section,
        render_component_help_html,
    )

    motor = Component(type=ComponentType.PMSM, name="M1")
    section = _motor_signal_bus_section(motor)
    # Every channel key is mentioned.
    for suffix, _label in MOTOR_SIGNAL_BUS_CHANNELS:
        assert f"M1.{suffix}" in section
    # And the full HTML embeds the section.
    full = render_component_help_html(motor)
    assert "OUT1" in full and "OUT7" in full
    assert "signal bus" in full.lower()


def test_help_dialog_no_bus_section_for_non_motor() -> None:
    from pulsimgui.views.dialogs.component_parameter_help_dialog import (
        _motor_signal_bus_section,
    )

    assert _motor_signal_bus_section(Component(type=ComponentType.RESISTOR)) == ""


def test_demux_lane_labels_resolve_when_wired_to_motor_sig(qapp) -> None:
    """The demux graphics helper returns the bus channel labels for each
    output when the demux IN is wired to a motor SIG pin (no lookup when
    unwired). This drives the per-output text shown on the canvas."""
    from pulsimgui.views.schematic.items.component_item import create_component_item

    circ = Circuit()
    motor = Component(type=ComponentType.PMSM, name="M1", x=0.0, y=0.0)
    demux = Component(
        type=ComponentType.SIGNAL_DEMUX, name="MotorBus", x=200.0, y=0.0,
        parameters={"output_count": 7},
    )
    for c in (motor, demux):
        circ.add_component(c)
    sig = next(i for i, p in enumerate(motor.pins) if p.name == MOTOR_SIGNAL_BUS_PIN_NAME)
    sx, sy = motor.get_pin_position(sig); ix, iy = demux.get_pin_position(0)
    circ.add_wire(Wire(
        segments=[WireSegment(sx, sy, ix, iy)],
        start_connection=WireConnection(component_id=motor.id, pin_index=sig),
        end_connection=WireConnection(component_id=demux.id, pin_index=0),
    ))

    # Build the demux item and attach to a scene exposing the circuit, the way
    # SchematicScene does. Then ask the item for its lane labels.
    from PySide6.QtWidgets import QGraphicsScene

    class _SceneWithCircuit(QGraphicsScene):
        circuit = circ

    scene = _SceneWithCircuit()
    item = create_component_item(demux)
    scene.addItem(item)
    output_pins = [p for p in demux.pins if p.name.startswith("OUT")]
    labels = item._motor_bus_lane_labels(output_pins)
    label_texts = [text for _pin, text in labels]
    expected = [label for _suffix, label in MOTOR_SIGNAL_BUS_CHANNELS]
    assert label_texts == expected
