"""Tests for SensorlessObserverService — pulsim 1.5 rotor-state
estimation (SlidingModeObserver for PMSM, FluxMRASObserver for IM).

The PMSM sliding-mode observer is validated by feeding a synthetic
back-EMF at a known electrical frequency and asserting the PLL locks
ω̂_e to 2π·f. The IM MRAS observer is validated structurally (runs,
finite, right trace shape) since a meaningful speed estimate needs a
full IM sim. Clarke + error paths are unit-tested directly.
"""
from __future__ import annotations

import math

import pytest

from pulsimgui.services.sensorless_observer_service import (
    SensorlessObserverError,
    SensorlessObserverService,
    is_available,
)


@pytest.fixture
def svc() -> SensorlessObserverService:
    return SensorlessObserverService()


def _synthetic_backemf(f_hz: float, dt: float, n: int, amp: float = 10.0):
    """PMSM-convention back-EMF α-β at electrical frequency f_hz:
    v_α = −amp·sin(ωt), v_β = +amp·cos(ωt); currents ≈ 0 (EMF-dominated)."""
    w = 2.0 * math.pi * f_hz
    times = [k * dt for k in range(n)]
    va = [-amp * math.sin(w * t) for t in times]
    vb = [amp * math.cos(w * t) for t in times]
    ia = [0.0] * n
    ib = [0.0] * n
    return times, va, vb, ia, ib


# ---------------------------------------------------------------------------
# Availability.
# ---------------------------------------------------------------------------
def test_is_available(svc: SensorlessObserverService) -> None:
    assert isinstance(is_available(), bool)
    assert isinstance(svc.is_available(), bool)
    # On the pinned pulsim>=1.6.1 it must be present.
    assert svc.is_available() is True


# ---------------------------------------------------------------------------
# PMSM sliding-mode observer — locks to a known frequency.
# ---------------------------------------------------------------------------
def test_pmsm_observer_locks_to_known_frequency(svc) -> None:
    f_e = 50.0
    dt = 1e-5
    n = 20000  # 200 ms — plenty for the ~100 Hz PLL to settle
    times, va, vb, ia, ib = _synthetic_backemf(f_e, dt, n)

    obs = svc.make_pmsm_observer(Rs=0.5, Ls=2e-3, f_init_hz=f_e)
    traces = svc.run(
        obs, v_alpha=va, v_beta=vb, i_alpha=ia, i_beta=ib, times=times,
        pole_pairs=2,
    )

    assert set(traces) >= {"time", "omega_hat_e", "theta_hat",
                           "low_speed_flag", "omega_hat_mech"}
    assert len(traces["omega_hat_e"]) == n
    # PLL must lock ω̂_e to 2π·50 ≈ 314.16 rad/s by the end.
    omega_final = traces["omega_hat_e"][-1]
    assert omega_final == pytest.approx(2.0 * math.pi * f_e, rel=0.02), (
        f"SMO failed to lock: ω̂={omega_final:.2f}, "
        f"target={2 * math.pi * f_e:.2f}"
    )
    # Mechanical speed = electrical / pole_pairs.
    assert traces["omega_hat_mech"][-1] == pytest.approx(
        omega_final / 2.0, rel=1e-6
    )


def test_pmsm_observer_tracks_different_frequency(svc) -> None:
    f_e = 80.0
    dt = 1e-5
    n = 20000
    times, va, vb, ia, ib = _synthetic_backemf(f_e, dt, n)
    obs = svc.make_pmsm_observer(Rs=0.5, Ls=2e-3, f_init_hz=60.0)
    traces = svc.run(obs, v_alpha=va, v_beta=vb, i_alpha=ia, i_beta=ib,
                     times=times)
    assert traces["omega_hat_e"][-1] == pytest.approx(
        2.0 * math.pi * f_e, rel=0.03
    )


# ---------------------------------------------------------------------------
# IM MRAS observer — structural (runs, finite, right shape).
# ---------------------------------------------------------------------------
def test_im_observer_runs_and_is_finite(svc) -> None:
    dt = 1e-5
    n = 10000
    times, va, vb, ia, ib = _synthetic_backemf(50.0, dt, n, amp=200.0)
    # Give the IM some current so the MRAS adjustable model is excited.
    w = 2.0 * math.pi * 50.0
    ia = [5.0 * math.cos(w * t) for t in times]
    ib = [5.0 * math.sin(w * t) for t in times]

    obs = svc.make_im_observer(Rs=0.5, Ls=0.05, Lr=0.05, Lm=0.045, Rr=0.4)
    traces = svc.run(obs, v_alpha=va, v_beta=vb, i_alpha=ia, i_beta=ib,
                     times=times)
    assert "omega_hat_e" in traces
    # MRAS gives speed only — no theta_hat.
    assert "theta_hat" not in traces
    assert len(traces["omega_hat_e"]) == n
    assert all(math.isfinite(w) for w in traces["omega_hat_e"])


def test_im_observer_rejects_unphysical_leakage(svc) -> None:
    with pytest.raises(SensorlessObserverError, match="leakage"):
        svc.make_im_observer(Rs=0.5, Ls=0.05, Lr=0.05, Lm=0.5)


# ---------------------------------------------------------------------------
# Clarke transform.
# ---------------------------------------------------------------------------
def test_clarke_balanced_three_phase(svc) -> None:
    """A balanced 3-phase set Clarke-transforms to a circle of radius =
    the phase amplitude (amplitude-invariant convention)."""
    amp = 10.0
    w = 2.0 * math.pi * 50.0
    dt = 1e-4
    n = 200
    a, b, c = [], [], []
    for k in range(n):
        t = k * dt
        a.append(amp * math.cos(w * t))
        b.append(amp * math.cos(w * t - 2 * math.pi / 3))
        c.append(amp * math.cos(w * t + 2 * math.pi / 3))
    alpha, beta = svc.clarke(a, b, c)
    assert len(alpha) == n and len(beta) == n
    # |(α, β)| should equal the phase amplitude at every sample.
    for k in range(n):
        mag = math.hypot(alpha[k], beta[k])
        assert mag == pytest.approx(amp, rel=1e-6)


def test_clarke_truncates_to_shortest(svc) -> None:
    alpha, beta = svc.clarke([1.0, 2.0, 3.0], [0.0, 0.0], [0.0, 0.0, 0.0])
    assert len(alpha) == 2
    assert len(beta) == 2


# ---------------------------------------------------------------------------
# run() error + edge paths.
# ---------------------------------------------------------------------------
def test_run_requires_two_samples(svc) -> None:
    obs = svc.make_pmsm_observer(Rs=0.5, Ls=2e-3)
    with pytest.raises(SensorlessObserverError, match="2 samples"):
        svc.run(obs, v_alpha=[1.0], v_beta=[1.0], i_alpha=[0.0],
                i_beta=[0.0], times=[0.0])


def test_run_handles_nonuniform_time_grid(svc) -> None:
    """Per-step dt from the local spacing — a non-uniform grid must not
    crash and yields a full-length trace."""
    obs = svc.make_pmsm_observer(Rs=0.5, Ls=2e-3, f_init_hz=50.0)
    times = [0.0, 1e-5, 3e-5, 6e-5, 10e-5]  # growing steps
    z = [0.0] * len(times)
    va = [-1.0, -0.9, -0.5, 0.0, 0.5]
    vb = [1.0, 1.0, 0.9, 0.8, 0.6]
    traces = svc.run(obs, v_alpha=va, v_beta=vb, i_alpha=z, i_beta=z,
                     times=times)
    assert len(traces["omega_hat_e"]) == len(times)
    assert all(math.isfinite(w) for w in traces["omega_hat_e"])
