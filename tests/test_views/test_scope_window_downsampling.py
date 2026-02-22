"""Tests for scope stacked waveform downsampling."""

from __future__ import annotations

import numpy as np

from pulsimgui.views.scope.scope_window import ScopeWindow


def test_stacked_downsampling_preserves_spike_shape() -> None:
    """Min/max bucket downsampling should preserve narrow spikes."""
    point_count = 200_000
    time = np.linspace(0.0, 5e-3, point_count, dtype=np.float64)
    values = np.sin(2.0 * np.pi * 20_000.0 * time)
    values[123_456] = 48.0  # narrow, high-amplitude event

    decimated_time, decimated_values = ScopeWindow._decimate_stacked_for_display(
        time,
        values,
        max_points=2000,
    )

    # First/last samples are preserved to keep time boundaries stable.
    assert decimated_time[0] == time[0]
    assert decimated_time[-1] == time[-1]
    assert np.max(decimated_values) == np.max(values)
    assert len(decimated_time) <= 2002
    assert len(decimated_time) == len(decimated_values)


def test_stacked_downsampling_skips_small_series() -> None:
    """Series under the threshold should be returned unchanged."""
    time = np.linspace(0.0, 1.0, 800, dtype=np.float64)
    values = np.cos(2.0 * np.pi * 10.0 * time)

    decimated_time, decimated_values = ScopeWindow._decimate_stacked_for_display(
        time,
        values,
        max_points=2000,
    )

    assert np.array_equal(decimated_time, time)
    assert np.array_equal(decimated_values, values)
