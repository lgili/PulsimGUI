"""Tests for dynamic scope symbol sizing based on channel count."""

from __future__ import annotations

import pytest

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.schematic.items import create_component_item


@pytest.mark.parametrize(
    "scope_type",
    [ComponentType.ELECTRICAL_SCOPE, ComponentType.THERMAL_SCOPE],
)
def test_scope_body_grows_with_channel_count(qapp, scope_type: ComponentType) -> None:
    """Scope icon body should expand vertically when channel count increases."""
    low_count = Component(type=scope_type, parameters={"channel_count": 2})
    high_count = Component(type=scope_type, parameters={"channel_count": 6})

    low_item = create_component_item(low_count)
    high_item = create_component_item(high_count)

    low_body = low_item._scope_body_rect()
    high_body = high_item._scope_body_rect()

    assert high_body.height() > low_body.height()
    assert high_body.top() < low_body.top()
    assert high_body.bottom() > low_body.bottom()
