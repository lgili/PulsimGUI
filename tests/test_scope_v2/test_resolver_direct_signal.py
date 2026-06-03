"""A scope channel may name a result signal directly (``"signal"`` in its
config) instead of being wired to a probe — used to plot device observer
traces (motor speed, phase currents, d-q) that aren't electrical nodes.

These resolve to a post-sim spec carrying that exact key, with no live spec
(observer traces aren't in the kernel state vector, so they appear when the
run finishes).
"""
from __future__ import annotations

from pulsimgui.models.circuit import Circuit
from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.scope_v2.resolver import resolve_scope_signal_specs


def _scope(channels: list[tuple[str, str]]) -> tuple[Component, Circuit]:
    circ = Circuit()
    scope = Component(
        type=ComponentType.ELECTRICAL_SCOPE,
        name="S",
        parameters={
            "channel_count": len(channels),
            "channels": [{"label": lbl, "signal": sig} for lbl, sig in channels],
        },
    )
    circ.add_component(scope)
    return scope, circ


def test_direct_signal_channel_resolves_to_named_key() -> None:
    scope, circ = _scope([("Speed", "M1.speed_rpm"), ("i_a", "M1.i_a")])
    live, post = resolve_scope_signal_specs(scope, circ, None, None)

    assert [p.signal_key for p in post] == ["M1.speed_rpm", "M1.i_a"]
    assert [p.name for p in post] == ["Speed", "i_a"]
    # Direct signals are post-sim only — not in the live state vector.
    assert live == []


def test_label_falls_back_to_signal_name() -> None:
    scope, circ = _scope([("", "M1.i_q")])
    _, post = resolve_scope_signal_specs(scope, circ, None, None)

    assert post[0].name == "M1.i_q"
    assert post[0].signal_key == "M1.i_q"


def test_blank_signal_is_ignored() -> None:
    # A channel with an empty/whitespace signal falls through to normal
    # wire-binding resolution (and, unwired, contributes no spec).
    scope, circ = _scope([("idle", "   ")])
    _, post = resolve_scope_signal_specs(scope, circ, None, None)
    assert post == []
