"""Pin the PWL-cache-singular retry guard.

When a transient run fails at the configured timestep and the backend
retries with a finer dt (the ``dt_scale=0.25`` quarter-step profile),
pulsim's PWL state-space cache can fail with::

    PwlStateSpaceCache: numerically singular for mask 0b… N=9 (dt=5e-07)

That is a STRUCTURAL ARTIFACT of the smaller timestep — a switched
circuit whose nodes reference ground only through reactances (a matrix
converter is the canonical case: load/filter inductors isolate the
output/input nodes) builds cleanly at the configured dt but goes
singular at a much finer dt because the companion conductances shrink.
Surfacing that retry artifact as the final error is misleading: the user
sees a bizarre ``singular at dt=5e-07`` they never configured, instead
of the real reason the original attempt failed.

``_is_pwl_cache_singular_error`` classifies the artifact so the retry
loop can prefer the original configured-dt error. These tests pin that
classifier.
"""
from __future__ import annotations

from pulsimgui.services.backend_adapter import PulsimBackend


def test_classifies_pwl_cache_singular_message() -> None:
    fn = PulsimBackend._is_pwl_cache_singular_error
    assert fn(
        "PwlStateSpaceCache: numerically singular for mask "
        "0b000000000 N=9 (dt=5e-07)"
    )
    # The mask-form without the class name (defensive — wording may vary).
    assert fn("numerically singular for mask 0b10 N=9")


def test_does_not_classify_real_diagnostics() -> None:
    fn = PulsimBackend._is_pwl_cache_singular_error
    # A genuine Newton/convergence failure is the REAL diagnostic — must
    # NOT be mistaken for the retry artifact (else the guard would hide
    # the actual fault).
    assert not fn("Newton iteration did not converge after 100 steps")
    assert not fn("transient diverged at t=1.2e-3")
    # A bare "singular matrix" without the PWL-cache/mask context is a
    # different (real) error and must not be swallowed.
    assert not fn("singular matrix in DC operating point")
    assert not fn("")
    assert not fn(None)  # type: ignore[arg-type]


def test_is_case_insensitive() -> None:
    fn = PulsimBackend._is_pwl_cache_singular_error
    assert fn("PWLSTATESPACECACHE: NUMERICALLY SINGULAR FOR MASK 0B0")
    assert fn("pwlstatespacecache singular")
