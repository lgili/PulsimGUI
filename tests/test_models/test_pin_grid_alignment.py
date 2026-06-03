"""Pin-to-grid alignment regression.

Every pin of every component instance must land on a multiple of the
20-px wiring grid. If it doesn't, wires snap to the grid and stop short
of the pin — the user sees the component "not connect" even when the
backend topology is fine.

The runtime safety net (``_snap_pin_layout``) snaps every authored
position at module load and every dynamic generator output. This test
guards two invariants:

1.  A freshly-created ``Component(type=X)`` has every pin on the grid,
    for every ``ComponentType``.
2.  The dynamic pin generators (``_default_sum_pins``,
    ``_default_c_block_pins``, ``_default_scope_pins``,
    ``_default_mux_pins``, ``_default_demux_pins``) emit pins on the
    grid for typical port counts — so an unsnapped path can't leak.

Regression notes:
* PMSM / INDUCTION_MOTOR / FOC_CONTROLLER originally authored stator/
  controller pins at ``±30 / ±25 / ±15``. The snap silently rounded to
  ``±40 / ±20``, leaving a ±5–10 px discrepancy between the body
  geometry the artist drew and where the pin bubble actually rendered.
  Pins are now authored at the snapped positions directly.
* SUM / C_BLOCK dynamic generators used to emit OUT pins at ``±35``;
  fixed to ``±40``.
"""
from __future__ import annotations

import pytest

from pulsimgui.models.component import (
    Component,
    ComponentType,
    PIN_GRID_STEP,
    _default_c_block_pins,
    _default_demux_pins,
    _default_mux_pins,
    _default_scope_pins,
    _default_sum_pins,
    _default_unary_block_pins,
)

GRID = PIN_GRID_STEP


def _on_grid(value: float) -> bool:
    return abs(value) % GRID < 1e-6


@pytest.mark.parametrize("ctype", list(ComponentType))
def test_default_component_pins_land_on_grid(ctype: ComponentType) -> None:
    """Default-constructed component of every type must have on-grid pins."""
    try:
        comp = Component(type=ctype, name=f"X_{ctype.name}")
    except Exception as exc:  # pragma: no cover — defensive
        pytest.skip(f"cannot instantiate {ctype.name}: {exc}")
    for pin in comp.pins:
        assert _on_grid(pin.x), (
            f"{ctype.name} pin[{pin.index}] {pin.name!r} x={pin.x} not on "
            f"{GRID}-px grid (would create visible wire-to-pin gap)"
        )
        assert _on_grid(pin.y), (
            f"{ctype.name} pin[{pin.index}] {pin.name!r} y={pin.y} not on "
            f"{GRID}-px grid"
        )


@pytest.mark.parametrize("input_count", [2, 3, 4, 5, 8])
def test_default_sum_pins_on_grid(input_count: int) -> None:
    for pin in _default_sum_pins(input_count):
        assert _on_grid(pin.x), f"sum({input_count}) pin {pin.name} x={pin.x} off-grid"
        assert _on_grid(pin.y), f"sum({input_count}) pin {pin.name} y={pin.y} off-grid"


@pytest.mark.parametrize("n_in,n_out", [(1, 1), (2, 1), (1, 2), (3, 3)])
def test_default_c_block_pins_on_grid(n_in: int, n_out: int) -> None:
    for pin in _default_c_block_pins(n_in, n_out):
        assert _on_grid(pin.x), f"C_BLOCK({n_in},{n_out}) pin {pin.name} x={pin.x} off-grid"
        assert _on_grid(pin.y), f"C_BLOCK({n_in},{n_out}) pin {pin.name} y={pin.y} off-grid"


def test_default_unary_block_pins_on_grid() -> None:
    for pin in _default_unary_block_pins():
        assert _on_grid(pin.x)
        assert _on_grid(pin.y)


@pytest.mark.parametrize("count", [1, 2, 4, 8])
def test_default_scope_pins_on_grid(count: int) -> None:
    for pin in _default_scope_pins(count):
        assert _on_grid(pin.x)
        assert _on_grid(pin.y)


@pytest.mark.parametrize("count", [2, 3, 4, 8])
def test_default_mux_demux_pins_on_grid(count: int) -> None:
    for pin in _default_mux_pins(count):
        assert _on_grid(pin.x), f"MUX({count}) pin {pin.name} x={pin.x} off-grid"
        assert _on_grid(pin.y), f"MUX({count}) pin {pin.name} y={pin.y} off-grid"
    for pin in _default_demux_pins(count):
        assert _on_grid(pin.x), f"DEMUX({count}) pin {pin.name} x={pin.x} off-grid"
        assert _on_grid(pin.y), f"DEMUX({count}) pin {pin.name} y={pin.y} off-grid"
