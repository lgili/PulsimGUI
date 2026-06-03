"""A scope channel wired through a SIGNAL_DEMUX to a PMSM's SIG pin must
resolve to the per-channel backend signal (``M1.speed_rpm`` / ``M1.i_a`` …).

This is the wired workflow for plotting motor signals: motor.SIG carries
the full observable bus, the demux splits it into per-channel outputs, and
each scope channel taps one demux output.
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
from pulsimgui.views.scope_v2.resolver import resolve_scope_signal_specs


def _wire(circuit: Circuit, a: Component, ap: int, b: Component, bp: int) -> None:
    ax, ay = a.get_pin_position(ap)
    bx, by = b.get_pin_position(bp)
    circuit.add_wire(
        Wire(
            segments=[WireSegment(ax, ay, bx, by)],
            start_connection=WireConnection(component_id=a.id, pin_index=ap),
            end_connection=WireConnection(component_id=b.id, pin_index=bp),
        )
    )


def _sig_index(motor: Component) -> int:
    return next(i for i, p in enumerate(motor.pins) if p.name == MOTOR_SIGNAL_BUS_PIN_NAME)


def test_demux_lane_selects_motor_channel(qapp) -> None:
    """Each demux output lane k selects bus channel k (speed → torque)."""
    circ = Circuit()
    motor = Component(type=ComponentType.PMSM, name="M1", x=0.0, y=0.0)
    demux = Component(
        type=ComponentType.SIGNAL_DEMUX, name="MotorBus", x=200.0, y=0.0,
        parameters={"output_count": 7},
    )
    # One scope channel per bus lane.
    scope = Component(
        type=ComponentType.ELECTRICAL_SCOPE, name="Scope_All", x=600.0, y=0.0,
        parameters={
            "channel_count": 7,
            "channels": [{"label": f"ch{i}"} for i in range(7)],
        },
    )
    for c in (motor, demux, scope):
        circ.add_component(c)

    sig = _sig_index(motor)
    _wire(circ, motor, sig, demux, 0)  # M1.SIG -> DMX.IN
    # Demux pins are IN (0) then OUT1..OUT7 (1..7); wire OUTk to scope channel k-1.
    for k in range(7):
        _wire(circ, demux, k + 1, scope, k)

    _, post = resolve_scope_signal_specs(scope, circ, None, None)
    keys = [p.signal_key for p in post]
    expected = [f"M1.{suffix}" for suffix, _ in MOTOR_SIGNAL_BUS_CHANNELS]
    assert keys == expected
