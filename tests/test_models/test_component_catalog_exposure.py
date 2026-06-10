"""The palette must expose every component the backend can actually simulate
— and ONLY those.

Pins the W1.3 fix: 13 fully-modelled control/analog/probe components existed in
component.py (defaults + pins + converter lowering) but were missing from
COMPONENT_LIBRARY, so users could not place them at all. The 7 types the
converter does NOT lower yet (BJTs, thyristor, TRIAC, relay, fuse, breaker)
stay hidden until they simulate.
"""
from __future__ import annotations

from pulsimgui.models.component import (
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
    Component,
    ComponentType,
)
from pulsimgui.models.component_catalog import (
    COMPONENT_LIBRARY,
    QUICK_ADD_COMPONENTS,
)

_EXPOSED = {entry["type"] for group in COMPONENT_LIBRARY.values() for entry in group}

NEWLY_EXPOSED = {
    ComponentType.OP_AMP,
    ComponentType.COMPARATOR,
    ComponentType.PID_CONTROLLER,
    ComponentType.INTEGRATOR,
    ComponentType.DIFFERENTIATOR,
    ComponentType.RATE_LIMITER,
    ComponentType.HYSTERESIS,
    ComponentType.LOOKUP_TABLE,
    ComponentType.TRANSFER_FUNCTION,
    ComponentType.DELAY_BLOCK,
    ComponentType.SAMPLE_HOLD,
    ComponentType.STATE_MACHINE,
    ComponentType.POWER_PROBE,
}

NOT_YET_CONVERTIBLE = {
    ComponentType.BJT_NPN,
    ComponentType.BJT_PNP,
    ComponentType.THYRISTOR,
    ComponentType.TRIAC,
    ComponentType.RELAY,
    ComponentType.FUSE,
    ComponentType.CIRCUIT_BREAKER,
}


def test_simulatable_components_are_in_the_palette() -> None:
    missing = NEWLY_EXPOSED - _EXPOSED
    assert not missing, f"palette lost simulatable components: {missing}"


def test_non_convertible_components_stay_hidden() -> None:
    leaked = NOT_YET_CONVERTIBLE & _EXPOSED
    assert not leaked, (
        f"{leaked} are in the palette but the circuit converter does not "
        "lower them — placing one builds a circuit that fails to simulate."
    )


def test_every_palette_entry_is_buildable(qapp) -> None:
    """Every exposed type must have pins, defaults and a graphics item."""
    from pulsimgui.views.schematic.items import create_component_item

    for comp_type in sorted(_EXPOSED, key=lambda t: t.name):
        assert comp_type in DEFAULT_PINS, f"{comp_type.name}: no DEFAULT_PINS"
        assert comp_type in DEFAULT_PARAMETERS, (
            f"{comp_type.name}: no DEFAULT_PARAMETERS")
        component = Component(type=comp_type, name=f"X_{comp_type.name}")
        item = create_component_item(component)
        assert item is not None, f"{comp_type.name}: no graphics item"
        assert item.boundingRect().width() > 0


def test_newly_exposed_are_searchable_in_quick_add() -> None:
    quick_types = {ct for ct, _name, _aliases in QUICK_ADD_COMPONENTS}
    missing = NEWLY_EXPOSED - quick_types
    assert not missing, f"missing quick-add search entries: {missing}"
