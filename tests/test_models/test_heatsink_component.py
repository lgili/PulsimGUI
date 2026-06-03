"""Tests for the SharedHeatsink (HEATSINK) component model.

The HEATSINK component is the GUI surface for pulsim 1.7's
``pulsim.thermal.SharedHeatsink`` — N devices coupled through one
heatsink-to-ambient resistance. The GUI carries the topology (n device
slots + ambient) and the sizing parameters; the converter +
backend (next commits) translate that into the actual pulsim API
calls.

These tests pin three things on the model layer:

  1. **Pins regenerate as the user changes ``n_devices``.** Saved
     files should migrate forward without manual cleanup; the
     `_synchronize_special_component` dispatch + the
     `_synchronize_heatsink` body do that.
  2. **Pin Y coordinates never collide after the grid snap.** Picking
     a continuous span and rounding to the 20-unit grid (the previous
     attempt) silently overlapped pins at higher n; we now lay them on
     a strict 20-unit step.
  3. **The thermal-domain tag covers every pin.** Without this the
     wire validator would let the user drop an electrical wire onto a
     thermal port — semantically wrong and the converter would later
     produce a confusing error.
"""
from __future__ import annotations

import pytest

from pulsimgui.models.component import (
    CONNECTION_DOMAIN_THERMAL,
    DEFAULT_PARAMETERS,
    DEFAULT_PINS,
    Component,
    ComponentType,
    _synchronize_special_component,
    pin_connection_domain,
)


def test_heatsink_default_layout_has_amb_plus_four_dev_pins() -> None:
    pins = DEFAULT_PINS[ComponentType.HEATSINK]
    names = [p.name for p in pins]
    assert names == ["AMB", "DEV1", "DEV2", "DEV3", "DEV4"]


def test_heatsink_default_parameters_match_runtime_contract() -> None:
    """The five params the converter + backend will read in the next
    commits are present and have engineering-sensible defaults."""
    params = DEFAULT_PARAMETERS[ComponentType.HEATSINK]
    assert params["n_devices"] == 4
    assert params["R_th_sink_to_amb_K_per_W"] == pytest.approx(5.0)
    assert params["C_th_sink_J_per_K"] == pytest.approx(0.0)
    assert params["T_amb_C"] == pytest.approx(25.0)
    assert params["case_to_sink_R_th_csv"] == ""


@pytest.mark.parametrize(
    "n, expected_dev_ys",
    [
        (1, [0]),
        (2, [-20, 20]),
        (3, [-20, 0, 20]),
        # n=4: gap at y=0 (skip the AMB row); pins on the 20-unit grid.
        (4, [-40, -20, 20, 40]),
        (5, [-40, -20, 0, 20, 40]),
        (6, [-60, -40, -20, 20, 40, 60]),
        (8, [-80, -60, -40, -20, 20, 40, 60, 80]),
    ],
)
def test_sync_regenerates_device_pins_without_collision(
    n: int, expected_dev_ys: list[int],
) -> None:
    """Bumping ``n_devices`` rebuilds the pin layout. Adjacent pins
    always sit ≥ 20 units apart so the snap pass can't drop two on
    the same coordinate — the previous attempt at a continuous span
    did exactly that for n ≥ 6."""
    component = Component(type=ComponentType.HEATSINK, name="HS")
    component.parameters["n_devices"] = n
    _synchronize_special_component(component)

    # AMB stays at index 0 and at (-40, 0); DEV pins start at index 1.
    assert component.pins[0].name == "AMB"
    dev_pins = component.pins[1:]
    assert len(dev_pins) == n, "DEV pin count must match n_devices"
    for idx, (pin, expected_y) in enumerate(
        zip(dev_pins, expected_dev_ys), start=1,
    ):
        assert pin.name == f"DEV{idx}"
        assert pin.x == 40
        assert pin.y == expected_y
    # Strict step-of-20 spacing — guard the no-overlap rule explicitly.
    ys = sorted(p.y for p in dev_pins)
    diffs = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
    for diff in diffs:
        assert diff >= 20, f"adjacent DEV pins {diff} units apart < grid"


def test_sync_clamps_n_devices_to_1_8_window() -> None:
    """The pin layout becomes unreadable outside [1, 8]; the sync
    rounds out-of-range values into the supported window so the user
    can't accidentally produce a 50-pin block from a stray edit."""
    for raw, expected in (
        (0, 1),
        (-3, 1),
        (10, 8),
        (None, 4),  # falsy → default 4
        ("garbage", 4),
    ):
        c = Component(type=ComponentType.HEATSINK, name="HS")
        c.parameters["n_devices"] = raw
        _synchronize_special_component(c)
        assert c.parameters["n_devices"] == expected
        dev_count = sum(1 for p in c.pins if p.name.startswith("DEV"))
        assert dev_count == expected


def test_every_heatsink_pin_is_thermal_domain() -> None:
    """The wire-domain validator uses ``pin_connection_domain`` to
    reject mixed-domain wires (e.g. dropping an electrical wire onto a
    thermal port). Every pin on HEATSINK must report thermal — the
    AMB reference AND every DEV slot."""
    c = Component(type=ComponentType.HEATSINK, name="HS")
    for idx, pin in enumerate(c.pins):
        assert pin_connection_domain(c, idx) == CONNECTION_DOMAIN_THERMAL, (
            f"pin {pin.name} reports a non-thermal domain"
        )
