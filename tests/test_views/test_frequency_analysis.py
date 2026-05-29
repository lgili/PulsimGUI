"""Tests for frequency-analysis wrappers and BodePlotDialog compatibility."""

from __future__ import annotations

from pulsimgui.services.backend_types import FrequencyAnalysisResult
from pulsimgui.services.simulation_service import ACResult
from pulsimgui.views.dialogs.bode_plot_dialog import BodePlotDialog


def _frequency_result(**overrides) -> FrequencyAnalysisResult:
    base = FrequencyAnalysisResult(
        frequencies=[10.0, 100.0, 1000.0],
        magnitude_db={"H(s)": [0.0, -3.0, -20.0]},
        phase_deg={"H(s)": [0.0, -45.0, -89.0]},
        success=True,
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def test_frequency_analysis_result_is_valid() -> None:
    result = _frequency_result()
    assert result.is_valid

    result.success = False
    assert not result.is_valid

    result.success = True
    result.frequencies = []
    assert not result.is_valid


def test_bode_dialog_accepts_frequency_analysis_result(qapp) -> None:
    dialog = BodePlotDialog(_frequency_result())
    assert dialog._result.success
    assert dialog._result.is_valid
    assert dialog._result.frequencies == [10.0, 100.0, 1000.0]


def test_bode_dialog_accepts_legacy_ac_result(qapp) -> None:
    legacy = ACResult(
        frequencies=[10.0, 100.0, 1000.0],
        magnitude={"V(out)": [0.0, -3.0, -20.0]},
        phase={"V(out)": [0.0, -45.0, -89.0]},
    )
    dialog = BodePlotDialog(legacy)
    assert dialog._result.success
    assert dialog._result.is_valid
    assert "V(out)" in dialog._result.magnitude_db


def test_bode_dialog_uses_backend_stability_margins(qapp) -> None:
    dialog = BodePlotDialog(
        _frequency_result(
            gain_margin_db=12.5,
            phase_margin_deg=58.4,
            gain_crossover_hz=2500.0,
            phase_crossover_hz=9000.0,
        )
    )

    assert dialog._gm_label.text() == "12.50 dB"
    assert dialog._pm_label.text() == "58.40°"
    assert dialog._gm_freq_label.text() == "9000.00 Hz"
    assert dialog._pm_freq_label.text() == "2500.00 Hz"
