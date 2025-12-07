"""Tests for Component model."""

import pytest
from uuid import UUID

from pulsimgui.models.component import Component, ComponentType, Pin


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
        # Pin at (-30, 0) rotated 90 degrees should be at (0, -30)
        x, y = comp.get_pin_position(0)
        assert abs(x - 0) < 0.001
        assert abs(y - (-30)) < 0.001

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
