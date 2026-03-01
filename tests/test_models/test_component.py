"""Tests for Component model."""

from pulsimgui.models.component import (
    CURRENT_PROBE_OUTPUT_PIN_NAME,
    Component,
    ComponentType,
    Pin,
    THERMAL_PORT_PARAMETER,
    THERMAL_PORT_PIN_NAME,
    VOLTAGE_PROBE_OUTPUT_PIN_NAME,
    can_connect_measurement_pins,
    set_thermal_port_enabled,
)


class TestPin:
    def test_create_pin(self):
        pin = Pin(index=0, name="A", x=10.0, y=20.0)
        assert pin.index == 0
        assert pin.name == "A"
        assert pin.x == 10.0
        assert pin.y == 20.0

    def test_pin_serialization(self):
        pin = Pin(index=1, name="B", x=-5.0, y=15.0)
        data = pin.to_dict()
        assert data["index"] == 1
        assert data["name"] == "B"

        restored = Pin.from_dict(data)
        assert restored.index == pin.index
        assert restored.name == pin.name
        assert restored.x == pin.x
        assert restored.y == pin.y


class TestComponent:
    def test_create_resistor(self):
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        assert comp.type == ComponentType.RESISTOR
        assert comp.name == "R1"
        assert len(comp.pins) == 2
        assert "resistance" in comp.parameters

    def test_create_mosfet(self):
        comp = Component(type=ComponentType.MOSFET_N, name="M1")
        assert comp.type == ComponentType.MOSFET_N
        assert len(comp.pins) == 3
        assert "vth" in comp.parameters

    def test_default_parameters(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert resistor.parameters["resistance"] == 1000.0

        cap = Component(type=ComponentType.CAPACITOR)
        assert cap.parameters["capacitance"] == 1e-6

    def test_pin_position_no_rotation(self):
        comp = Component(type=ComponentType.RESISTOR, x=100, y=200)
        x, y = comp.get_pin_position(0)
        assert x == 100 + comp.pins[0].x
        assert y == 200 + comp.pins[0].y

    def test_pin_position_with_rotation(self):
        comp = Component(type=ComponentType.RESISTOR, x=0, y=0, rotation=90)
        # 90-degree rotation maps local (x, y) -> (-y, x).
        pin = comp.pins[0]
        expected_x = -pin.y
        expected_y = pin.x
        x, y = comp.get_pin_position(0)
        assert abs(x - expected_x) < 0.001
        assert abs(y - expected_y) < 0.001

    def test_serialization(self):
        comp = Component(
            type=ComponentType.CAPACITOR,
            name="C1",
            x=50,
            y=100,
            rotation=180,
        )
        comp.parameters["capacitance"] = 10e-6

        data = comp.to_dict()
        assert data["type"] == "CAPACITOR"
        assert data["name"] == "C1"
        assert data["x"] == 50
        assert data["rotation"] == 180

        restored = Component.from_dict(data)
        assert restored.type == comp.type
        assert restored.name == comp.name
        assert restored.x == comp.x
        assert restored.rotation == comp.rotation
        assert restored.parameters["capacitance"] == 10e-6

    def test_uuid_preserved(self):
        comp = Component(type=ComponentType.RESISTOR)
        original_id = comp.id
        data = comp.to_dict()
        restored = Component.from_dict(data)
        assert restored.id == original_id

    def test_control_blocks_have_defaults(self):
        pi = Component(type=ComponentType.PI_CONTROLLER)
        assert len(pi.pins) == 2
        assert "kp" in pi.parameters and "ki" in pi.parameters

        pid = Component(type=ComponentType.PID_CONTROLLER)
        assert "kd" in pid.parameters

        math_block = Component(type=ComponentType.MATH_BLOCK)
        assert math_block.parameters["operation"] == "sum"

        pwm = Component(type=ComponentType.PWM_GENERATOR)
        assert len(pwm.pins) == 2
        assert pwm.parameters["frequency"] == 10000.0

        gain = Component(type=ComponentType.GAIN)
        assert len(gain.pins) == 2
        assert gain.parameters["gain"] == 1.0

        summing = Component(type=ComponentType.SUM)
        assert len(summing.pins) == 3
        assert summing.parameters["input_count"] == 2

        subtractor = Component(type=ComponentType.SUBTRACTOR)
        assert len(subtractor.pins) == 3
        assert subtractor.parameters["signs"] == ["+", "-"]

        # PWM exposes DUTY_IN for closed-loop signal control.
        assert pwm.pins[0].name == "OUT"
        assert pwm.pins[1].name == "DUTY_IN"

    def test_thermal_port_default_is_disabled(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is False
        assert all(pin.name != THERMAL_PORT_PIN_NAME for pin in resistor.pins)

    def test_thermal_port_toggle_updates_pin_layout(self):
        resistor = Component(type=ComponentType.RESISTOR)
        assert len(resistor.pins) == 2

        set_thermal_port_enabled(resistor, True)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is True
        assert len(resistor.pins) == 3
        assert resistor.pins[-1].name == THERMAL_PORT_PIN_NAME

        set_thermal_port_enabled(resistor, False)
        assert resistor.parameters[THERMAL_PORT_PARAMETER] is False
        assert len(resistor.pins) == 2
        assert all(pin.name != THERMAL_PORT_PIN_NAME for pin in resistor.pins)

    def test_thermal_port_not_exposed_for_unsupported_components(self):
        pi = Component(type=ComponentType.PI_CONTROLLER)
        assert THERMAL_PORT_PARAMETER not in pi.parameters

    def test_voltage_probe_has_scope_output_pin(self):
        probe = Component(type=ComponentType.VOLTAGE_PROBE)
        assert len(probe.pins) == 3
        assert probe.pins[2].name == VOLTAGE_PROBE_OUTPUT_PIN_NAME

    def test_current_probe_has_scope_output_pin(self):
        probe = Component(type=ComponentType.CURRENT_PROBE)
        assert len(probe.pins) == 3
        assert probe.pins[2].name == CURRENT_PROBE_OUTPUT_PIN_NAME

    def test_scope_connection_rules_for_electrical_probes(self):
        scope = Component(type=ComponentType.ELECTRICAL_SCOPE, name="ES1")
        v_probe = Component(type=ComponentType.VOLTAGE_PROBE, name="VP1")
        resistor = Component(type=ComponentType.RESISTOR, name="R1")

        assert can_connect_measurement_pins(scope, 0, v_probe, 2)
        assert not can_connect_measurement_pins(scope, 0, resistor, 0)

    def test_scope_connection_rules_for_thermal_outputs(self):
        scope = Component(type=ComponentType.THERMAL_SCOPE, name="TS1")
        resistor = Component(type=ComponentType.RESISTOR, name="R1")
        set_thermal_port_enabled(resistor, True)

        assert can_connect_measurement_pins(scope, 0, resistor, 2)
        assert not can_connect_measurement_pins(scope, 0, resistor, 1)
