"""Tests for ``PlotCanvas`` signal registry + view mode swap."""

from __future__ import annotations

import numpy as np


def test_add_signal_creates_curve_and_hides_empty_overlay(qapp) -> None:
    """The first registered signal hides the empty-state hint."""
    from pulsimgui.views.scope_v2.plot_canvas import PlotCanvas

    canvas = PlotCanvas()
    try:
        assert list(canvas.signals()) == []
        # ``isHidden`` reports the local setVisible(...) state, so it
        # works even before the canvas itself is shown — ``isVisible``
        # cascades through parents.
        assert not canvas._empty_overlay.isHidden()
        canvas.add_signal("V(out)", color="#5b8def", unit="V")
        assert list(canvas.signals()) == ["V(out)"]
        qapp.processEvents()
        assert canvas._empty_overlay.isHidden()
    finally:
        canvas.close()


def test_append_signal_concatenates_chunks(qapp) -> None:
    """Live-stream path: ``append_signal`` adds samples without losing history."""
    from pulsimgui.views.scope_v2.plot_canvas import PlotCanvas

    canvas = PlotCanvas()
    try:
        canvas.add_signal("y", color="#fff")
        canvas.append_signal("y", np.array([0.0, 0.1]), np.array([1.0, 2.0]))
        canvas.append_signal("y", np.array([0.2, 0.3]), np.array([3.0, 4.0]))
        state = canvas._signals["y"]
        t, y = state.merged()
        np.testing.assert_array_equal(t, [0.0, 0.1, 0.2, 0.3])
        np.testing.assert_array_equal(y, [1.0, 2.0, 3.0, 4.0])
    finally:
        canvas.close()


def test_replace_signal_drops_streaming_cache(qapp) -> None:
    """Post-sim path: ``replace_signal`` swaps in the full-resolution array."""
    from pulsimgui.views.scope_v2.plot_canvas import PlotCanvas

    canvas = PlotCanvas()
    try:
        canvas.add_signal("y", color="#fff")
        canvas.append_signal("y", np.array([0.0, 0.1]), np.array([1.0, 2.0]))
        # Full result has 5 samples — should replace, not append.
        canvas.replace_signal(
            "y",
            np.linspace(0.0, 1.0, 5),
            np.array([0.0, 1.0, 4.0, 9.0, 16.0]),
        )
        t, y = canvas._signals["y"].merged()
        assert t.size == 5 and y.size == 5
        np.testing.assert_array_equal(y, [0.0, 1.0, 4.0, 9.0, 16.0])
    finally:
        canvas.close()


def test_set_view_swaps_time_and_fft(qapp) -> None:
    """Toggling the view mode rebuilds the FFT page from cached data."""
    from pulsimgui.views.scope_v2.plot_canvas import PlotCanvas

    canvas = PlotCanvas()
    try:
        canvas.add_signal("y", color="#fff")
        # 1 kHz sine for 1 ms (1000 samples) → FFT should resolve a peak.
        n = 1000
        t = np.linspace(0.0, 1e-3, n)
        y = np.sin(2 * np.pi * 1000.0 * t)
        canvas.replace_signal("y", t, y)

        assert canvas._view_mode == "time"
        canvas.set_view("fft")
        assert canvas._view_mode == "fft"
        # FFT plot was lazily created on first switch.
        assert canvas._fft_plot is not None
        assert "y" in canvas._fft_curves

        canvas.set_view("time")
        assert canvas._view_mode == "time"
    finally:
        canvas.close()
