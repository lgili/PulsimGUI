"""PMSM exposes a SIG signal-bus output pin.

The pin carries the motor's full observable bus (speed / currents / torque)
and is a signal-domain output that connects to a SIGNAL_DEMUX → scope.
Motors saved before this feature gain the pin on load (idempotent).
"""
from __future__ import annotations

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_CIRCUIT,
    CONNECTION_DOMAIN_SIGNAL,
    MOTOR_SIGNAL_BUS_CHANNELS,
    MOTOR_SIGNAL_BUS_PIN_NAME,
    Component,
    ComponentType,
    is_motor_signal_bus_pin,
    is_signal_scope_source_pin,
    pin_connection_domain,
    supports_motor_signal_bus,
)


def _sig_index(component: Component) -> int:
    return next(
        i for i, p in enumerate(component.pins) if p.name == MOTOR_SIGNAL_BUS_PIN_NAME
    )


def test_supports_motor_signal_bus_for_pmsm() -> None:
    assert supports_motor_signal_bus(ComponentType.PMSM)
    assert not supports_motor_signal_bus(ComponentType.RESISTOR)


def test_pmsm_fresh_has_signal_bus_pin() -> None:
    motor = Component(type=ComponentType.PMSM, name="M1")
    pin_names = [p.name for p in motor.pins]
    assert pin_names == ["A", "B", "C", "N", MOTOR_SIGNAL_BUS_PIN_NAME]


def test_signal_bus_pin_is_signal_domain_and_scope_source() -> None:
    motor = Component(type=ComponentType.PMSM, name="M1")
    sig = _sig_index(motor)
    assert is_motor_signal_bus_pin(motor, sig)
    assert pin_connection_domain(motor, sig) == CONNECTION_DOMAIN_SIGNAL
    assert is_signal_scope_source_pin(motor, sig)


def test_electrical_terminals_stay_circuit_domain() -> None:
    motor = Component(type=ComponentType.PMSM, name="M1")
    for i, expected in enumerate(("A", "B", "C", "N")):
        assert motor.pins[i].name == expected
        assert pin_connection_domain(motor, i) == CONNECTION_DOMAIN_CIRCUIT
        assert not is_motor_signal_bus_pin(motor, i)


def test_legacy_four_pin_pmsm_gains_signal_bus_on_load() -> None:
    """A motor saved with the old 4-pin layout (no SIG) gets the SIG pin
    on load, AND its four original electrical terminals get migrated
    from the old ±25 / ±30 offsets to the current ±20 / ±40 grid layout
    — wires connected to the saved coordinates pick up the same snap
    via ``SchematicScene._normalize_circuit_geometry`` so the
    connection survives.
    """
    data = {
        "id": "11111111-1111-1111-1111-111111111111",
        "type": "PMSM",
        "name": "M1",
        "x": 0.0,
        "y": 0.0,
        "rotation": 0,
        "mirrored_h": False,
        "mirrored_v": False,
        "parameters": {},
        "pins": [
            {"index": 0, "name": "A", "x": -30.0, "y": -25.0},
            {"index": 1, "name": "B", "x": -30.0, "y": 0.0},
            {"index": 2, "name": "C", "x": -30.0, "y": 25.0},
            {"index": 3, "name": "N", "x": 30.0, "y": 0.0},
        ],
    }
    motor = Component.from_dict(data)
    coords = {p.name: (p.x, p.y) for p in motor.pins}
    # All four electrical terminals migrated to the current grid-aligned
    # layout (±25 → ±20, ±30 → ±40).
    assert coords["A"] == (-40.0, -20.0)
    assert coords["B"] == (-40.0, 0.0)
    assert coords["C"] == (-40.0, 20.0)
    assert coords["N"] == (40.0, 0.0)
    # SIG pin added at its template position.
    assert MOTOR_SIGNAL_BUS_PIN_NAME in coords


def test_bus_channel_definitions_match_backend_signals() -> None:
    """Every advertised bus channel must follow the ``<motor>.<suffix>``
    naming the backend publishes in ``_merge_motor_observer_signals``."""
    suffixes = [suffix for suffix, _label in MOTOR_SIGNAL_BUS_CHANNELS]
    assert suffixes == ["speed_rpm", "i_a", "i_b", "i_c", "i_d", "i_q", "torque"]
