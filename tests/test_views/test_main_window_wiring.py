"""Regression tests for MainWindow wire-domain validation."""

from __future__ import annotations

from PySide6.QtCore import QPointF

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireConnection, WireSegment
from pulsimgui.views.main_window import MainWindow


def _connect_pins(
    circuit,
    left: Component,
    left_pin: int,
    right: Component,
    right_pin: int,
) -> Wire:
    """Create a wire with endpoint metadata between two component pins."""
    x1, y1 = left.get_pin_position(left_pin)
    x2, y2 = right.get_pin_position(right_pin)
    wire = Wire(
        segments=[WireSegment(x1, y1, x2, y2)],
        start_connection=WireConnection(component_id=left.id, pin_index=left_pin),
        end_connection=WireConnection(component_id=right.id, pin_index=right_pin),
    )
    circuit.add_wire(wire)
    return wire


def test_scope_pin_can_tap_existing_control_wire(qapp) -> None:
    """Scope pins should accept tapping from a signal wire segment."""
    window = MainWindow()
    try:
        circuit = window._current_circuit()
        controller = Component(type=ComponentType.PI_CONTROLLER, name="PI1", x=100.0, y=100.0)
        pwm = Component(type=ComponentType.PWM_GENERATOR, name="PWM1", x=260.0, y=100.0)
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1", x=260.0, y=160.0)
        circuit.add_component(controller)
        circuit.add_component(pwm)
        circuit.add_component(scope)

        signal_wire = _connect_pins(circuit, controller, 1, pwm, 1)
        segment = signal_wire.segments[0]
        tap = QPointF((segment.x1 + segment.x2) / 2.0, (segment.y1 + segment.y2) / 2.0)
        scope_pin = QPointF(*scope.get_pin_position(0))

        assert window._is_valid_wire_measurement_connection(
            (scope, 0),
            None,
            start_pos=scope_pin,
            end_pos=tap,
        )
    finally:
        window.close()


def test_scope_pin_rejects_unconnected_control_tap_point(qapp) -> None:
    """Scope pins should still reject points that are not on existing compatible wires."""
    window = MainWindow()
    try:
        circuit = window._current_circuit()
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1", x=260.0, y=160.0)
        circuit.add_component(scope)

        scope_pin = QPointF(*scope.get_pin_position(0))
        floating_point = QPointF(999.0, 999.0)
        assert not window._is_valid_wire_measurement_connection(
            (scope, 0),
            None,
            start_pos=scope_pin,
            end_pos=floating_point,
        )
    finally:
        window.close()


def test_goto_from_pins_accept_circuit_and_signal_domains(qapp) -> None:
    """Goto/From pins should connect with both electrical and control domains."""
    window = MainWindow()
    try:
        circuit = window._current_circuit()
        goto = Component(type=ComponentType.GOTO_LABEL, name="G1", x=180.0, y=120.0)
        from_label = Component(type=ComponentType.FROM_LABEL, name="F1", x=260.0, y=120.0)
        resistor = Component(type=ComponentType.RESISTOR, name="R1", x=100.0, y=120.0)
        controller = Component(type=ComponentType.PI_CONTROLLER, name="PI1", x=340.0, y=120.0)
        circuit.add_component(goto)
        circuit.add_component(from_label)
        circuit.add_component(resistor)
        circuit.add_component(controller)

        assert window._is_valid_wire_measurement_connection((goto, 0), (resistor, 1))
        assert window._is_valid_wire_measurement_connection((resistor, 1), (goto, 0))
        assert window._is_valid_wire_measurement_connection((from_label, 0), (controller, 0))
        assert window._is_valid_wire_measurement_connection((controller, 0), (from_label, 0))
    finally:
        window.close()
