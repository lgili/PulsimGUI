"""Regression tests for probe → backend-signal resolution (scope channels).

The kernel names every electrical node ``N{netid}`` and emits its voltage as
``V(N{netid})`` regardless of any wire alias. A probe wired to such a node
must resolve to that key — even when the node has a different alias
(``BUSP`` != ``N1``) or the probe only knows the bare numeric net id (``4``
vs the backend's ``N4``).

Regression: example 21 (FOC drive) plotted flat "N3" garbage on every
channel because the probe lookup tried ``V(BUSP)`` / ``V(4)`` and never the
``V(N1)`` / ``V(N4)`` keys the backend actually emits.
"""
from __future__ import annotations

from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.main_window import MainWindow


def _result() -> SimulationResult:
    n = 8
    return SimulationResult(
        time=[float(i) for i in range(n)],
        signals={
            "V(N1)": [180.0] * n,                            # bus rail (flat)
            "V(N4)": [(-1) ** i * 180.0 for i in range(n)],  # phase A (switching)
        },
    )


def test_resolves_unaliased_node_by_N_form() -> None:
    # net 4, no alias → node_label is the bare id "4"; backend emits V(N4).
    series = MainWindow._probe_backend_series(
        _result(), "V_motor_A", "id-A", node_label="4", node_id="4",
    )
    assert series is not None
    assert max(series) - min(series) > 5  # found the switching V(N4), not flat


def test_resolves_aliased_node_by_N_form() -> None:
    # net 1 has alias "BUSP" but the backend emits V(N1), not V(BUSP).
    series = MainWindow._probe_backend_series(
        _result(), "V_bus", "id-B", node_label="BUSP", node_id="1",
    )
    assert series is not None
    assert series[0] == 180.0


def test_without_node_id_alias_only_lookup_misses() -> None:
    # Pre-fix behaviour: only the alias/raw label and no N-form → no match.
    series = MainWindow._probe_backend_series(
        _result(), "V_bus", "id-B", node_label="BUSP",
    )
    assert series is None


def test_component_name_still_wins_when_registered() -> None:
    # If the kernel registered the probe under its own name, that takes
    # priority over the node-voltage fallback.
    res = _result()
    res.signals["V_bus"] = [42.0] * len(res.time)
    series = MainWindow._probe_backend_series(
        res, "V_bus", "id-B", node_label="BUSP", node_id="1",
    )
    assert series == [42.0] * len(res.time)
