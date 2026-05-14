"""Tests for formula-based math signal creation inside ScopeWindow."""

from __future__ import annotations

import numpy as np

from pulsimgui.models.component import ComponentType
from pulsimgui.services.simulation_service import SimulationResult
from pulsimgui.views.scope.scope_window import MathSignalDialog, ScopeWindow


def _sample_result(signal_count: int = 3, sample_count: int = 32) -> SimulationResult:
    time = [idx * 1e-6 for idx in range(sample_count)]
    signals = {
        f"S{sig_idx + 1}": [(sig_idx + 1) * 0.2 + (idx * 0.01) for idx in range(sample_count)]
        for sig_idx in range(signal_count)
    }
    return SimulationResult(time=time, signals=signals, statistics={})


def _prepare_window(window: ScopeWindow) -> None:
    result = _sample_result(signal_count=3)
    window._current_result = result
    window._refresh_stacked_sidebar(result)
    window._rebuild_stacked_plots(result)


def test_math_dialog_valid_formula_enables_create_and_unit_preview(qapp) -> None:
    dialog = MathSignalDialog(
        None,
        signal_data={
            "Vin": np.array([0.0, 1.0, 2.0], dtype=float),
            "Vout": np.array([1.0, 2.0, 3.0], dtype=float),
        },
        signal_units={"Vin": "V", "Vout": "V"},
        time_values=np.array([0.0, 1e-6, 2e-6], dtype=float),
        default_signal="Vin",
        theme=None,
    )
    try:
        dialog._source_b_combo.setCurrentIndex(dialog._source_b_combo.findText("Vout"))
        dialog._formula_edit.setText("A + B")

        assert dialog._create_button is not None
        assert dialog._create_button.isEnabled() is True
        assert dialog._unit_preview_label.text() == "Result Unit: V"
        assert "valid expression" in dialog._preview_label.text()
    finally:
        dialog.close()


def test_math_dialog_invalid_formula_disables_create(qapp) -> None:
    dialog = MathSignalDialog(
        None,
        signal_data={"Vin": np.array([0.0, 1.0, 2.0], dtype=float)},
        signal_units={"Vin": "V"},
        time_values=np.array([0.0, 1e-6, 2e-6], dtype=float),
        default_signal="Vin",
        theme=None,
    )
    try:
        dialog._formula_edit.setText("A + C")

        assert dialog._create_button is not None
        assert dialog._create_button.isEnabled() is False
        assert "invalid expression" in dialog._preview_label.text()
    finally:
        dialog.close()


def test_scope_creates_hidden_math_signal_when_auto_plot_disabled(qapp) -> None:
    window = ScopeWindow("scope-math-1", "Math Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._signal_units.update({"S1": "V", "S2": "V", "S3": "A"})

        signal_key = window._create_math_signal_from_config(
            {
                "source_a": "S1",
                "source_b": "S2",
                "formula": "A + B",
                "custom_name": "Sum V",
                "auto_plot": False,
                "result_unit": "V",
            }
        )

        assert signal_key in window._stacked_signals
        assert window._display_signal_name(signal_key) == "Sum V"
        assert window._signal_units[signal_key] == "V"
        assert signal_key not in window._stacked_signal_list.get_visible_signals()
    finally:
        window.close()


def test_scope_creates_visible_math_signal_when_auto_plot_enabled(qapp) -> None:
    window = ScopeWindow("scope-math-2", "Math Scope", ComponentType.ELECTRICAL_SCOPE)
    try:
        _prepare_window(window)
        window._signal_units.update({"S1": "V", "S2": "V", "S3": "A"})

        signal_key = window._create_math_signal_from_config(
            {
                "source_a": "S1",
                "source_b": "S2",
                "formula": "moving_avg(A - B, 4)",
                "custom_name": "",
                "auto_plot": True,
                "result_unit": "V",
            }
        )

        assert signal_key in window._stacked_signal_list.get_visible_signals()
        assert window._stacked_active_signal == signal_key
        assert "moving_avg(A - B, 4)" in window._display_signal_name(signal_key)
    finally:
        window.close()
