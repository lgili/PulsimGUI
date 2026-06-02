"""Tests for publishing dynamic-machine observer traces as result signals.

A PMSM tracked by ``circuit.nonlinear_observer_specs`` carries a live observer
bundle (rotor speed, d/q, per-phase currents) that is NOT in the electrical
state vector. ``PulsimBackend._merge_motor_observer_signals`` resamples those
traces onto the output time base and exposes them as ``<motor>.speed_rpm`` /
``.i_a`` / ``.i_d`` … so a scope channel can plot the FOC story.
"""
from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from pulsimgui.services.backend_adapter import BackendRunResult, PulsimBackend


def _backend() -> PulsimBackend:
    return PulsimBackend.__new__(PulsimBackend)


def _pmsm_circuit(name: str = "M1") -> SimpleNamespace:
    bundle = SimpleNamespace(
        times=[0.0, 1.0, 2.0, 3.0, 4.0],
        omega_rad_s=[0.0, 10.0, 20.0, 30.0, 40.0],
        i_a=[0.0, 1.0, 2.0, 3.0, 4.0],
        i_b=[0.0, -1.0, -2.0, -3.0, -4.0],
        i_c=[0.0, 0.0, 0.0, 0.0, 0.0],
        i_d=[0.0, 0.0, 0.0, 0.0, 0.0],
        i_q=[0.0, 1.0, 2.0, 3.0, 4.0],
        T_em=[0.0, 0.1, 0.2, 0.3, 0.4],
    )
    return SimpleNamespace(
        nonlinear_observer_specs=[{"kind": "pmsm", "name": name, "bundle": bundle}]
    )


def test_publishes_speed_currents_and_dq() -> None:
    result = BackendRunResult()
    result.time = [0.0, 1.0, 2.0, 3.0, 4.0]
    _backend()._merge_motor_observer_signals(_pmsm_circuit(), result)

    for key in ("M1.speed_rpm", "M1.i_a", "M1.i_b", "M1.i_c",
                "M1.i_d", "M1.i_q", "M1.torque"):
        assert key in result.signals
    # rad/s → rpm
    assert result.signals["M1.speed_rpm"][-1] == pytest.approx(40.0 * 60.0 / (2.0 * math.pi))
    assert result.signals["M1.i_a"][-1] == pytest.approx(4.0)
    assert result.signals["M1.i_q"][-1] == pytest.approx(4.0)
    assert result.statistics["motor_observer_signals"]


def test_resamples_onto_output_time() -> None:
    # Output time coarser than the bundle's internal steps → interpolated.
    result = BackendRunResult()
    result.time = [0.0, 2.0, 4.0]
    _backend()._merge_motor_observer_signals(_pmsm_circuit(), result)

    assert len(result.signals["M1.speed_rpm"]) == 3
    # omega at t=2 is 20 rad/s
    assert result.signals["M1.speed_rpm"][1] == pytest.approx(20.0 * 60.0 / (2.0 * math.pi))


def test_noop_without_pmsm_specs() -> None:
    result = BackendRunResult()
    result.time = [0.0, 1.0]
    _backend()._merge_motor_observer_signals(
        SimpleNamespace(nonlinear_observer_specs=[]), result
    )
    assert not any(k.startswith("M1.") for k in result.signals)


def test_noop_without_time() -> None:
    result = BackendRunResult()  # empty time
    _backend()._merge_motor_observer_signals(_pmsm_circuit(), result)
    assert result.signals == {}
