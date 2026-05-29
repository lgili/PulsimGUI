"""Tests for post-processing panel and sidebar behavior."""

from __future__ import annotations

from PySide6.QtCore import Qt

from pulsimgui.services.backend_types import (
    HarmonicEntry,
    PostProcessingJobResult,
    PostProcessingResult,
)
from pulsimgui.services.theme_service import DARK_THEME, LIGHT_THEME
from pulsimgui.views.waveform.post_processing_panel import PostProcessingPanel
from pulsimgui.views.waveform.waveform_viewer import WaveformViewer


def test_post_processing_panel_builds_windowed_spectral_job(qapp) -> None:
    panel = PostProcessingPanel()
    try:
        panel.set_available_signals(["V(out)", "I(in)"])
        panel._window_mode_combo.setCurrentIndex(panel._window_mode_combo.findData("index"))
        panel._index_start_spin.setValue(10)
        panel._index_stop_spin.setValue(250)
        panel._job_kind_combo.setCurrentIndex(panel._job_kind_combo.findData("spectral"))
        panel._fundamental_spin.setValue(50_000.0)

        # Check both signals in checklist.
        panel._signals_list.item(0).setCheckState(Qt.CheckState.Checked)
        panel._signals_list.item(1).setCheckState(Qt.CheckState.Checked)

        captured: list[list[dict]] = []
        panel.run_requested.connect(captured.append)
        panel._on_run_clicked()

        assert captured
        payload = captured[0][0]
        assert payload["kind"] == "spectral"
        assert payload["signals"] == ["V(out)", "I(in)"]
        assert payload["window_mode"] == "index"
        assert payload["window_index_start"] == 10
        assert payload["window_index_stop"] == 250
        assert payload["fundamental_hz"] == 50_000.0
    finally:
        panel.close()


def test_post_processing_panel_switches_to_spectral_results_stack(qapp) -> None:
    panel = PostProcessingPanel()
    try:
        result = PostProcessingResult(
            success=True,
            jobs=[
                PostProcessingJobResult(
                    job_id="sp1",
                    kind="spectral",
                    success=True,
                    thd_pct=3.2,
                    fundamental_hz=60_000.0,
                    harmonics=[
                        HarmonicEntry(order=1, frequency_hz=60_000.0, amplitude=1.0),
                        HarmonicEntry(order=2, frequency_hz=120_000.0, amplitude=0.12),
                    ],
                )
            ],
        )
        panel._on_result(result)

        assert not panel._results_stack.isHidden()
        assert panel._results_stack.currentIndex() == 1
        assert "3.2" in panel._spectral_summary_label.text()
    finally:
        panel.close()


def test_post_processing_panel_apply_theme_updates_surface_and_plot(qapp) -> None:
    panel = PostProcessingPanel()
    try:
        panel.apply_theme(LIGHT_THEME)
        light_style = panel.styleSheet()
        light_bg = panel._spectral_plot.backgroundBrush().color().name()

        panel.apply_theme(DARK_THEME)
        dark_style = panel.styleSheet()
        dark_bg = panel._spectral_plot.backgroundBrush().color().name()

        assert LIGHT_THEME.colors.panel_background in light_style
        assert DARK_THEME.colors.panel_background in dark_style
        assert light_style != dark_style
        assert light_bg != dark_bg
    finally:
        panel.close()


def test_waveform_viewer_post_sidebar_hidden_and_toggleable(qapp) -> None:
    viewer = WaveformViewer()
    try:
        assert viewer._right_panel_tabs.isHidden()
        assert not viewer._post_panel_toggle_btn.isChecked()

        viewer._post_panel_toggle_btn.setChecked(True)
        assert not viewer._right_panel_tabs.isHidden()

        viewer._post_panel_toggle_btn.setChecked(False)
        assert viewer._right_panel_tabs.isHidden()
    finally:
        viewer.close()


def test_waveform_viewer_disables_toggle_when_capability_missing(qapp) -> None:
    viewer = WaveformViewer()
    try:
        viewer.set_post_processing_capability(False)
        assert not viewer._post_panel_toggle_btn.isEnabled()
        assert "requires backend" in viewer._post_panel_toggle_btn.toolTip().lower()
        assert viewer._right_panel_tabs.isHidden()
    finally:
        viewer.close()


def test_waveform_viewer_propagates_theme_to_post_processing_panel(qapp) -> None:
    viewer = WaveformViewer()
    try:
        viewer.apply_theme(LIGHT_THEME)
        light_style = viewer._post_processing_panel.styleSheet()

        viewer.apply_theme(DARK_THEME)
        dark_style = viewer._post_processing_panel.styleSheet()

        assert LIGHT_THEME.colors.panel_background in light_style
        assert DARK_THEME.colors.panel_background in dark_style
        assert light_style != dark_style
    finally:
        viewer.close()
