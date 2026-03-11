"""Tests for dynamic measurement row visibility."""

from __future__ import annotations

from pulsimgui.views.waveform.waveform_viewer import MeasurementsPanel


_SAMPLE_TABLE = {
    "Vout": {
        "c1": 1.0,
        "c2": 2.0,
        "dv": 1.0,
        "min": 0.0,
        "max": 2.5,
        "mean": 1.5,
        "rms": 1.7,
        "pkpk": 2.5,
    }
}


def test_measurements_panel_can_filter_visible_rows(qapp) -> None:
    panel = MeasurementsPanel()
    try:
        panel.set_multi_signal_measurements(_SAMPLE_TABLE)
        assert panel._multi_table.rowCount() == 1
        assert panel._multi_table.columnCount() == 8

        panel.set_visible_measurement_keys(["rms", "max"])

        assert panel.visible_measurement_keys() == ["rms", "max"]
        assert panel._multi_table.rowCount() == 1
        assert panel._multi_table.columnCount() == 2
        assert panel._multi_table.horizontalHeaderItem(0).text() == "RMS"
        assert panel._multi_table.horizontalHeaderItem(1).text() == "Max"
    finally:
        panel.close()


def test_measurements_panel_reverts_to_defaults_when_empty_selection(qapp) -> None:
    panel = MeasurementsPanel()
    try:
        panel.set_visible_measurement_keys([])
        assert panel.visible_measurement_keys() == panel.available_measurement_keys()
    finally:
        panel.close()
