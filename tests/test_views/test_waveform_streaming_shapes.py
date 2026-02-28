"""Regression tests for streaming waveform shape alignment."""

from __future__ import annotations

import numpy as np

from pulsimgui.views.waveform.waveform_viewer import WaveformViewer


def test_streaming_late_signal_keeps_x_y_lengths_aligned(qapp) -> None:
    """A signal that starts late should be padded, not crash plotting."""

    viewer = WaveformViewer()
    try:
        for index in range(25):
            sample = {"V(out)": float(index)}
            if index >= 20:
                sample["I(L1)"] = float(index) * 0.1
            viewer.add_data_point(float(index), sample)

        viewer._flush_streaming_data()

        assert "I(L1)" in viewer._streaming_traces
        x_data, y_data = viewer._streaming_traces["I(L1)"].getData()
        assert x_data is not None
        assert y_data is not None
        assert len(x_data) == len(y_data) == 25
        assert np.isnan(y_data[:20]).all()
    finally:
        viewer.close()


def test_streaming_ignores_non_scalar_values(qapp) -> None:
    """Vector metadata in callbacks must not be treated as waveform traces."""

    viewer = WaveformViewer()
    try:
        viewer.add_data_point(0.0, {"V(out)": 1.0, "state_vector": np.array([1.0, 2.0, 3.0])})
        viewer._flush_streaming_data()

        assert "V(out)" in viewer._streaming_signals
        assert "state_vector" not in viewer._streaming_signals
    finally:
        viewer.close()
