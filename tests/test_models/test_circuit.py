"""Tests for Circuit model."""

import pytest

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire, WireSegment


class TestCircuit:
    def test_create_circuit(self):
        circuit = Circuit(name="test")
        assert circuit.name == "test"
        assert len(circuit.components) == 0
        assert len(circuit.wires) == 0

    def test_add_component(self):
        circuit = Circuit()
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        circuit.add_component(comp)

        assert comp.id in circuit.components
        assert circuit.get_component(comp.id) == comp

    def test_auto_name_generation(self):
        circuit = Circuit()

        r1 = Component(type=ComponentType.RESISTOR)
        circuit.add_component(r1)
        assert r1.name == "R1"

        r2 = Component(type=ComponentType.RESISTOR)
        circuit.add_component(r2)
        assert r2.name == "R2"

        c1 = Component(type=ComponentType.CAPACITOR)
        circuit.add_component(c1)
        assert c1.name == "C1"

    def test_get_component_by_name(self):
        circuit = Circuit()
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        circuit.add_component(comp)

        found = circuit.get_component_by_name("R1")
        assert found == comp

        not_found = circuit.get_component_by_name("R2")
        assert not_found is None

    def test_remove_component(self):
        circuit = Circuit()
        comp = Component(type=ComponentType.RESISTOR, name="R1")
        circuit.add_component(comp)

        removed = circuit.remove_component(comp.id)
        assert removed == comp
        assert comp.id not in circuit.components

    def test_add_wire(self):
        circuit = Circuit()
        wire = Wire()
        wire.add_segment(0, 0, 100, 0)
        circuit.add_wire(wire)

        assert wire.id in circuit.wires

    def test_clear(self):
        circuit = Circuit()
        circuit.add_component(Component(type=ComponentType.RESISTOR))
        circuit.add_wire(Wire())

        circuit.clear()
        assert len(circuit.components) == 0
        assert len(circuit.wires) == 0

    def test_serialization(self):
        circuit = Circuit(name="test_circuit")
        r1 = Component(type=ComponentType.RESISTOR, name="R1", x=100, y=100)
        c1 = Component(type=ComponentType.CAPACITOR, name="C1", x=200, y=100)
        circuit.add_component(r1)
        circuit.add_component(c1)

        wire = Wire()
        wire.add_segment(130, 100, 180, 100)
        circuit.add_wire(wire)

        data = circuit.to_dict()
        assert data["name"] == "test_circuit"
        assert len(data["components"]) == 2
        assert len(data["wires"]) == 1

        restored = Circuit.from_dict(data)
        assert restored.name == circuit.name
        assert len(restored.components) == 2
        assert len(restored.wires) == 1
        assert r1.id in restored.components

    def test_iter_components(self):
        circuit = Circuit()
        circuit.add_component(Component(type=ComponentType.RESISTOR, name="R1"))
        circuit.add_component(Component(type=ComponentType.CAPACITOR, name="C1"))

        names = [c.name for c in circuit.iter_components()]
        assert "R1" in names
        assert "C1" in names
