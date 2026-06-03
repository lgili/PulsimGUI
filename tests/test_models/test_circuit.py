"""Tests for Circuit model."""


from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.models.wire import Wire


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


class TestDoubleRotationHeal:
    """Loading self-heals components whose 90°/270° rotation was double-applied.

    Such a part has its pins stored *already rotated* AND a non-zero
    ``rotation``; it renders with diagonal leads and its computed terminals
    land 90° away from the wires. ``Circuit.from_dict`` repairs it using the
    wires as ground truth — but only when un-rotating fully reconnects it.
    """

    from pulsimgui.models.component import Pin
    from pulsimgui.models.wire import WireSegment

    def _dict(self, *, rotation, pins, wire_endpoints):
        from pulsimgui.models.component import Component, ComponentType, Pin
        from pulsimgui.models.wire import Wire, WireSegment

        r = Component(
            type=ComponentType.RESISTOR, name="R1", x=0.0, y=0.0, rotation=rotation,
            pins=[Pin(i, n, x, y) for i, (n, x, y) in enumerate(pins)],
        )
        wires = [
            Wire(segments=[WireSegment(ex, ey, ex, ey - 60)]) for (ex, ey) in wire_endpoints
        ]
        return {
            "name": "t",
            "components": [r.to_dict()],
            "wires": [w.to_dict() for w in wires],
        }

    def _coords(self, comp):
        return sorted((round(p.x, 1), round(p.y, 1)) for p in comp.pins)

    def _terminals(self, comp):
        return sorted(
            tuple(round(v, 1) for v in comp.get_pin_position(i))
            for i in range(len(comp.pins))
        )

    def test_double_rotated_resistor_is_healed(self):
        # Pins stored vertical (0,±25) + rotation=90 → terminals compute to
        # (±25,0); wires are on the vertical axis at (0,±25). Component
        # post-init snaps every saved coord to the 20-px grid, so the
        # ±25 inputs land at ±20 in the rest of the assertions.
        data = self._dict(
            rotation=90,
            pins=[("1", 0.0, -25.0), ("2", 0.0, 25.0)],
            wire_endpoints=[(0.0, -25.0), (0.0, 25.0)],
        )
        circuit = Circuit.from_dict(data)
        r = next(iter(circuit.components.values()))
        # Pins un-rotated to canonical horizontal AND snapped to grid.
        assert self._coords(r) == [(-20.0, 0.0), (20.0, 0.0)]
        # Terminals now sit on the wires (also snapped).
        assert self._terminals(r) == [(0.0, -20.0), (0.0, 20.0)]

    def test_legit_rotated_component_is_untouched(self):
        # Canonical pins (±25,0) + rotation=90 → terminals (0,±25) already
        # on wires. The post-init snap moves ±25 to ±20 — rotation logic
        # leaves the pin axes alone.
        data = self._dict(
            rotation=90,
            pins=[("1", -25.0, 0.0), ("2", 25.0, 0.0)],
            wire_endpoints=[(0.0, -25.0), (0.0, 25.0)],
        )
        circuit = Circuit.from_dict(data)
        r = next(iter(circuit.components.values()))
        assert self._coords(r) == [(-20.0, 0.0), (20.0, 0.0)]

    def test_unwired_component_is_not_healed(self):
        # Same suspicious geometry but no wire near either orientation.
        # The rotation heal stays put (no wire evidence); the only
        # change is the post-init grid snap on the pin coordinates.
        data = self._dict(
            rotation=90,
            pins=[("1", 0.0, -25.0), ("2", 0.0, 25.0)],
            wire_endpoints=[(500.0, 500.0)],
        )
        circuit = Circuit.from_dict(data)
        r = next(iter(circuit.components.values()))
        assert self._coords(r) == [(0.0, -20.0), (0.0, 20.0)]

    def test_heal_is_idempotent(self):
        data = self._dict(
            rotation=90,
            pins=[("1", 0.0, -25.0), ("2", 0.0, 25.0)],
            wire_endpoints=[(0.0, -25.0), (0.0, 25.0)],
        )
        once = Circuit.from_dict(data)
        twice = Circuit.from_dict(once.to_dict())
        c1 = next(iter(once.components.values()))
        c2 = next(iter(twice.components.values()))
        assert self._coords(c1) == self._coords(c2)

    def test_count_returned(self):
        from pulsimgui.models.circuit import _heal_double_rotated_components

        # An already-healed circuit reports zero repairs (no-op).
        data = self._dict(
            rotation=90,
            pins=[("1", 0.0, -25.0), ("2", 0.0, 25.0)],
            wire_endpoints=[(0.0, -25.0), (0.0, 25.0)],
        )
        healed = Circuit.from_dict(data)
        assert _heal_double_rotated_components(healed) == 0
