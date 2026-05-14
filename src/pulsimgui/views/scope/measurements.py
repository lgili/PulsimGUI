"""Pure-Python scope measurement helpers.

These functions take numpy arrays + simple scalars and return the
quantities engineers expect on a power-electronics waveform — THD,
power, energy, RMS, peak-to-peak — without any Qt dependency. The
scope window imports them; tests exercise them in isolation.

Everything is `float64` so accumulation noise stays below the level
that's visible to the user. Goertzel-style single-bin DFTs are used
for THD so the same routine that ships in the Pulsim benchmark KPI
module (``benchmarks/kpi/__init__.py``) produces matching numbers
on both sides of the API boundary.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np


__all__ = [
    "compute_thd",
    "compute_thd_from_spectrum",
    "compute_average_power",
    "compute_energy",
    "compute_rms",
    "snap_to_peak_frequency",
]


def _as_array(values: Iterable[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("measurement helpers expect a 1-D array")
    return arr


def compute_rms(samples: Iterable[float] | np.ndarray) -> float:
    """Root-mean-square of a 1-D array. Returns 0 for an empty input."""
    arr = _as_array(samples)
    if arr.size == 0:
        return 0.0
    return float(math.sqrt(float(np.mean(arr * arr))))


def compute_thd(
    samples: Iterable[float] | np.ndarray,
    sample_rate_hz: float,
    fundamental_hz: float,
    num_harmonics: int = 20,
) -> float:
    """Total Harmonic Distortion as a percentage.

    ``THD% = 100 · √Σ_{k=2..N}(A_k²) / A_1`` where ``A_k`` is the
    one-sided amplitude of the k-th harmonic bin recovered through
    Goertzel-style DFT projection (which avoids the leakage of a
    naive rectangular FFT when the window doesn't span an integer
    number of fundamental periods).

    Returns 0 if the input is too short, the fundamental frequency
    is non-positive, or the recovered ``A_1`` is effectively zero.
    """
    arr = _as_array(samples)
    if arr.size < 4 or sample_rate_hz <= 0.0 or fundamental_hz <= 0.0:
        return 0.0
    a1 = _bin_amplitude(arr, fundamental_hz, sample_rate_hz)
    if a1 <= 0.0:
        return 0.0
    sum_sq = 0.0
    for k in range(2, num_harmonics + 1):
        a_k = _bin_amplitude(arr, k * fundamental_hz, sample_rate_hz)
        sum_sq += a_k * a_k
    if sum_sq <= 0.0:
        return 0.0
    return 100.0 * math.sqrt(sum_sq) / a1


def compute_thd_from_spectrum(
    frequencies: Sequence[float] | np.ndarray,
    magnitudes: Sequence[float] | np.ndarray,
    fundamental_hz: float,
    num_harmonics: int = 20,
) -> float:
    """THD computed directly from a precomputed amplitude spectrum.

    Used by the FFT panel — it already has a one-sided magnitude
    array, so we just bilinearly interpolate the harmonic bins from
    that grid. Returns 0 on invalid inputs.
    """
    freqs = np.asarray(frequencies, dtype=np.float64)
    mags = np.asarray(magnitudes, dtype=np.float64)
    if freqs.size < 2 or mags.size != freqs.size or fundamental_hz <= 0.0:
        return 0.0
    a1 = _interp_amplitude(freqs, mags, fundamental_hz)
    if a1 <= 0.0:
        return 0.0
    sum_sq = 0.0
    for k in range(2, num_harmonics + 1):
        a_k = _interp_amplitude(freqs, mags, k * fundamental_hz)
        sum_sq += a_k * a_k
    if sum_sq <= 0.0:
        return 0.0
    return 100.0 * math.sqrt(sum_sq) / a1


def compute_average_power(
    voltage: Iterable[float] | np.ndarray,
    current: Iterable[float] | np.ndarray,
    *,
    reference: Iterable[float] | np.ndarray | None = None,
) -> float:
    """Average power over the supplied window.

    Computes ``⟨v · i⟩`` element-wise. When ``reference`` is given
    (the second voltage terminal in a probe pair) the voltage drop
    is ``v − reference``.

    The two input arrays must be the same length; if not the
    function returns 0 rather than guessing.
    """
    v = _as_array(voltage)
    i = _as_array(current)
    if v.size == 0 or v.size != i.size:
        return 0.0
    if reference is not None:
        r = _as_array(reference)
        if r.size != v.size:
            return 0.0
        v = v - r
    return float(np.mean(v * i))


def compute_energy(
    times: Iterable[float] | np.ndarray,
    power: Iterable[float] | np.ndarray,
) -> float:
    """Integrate an instantaneous-power trace over its time-base.

    Uses the trapezoidal rule (``numpy.trapezoid`` when available,
    falling back to the older ``numpy.trapz`` alias on numpy < 2.0).
    Returns 0 on shape mismatch or empty input.
    """
    t = _as_array(times)
    p = _as_array(power)
    if t.size < 2 or t.size != p.size:
        return 0.0
    trapezoid = getattr(np, "trapezoid", None) or getattr(np, "trapz", None)
    if trapezoid is None:  # pragma: no cover - numpy always has one of the two
        return 0.0
    return float(trapezoid(p, t))


def snap_to_peak_frequency(
    frequencies: Sequence[float] | np.ndarray,
    magnitudes: Sequence[float] | np.ndarray,
    *,
    exclude_dc_hz: float = 1.0,
    max_hz: float | None = None,
) -> float:
    """Return the frequency of the largest in-band magnitude bin.

    DC bins below ``exclude_dc_hz`` are skipped so the helper doesn't
    "snap" to the DC component of a real-world signal. ``max_hz``,
    if given, clips the search range to ``[exclude_dc_hz, max_hz]``.

    Returns 0 when no usable bins exist (e.g. spectrum too short).
    """
    freqs = np.asarray(frequencies, dtype=np.float64)
    mags = np.asarray(magnitudes, dtype=np.float64)
    if freqs.size == 0 or mags.size != freqs.size:
        return 0.0
    mask = freqs >= exclude_dc_hz
    if max_hz is not None:
        mask &= freqs <= max_hz
    if not bool(mask.any()):
        return 0.0
    candidate_freqs = freqs[mask]
    candidate_mags = mags[mask]
    peak_idx = int(np.argmax(candidate_mags))
    return float(candidate_freqs[peak_idx])


# ---------------------------------------------------------------------------
# Goertzel helpers
# ---------------------------------------------------------------------------


def _bin_amplitude(samples: np.ndarray, freq_hz: float, sample_rate_hz: float) -> float:
    """Single-bin Goertzel projection → one-sided amplitude estimate."""
    n = samples.size
    if n == 0 or freq_hz <= 0 or sample_rate_hz <= 0:
        return 0.0
    k = freq_hz / sample_rate_hz
    omega = 2.0 * math.pi * k
    cos_omega = math.cos(omega)
    coeff = 2.0 * cos_omega
    s_prev = 0.0
    s_prev2 = 0.0
    for x in samples:
        s = float(x) + coeff * s_prev - s_prev2
        s_prev2 = s_prev
        s_prev = s
    real = s_prev - s_prev2 * cos_omega
    imag = s_prev2 * math.sin(omega)
    # Normalise to the one-sided amplitude of a real sinusoid (same
    # convention as ``benchmarks/kpi/_bin_magnitude``).
    return 2.0 * math.hypot(real, imag) / max(1, n)


def _interp_amplitude(freqs: np.ndarray, mags: np.ndarray, target_hz: float) -> float:
    """Linearly interpolate the amplitude spectrum at ``target_hz``."""
    if target_hz <= float(freqs[0]) or target_hz >= float(freqs[-1]):
        # Out-of-band harmonic — contributes nothing to THD.
        return 0.0
    idx = int(np.searchsorted(freqs, target_hz))
    if idx <= 0 or idx >= freqs.size:
        return 0.0
    f_lo = float(freqs[idx - 1])
    f_hi = float(freqs[idx])
    if f_hi <= f_lo:
        return float(mags[idx])
    weight = (target_hz - f_lo) / (f_hi - f_lo)
    return float((1.0 - weight) * mags[idx - 1] + weight * mags[idx])
