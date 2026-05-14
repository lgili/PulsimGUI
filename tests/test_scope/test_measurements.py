"""Unit tests for the scope measurement helpers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from pulsimgui.views.scope import measurements as m


# Sample rate that nicely divides 60 Hz so single-bin DFT lands cleanly.
FS = 10_000.0
F0 = 60.0


def _make_time(duration: float = 0.1) -> np.ndarray:
    """Time-vector with exactly ``duration * FS`` samples."""
    n = int(duration * FS)
    return np.arange(n, dtype=np.float64) / FS


class TestComputeRMS:
    def test_pure_sine(self):
        t = _make_time()
        signal = np.sin(2 * math.pi * F0 * t)
        assert m.compute_rms(signal) == pytest.approx(1.0 / math.sqrt(2), abs=1e-3)

    def test_dc(self):
        assert m.compute_rms(np.full(100, 5.0)) == pytest.approx(5.0)

    def test_empty(self):
        assert m.compute_rms(np.array([])) == 0.0


class TestComputeTHD:
    def test_pure_sine_is_zero(self):
        t = _make_time()
        sine = np.sin(2 * math.pi * F0 * t)
        # Pure sinusoid should produce essentially zero THD.
        assert m.compute_thd(sine, FS, F0) < 0.5

    def test_square_wave_matches_textbook(self):
        t = _make_time(0.5)
        square = np.sign(np.sin(2 * math.pi * F0 * t))
        # Textbook square-wave THD is ~48 % (sqrt(π²/8 − 1) ≈ 0.4834).
        thd = m.compute_thd(square, FS, F0, num_harmonics=40)
        assert 40.0 <= thd <= 55.0

    def test_triangle_wave_matches_textbook(self):
        t = _make_time(0.5)
        # Symmetric unit-amplitude triangle wave.
        triangle = 2.0 * np.abs((t * F0) % 1.0 - 0.5) - 0.5
        # Textbook triangle THD is ~12.1 %.
        thd = m.compute_thd(triangle, FS, F0, num_harmonics=40)
        assert 10.0 <= thd <= 14.0

    def test_invalid_inputs_return_zero(self):
        assert m.compute_thd(np.array([]), FS, F0) == 0.0
        assert m.compute_thd(np.ones(10), 0.0, F0) == 0.0
        assert m.compute_thd(np.ones(10), FS, 0.0) == 0.0


class TestComputeTHDFromSpectrum:
    def test_zero_for_pure_fundamental(self):
        freqs = np.linspace(0, 1000, 1001)
        mags = np.zeros_like(freqs)
        mags[60] = 1.0  # only fundamental
        assert m.compute_thd_from_spectrum(freqs, mags, 60.0) == pytest.approx(0.0, abs=1e-6)

    def test_third_harmonic_thd(self):
        freqs = np.linspace(0, 1000, 1001)
        mags = np.zeros_like(freqs)
        mags[60] = 1.0   # A_1
        mags[180] = 0.3  # A_3
        # THD = 100 * 0.3 / 1.0 = 30 %
        assert m.compute_thd_from_spectrum(freqs, mags, 60.0) == pytest.approx(30.0, abs=0.5)


class TestComputePower:
    def test_dc_power(self):
        v = np.full(1000, 12.0)
        i = np.full(1000, 1.5)
        assert m.compute_average_power(v, i) == pytest.approx(18.0)

    def test_with_reference(self):
        v = np.full(1000, 12.0)
        i = np.full(1000, 1.0)
        ref = np.full(1000, 2.0)
        # (12 − 2) * 1 = 10 W
        assert m.compute_average_power(v, i, reference=ref) == pytest.approx(10.0)

    def test_mismatched_returns_zero(self):
        assert m.compute_average_power(np.ones(5), np.ones(10)) == 0.0


class TestComputeEnergy:
    def test_constant_power(self):
        # 18 W constant over 0.1 s should be 1.8 J.
        t = np.linspace(0, 0.1, 1000)
        p = np.full(1000, 18.0)
        assert m.compute_energy(t, p) == pytest.approx(1.8, abs=1e-3)

    def test_ramp_power(self):
        # P(t) ramps 0 → 10 over 1 s → energy = 5 J (triangle area).
        t = np.linspace(0, 1.0, 100)
        p = 10.0 * t
        assert m.compute_energy(t, p) == pytest.approx(5.0, abs=0.1)

    def test_mismatched_returns_zero(self):
        assert m.compute_energy(np.ones(5), np.ones(10)) == 0.0


class TestSnapToPeak:
    def test_picks_largest_bin(self):
        freqs = np.linspace(0, 1000, 101)  # 10 Hz steps
        mags = np.zeros(101)
        mags[12] = 0.5   # 120 Hz
        mags[6] = 1.0    # 60 Hz <- biggest
        mags[18] = 0.3   # 180 Hz
        assert m.snap_to_peak_frequency(freqs, mags) == pytest.approx(60.0, abs=10.0)

    def test_excludes_dc(self):
        freqs = np.linspace(0, 1000, 101)
        mags = np.zeros(101)
        mags[0] = 5.0    # huge DC component
        mags[6] = 1.0    # actual 60 Hz peak
        # exclude_dc_hz=1 should skip the DC bin.
        assert m.snap_to_peak_frequency(freqs, mags) == pytest.approx(60.0, abs=10.0)

    def test_respects_max_hz(self):
        freqs = np.linspace(0, 1000, 101)
        mags = np.zeros(101)
        mags[6] = 0.5   # 60 Hz
        mags[60] = 1.0  # 600 Hz <- bigger but outside max_hz
        assert m.snap_to_peak_frequency(freqs, mags, max_hz=200.0) == pytest.approx(60.0, abs=10.0)
