"""Sensorless rotor-state estimation (pulsim 1.5 observers).

Wraps pulsim's two textbook sensorless observers and runs them over a
simulation's stator waveforms to estimate rotor angle / speed WITHOUT
a physical position sensor:

* :class:`pulsim.SlidingModeObserver` — for **PMSM** (and other
  synchronous machines). Utkin sliding-mode current observer +
  equivalent-control LPF + angle PLL. Estimates ``θ̂_e`` and
  ``ω̂_e``.
* :class:`pulsim.FluxMRASObserver` — for the **induction motor**.
  Schauder model-reference adaptive system on the rotor flux.
  Estimates ``ω̂_e`` (rotor electrical speed).

This is a POST-PROCESSING analysis: it consumes recorded stator
α-β voltages and currents (Clarke-transformed from the 3-phase
terminals) and replays the observer's discrete ``update`` step over
the time series. It does not affect the circuit — exactly like the
loss / thermal post-processing.

Typical use::

    svc = SensorlessObserverService()
    obs = svc.make_pmsm_observer(Rs=0.5, Ls=2e-3, f_init_hz=50.0)
    traces = svc.run(obs, v_alpha=va, v_beta=vb,
                     i_alpha=ia, i_beta=ib, times=t)
    # traces["omega_hat_e"], traces["theta_hat"] ...
"""
from __future__ import annotations

import math
from typing import Any, Sequence


class SensorlessObserverError(Exception):
    """Raised when an observer can't be built/run (e.g. pulsim too old
    or unphysical motor parameters). Message is GUI-safe."""


def is_available() -> bool:
    """True iff pulsim exposes the sensorless observer classes
    (pulsim >= 1.5)."""
    try:
        import pulsim as p
        return hasattr(p, "SlidingModeObserver") and hasattr(
            p, "FluxMRASObserver"
        )
    except Exception:  # noqa: BLE001
        return False


class SensorlessObserverService:
    """Builds + runs pulsim sensorless observers over stator
    waveforms."""

    def is_available(self) -> bool:
        return is_available()

    # ------------------------------------------------------------------
    # Observer factories.
    # ------------------------------------------------------------------
    def make_pmsm_observer(
        self,
        *,
        Rs: float,
        Ls: float,
        K_sl: float = 50.0,
        omega_lpf: float | None = None,
        Kp_pll: float = 200.0,
        Ki_pll: float = 1.0e4,
        f_init_hz: float = 50.0,
        epsilon: float = 0.5,
    ) -> Any:
        """Build a :class:`pulsim.SlidingModeObserver` for a PMSM.

        ``Rs`` / ``Ls`` should match the machine's per-phase stator
        resistance / (synchronous) inductance. ``f_init_hz`` is the
        PLL's initial frequency guess — set near the nominal
        electrical frequency for a faster lock.
        """
        try:
            import pulsim as p
        except Exception as exc:  # noqa: BLE001
            raise SensorlessObserverError(
                "pulsim is not importable for sensorless estimation"
            ) from exc
        smo_cls = getattr(p, "SlidingModeObserver", None)
        if smo_cls is None:
            raise SensorlessObserverError(
                "pulsim runtime has no SlidingModeObserver "
                "(requires pulsim >= 1.5)"
            )
        if omega_lpf is None:
            omega_lpf = 2.0 * math.pi * 500.0
        try:
            return smo_cls(
                Rs=float(Rs), Ls=float(Ls), K_sl=float(K_sl),
                omega_lpf=float(omega_lpf), Kp_pll=float(Kp_pll),
                Ki_pll=float(Ki_pll), f_init_hz=float(f_init_hz),
                epsilon=float(epsilon),
            )
        except (TypeError, ValueError) as exc:
            raise SensorlessObserverError(
                f"SlidingModeObserver params rejected: {exc}"
            ) from exc

    def make_im_observer(
        self,
        *,
        Rs: float,
        Ls: float,
        Lr: float,
        Lm: float,
        Rr: float = 0.0,
        Kp_mras: float = 50.0,
        Ki_mras: float = 1.0e3,
    ) -> Any:
        """Build a :class:`pulsim.FluxMRASObserver` for an induction
        motor. R/L are the IEEE equivalent-circuit values (rotor side
        referred to the stator). ``Rr`` improves accuracy; when 0 the
        observer uses a NEMA-B heuristic ``Rr ≈ 0.5·Rs``.

        Enforces ``Lm² < Ls·Lr`` (physical leakage) up-front with a
        clear error rather than letting σ go non-positive."""
        if Lm * Lm >= Ls * Lr:
            raise SensorlessObserverError(
                f"Unphysical leakage for the MRAS observer: "
                f"Lm²={Lm * Lm:.3e} ≥ Ls·Lr={Ls * Lr:.3e}."
            )
        try:
            import pulsim as p
        except Exception as exc:  # noqa: BLE001
            raise SensorlessObserverError(
                "pulsim is not importable for sensorless estimation"
            ) from exc
        mras_cls = getattr(p, "FluxMRASObserver", None)
        if mras_cls is None:
            raise SensorlessObserverError(
                "pulsim runtime has no FluxMRASObserver "
                "(requires pulsim >= 1.5)"
            )
        try:
            return mras_cls(
                Rs=float(Rs), Ls=float(Ls), Lr=float(Lr), Lm=float(Lm),
                Rr=float(Rr), Kp_mras=float(Kp_mras), Ki_mras=float(Ki_mras),
            )
        except (TypeError, ValueError) as exc:
            raise SensorlessObserverError(
                f"FluxMRASObserver params rejected: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Clarke transform — 3-phase → α-β (amplitude-invariant).
    # ------------------------------------------------------------------
    @staticmethod
    def clarke(
        a: Sequence[float], b: Sequence[float], c: Sequence[float],
    ) -> tuple[list[float], list[float]]:
        """Amplitude-invariant Clarke transform of three balanced
        phase quantities to the stationary α-β frame::

            α = (2a − b − c) / 3
            β = (b − c) / √3

        Returns ``(alpha, beta)`` as lists matching the input length
        (truncated to the shortest of a/b/c)."""
        n = min(len(a), len(b), len(c))
        inv_sqrt3 = 1.0 / math.sqrt(3.0)
        alpha = [0.0] * n
        beta = [0.0] * n
        for k in range(n):
            ak, bk, ck = float(a[k]), float(b[k]), float(c[k])
            alpha[k] = (2.0 * ak - bk - ck) / 3.0
            beta[k] = (bk - ck) * inv_sqrt3
        return alpha, beta

    # ------------------------------------------------------------------
    # Run the observer over a time series.
    # ------------------------------------------------------------------
    def run(
        self,
        observer: Any,
        *,
        v_alpha: Sequence[float],
        v_beta: Sequence[float],
        i_alpha: Sequence[float],
        i_beta: Sequence[float],
        times: Sequence[float],
        pole_pairs: int | None = None,
    ) -> dict[str, list[float]]:
        """Replay ``observer.update`` over the α-β stator waveforms and
        collect the estimated rotor-state traces.

        Returns a dict with::

            {"time":          [...],
             "omega_hat_e":   [...],   # electrical speed, rad/s
             "theta_hat":     [...],   # electrical angle, rad (SMO only)
             "omega_hat_mech":[...],   # mech speed, rad/s (if pole_pairs)
             "low_speed_flag":[...]}   # SMO only

        The ``dt`` handed to each step is the local sample spacing
        ``times[k] - times[k-1]`` (first step reuses the second's),
        so non-uniform output grids are handled correctly.

        Raises :class:`SensorlessObserverError` on length mismatch or
        if the observer lacks an ``update`` method.
        """
        n = min(
            len(times), len(v_alpha), len(v_beta),
            len(i_alpha), len(i_beta),
        )
        if n < 2:
            raise SensorlessObserverError(
                "Need at least 2 samples to run a sensorless observer."
            )
        update = getattr(observer, "update", None)
        if not callable(update):
            raise SensorlessObserverError(
                "Observer object has no callable update() method."
            )

        # Detect the observer flavor by its class name (avoids importing
        # both classes just for isinstance). SMO returns a 5-tuple
        # (theta, omega, e_a, e_b, low_speed); MRAS returns a 3-tuple
        # (omega, psi_a, psi_b).
        is_smo = type(observer).__name__ == "SlidingModeObserver"

        # Precompute dt per step.
        out_time: list[float] = []
        out_omega_e: list[float] = []
        out_theta: list[float] = []
        out_flag: list[float] = []

        for k in range(n):
            t = float(times[k])
            if k == 0:
                dt = float(times[1]) - float(times[0]) if n > 1 else 0.0
            else:
                dt = float(times[k]) - float(times[k - 1])
            if dt <= 0.0:
                # Skip non-advancing / duplicate timestamps but keep the
                # trace length aligned by repeating the last estimate.
                out_time.append(t)
                out_omega_e.append(out_omega_e[-1] if out_omega_e else 0.0)
                if is_smo:
                    out_theta.append(out_theta[-1] if out_theta else 0.0)
                    out_flag.append(out_flag[-1] if out_flag else 0.0)
                continue
            try:
                raw: Any = update(
                    v_alpha=float(v_alpha[k]), v_beta=float(v_beta[k]),
                    i_alpha=float(i_alpha[k]), i_beta=float(i_beta[k]),
                    dt=dt,
                )
                result: tuple = tuple(raw)
            except SensorlessObserverError:
                raise
            except Exception as exc:  # noqa: BLE001
                raise SensorlessObserverError(
                    f"Observer.update failed at sample {k} (t={t:.6g}s): "
                    f"{type(exc).__name__}: {exc}"
                ) from exc

            out_time.append(t)
            if is_smo:
                theta_hat, omega_hat = float(result[0]), float(result[1])
                low_flag = float(bool(result[4])) if len(result) > 4 else 0.0
                out_theta.append(theta_hat)
                out_omega_e.append(omega_hat)
                out_flag.append(low_flag)
            else:
                out_omega_e.append(float(result[0]))

        traces: dict[str, list[float]] = {
            "time": out_time,
            "omega_hat_e": out_omega_e,
        }
        if is_smo:
            traces["theta_hat"] = out_theta
            traces["low_speed_flag"] = out_flag
        if pole_pairs and int(pole_pairs) > 0:
            pp = int(pole_pairs)
            traces["omega_hat_mech"] = [w / pp for w in out_omega_e]
        return traces
