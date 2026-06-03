"""Tests for the pulsim 1.7 thermal viewer enhancements: runaway
banner, T_j limit-trip banner, and Coupled Solve tab.

What we pin:

  1. **No HEATSINK on the schematic** → Coupled Solve tab disabled,
     both banners hidden, caption explains the legacy path owns
     the answer.

  2. **HEATSINK present, stable coupled solve** → Coupled Solve tab
     enabled, table rows per (sink, device) carrying T_amb / T_sink /
     T_j / power, banners hidden, caption explains the powers are
     reference (T-independent) losses.

  3. **electrothermal_steady_state converged with tempcos** →
     Coupled Solve table prefers the electrothermal record per sink
     (final_powers_W, not the T-independent ones), caption updates
     to note temperature-dependent corrections are applied,
     runaway banner stays hidden (converged=True).

  4. **runaway=True** → Banner shows with the sink name(s) and
     feedback_gain values, Coupled Solve tab stays usable (other
     sinks may have converged).

  5. **thermal_limit_trips with tripped=True** → Limit banner shows
     with the device name and peak vs T_limit, independent of the
     runaway banner (both can show simultaneously).

  6. **Re-clearing the widget** wipes banners + table so a stale
     warning doesn't linger when a new sim returns no results.
"""
from __future__ import annotations

from pulsimgui.services.thermal_service import (
    ThermalDeviceResult,
    ThermalResult,
    ThermalStage,
)


def _device(name: str, peak: float = 80.0) -> ThermalDeviceResult:
    """Minimal device record so the widget has at least one row to
    plot. Most ThermalViewer paths early-return when devices is empty."""
    return ThermalDeviceResult(
        component_id=f"id_{name}",
        component_name=name,
        stages=[ThermalStage(name=f"{name} jc", resistance=1.5,
                             capacitance=0.075, temperature=peak)],
        temperature_trace=[25.0, 50.0, peak],
        conduction_loss=3.0,
        switching_loss_on=0.5, switching_loss_off=0.5,
        reverse_recovery_loss=0.0,
        steady_state_temperature=peak,
        thermal_limit=None,
    )


def _result(
    *,
    devices: list[str] | None = None,
    shared_heatsink: list[dict] | None = None,
    electrothermal: list[dict] | None = None,
    trips: list[dict] | None = None,
) -> ThermalResult:
    return ThermalResult(
        time=[0.0, 0.5, 1.0],
        devices=[_device(n) for n in (devices or ["Q1"])],
        ambient_temperature=25.0,
        is_synthetic=False,
        error_message="",
        shared_heatsink_results=shared_heatsink or [],
        electrothermal_results=electrothermal or [],
        thermal_limit_trips=trips or [],
    )


# ---------------------------------------------------------------------------
# 1. No HEATSINK → tab disabled, banners hidden
# ---------------------------------------------------------------------------


def test_no_heatsink_disables_coupled_tab_and_hides_banners(qapp, qtbot) -> None:
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result())  # devices but no heatsink records

    assert w._tabs.isTabEnabled(w._coupled_tab_index) is False
    assert w._runaway_banner.isHidden() is True
    assert w._limit_banner.isHidden() is True
    assert w._coupled_table.rowCount() == 0
    assert "No HEATSINK" in w._coupled_caption.text()


# ---------------------------------------------------------------------------
# 2. SharedHeatsink present, no tempcos → table populated, banners hidden
# ---------------------------------------------------------------------------


def test_shared_heatsink_populates_table_without_tempcos(qapp, qtbot) -> None:
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result(
        devices=["Q1", "Q2"],
        shared_heatsink=[{
            "name": "HS_PFC",
            "T_amb_C": 40.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "T_sink_C": 85.0,
            "devices": {"Q1": 95.0, "Q2": 100.0},
            "powers_W": {"Q1": 5.0, "Q2": 10.0},
        }],
    ))
    assert w._tabs.isTabEnabled(w._coupled_tab_index) is True
    assert w._runaway_banner.isHidden() is True
    assert w._limit_banner.isHidden() is True
    # 2 device rows under one sink.
    assert w._coupled_table.rowCount() == 2
    # Sink name appears only on the first row (the rest are blank).
    assert w._coupled_table.item(0, 0).text() == "HS_PFC"
    assert w._coupled_table.item(1, 0).text() == ""
    # T_amb / T_sink also only on the first row.
    assert w._coupled_table.item(0, 1).text() == "40.0"
    assert w._coupled_table.item(0, 2).text() == "85.0"
    # Device-specific T_j on every row.
    device_temps = {
        w._coupled_table.item(r, 3).text():
            w._coupled_table.item(r, 4).text()
        for r in range(2)
    }
    assert device_temps == {"Q1": "95.0", "Q2": "100.0"}
    # Powers carry through.
    device_powers = {
        w._coupled_table.item(r, 3).text():
            w._coupled_table.item(r, 5).text()
        for r in range(2)
    }
    assert device_powers == {"Q1": "5.00", "Q2": "10.00"}
    # Caption explains we're showing reference (T-independent) powers.
    assert "reference" in w._coupled_caption.text().lower()


# ---------------------------------------------------------------------------
# 3. electrothermal converged → final_powers preferred over reference
# ---------------------------------------------------------------------------


def test_electrothermal_converged_prefers_final_powers(qapp, qtbot) -> None:
    """When electrothermal solved cleanly for a sink, the Coupled Solve
    tab should display final_powers_W (T-corrected) rather than the
    reference powers from shared_heatsink. The caption updates to note
    this."""
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result(
        devices=["Q1"],
        shared_heatsink=[{
            "name": "HS", "T_amb_C": 40.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "T_sink_C": 85.0,
            "devices": {"Q1": 95.0},
            "powers_W": {"Q1": 5.0},
        }],
        electrothermal=[{
            "name": "HS", "T_amb_C": 40.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "converged": True, "runaway": False,
            "feedback_gain": 0.42,
            "T_sink_C": 92.1,
            "devices": {"Q1": 105.4},
            "final_powers_W": {"Q1": 5.5},
            "reference_powers_W": {"Q1": 5.0},
        }],
    ))
    # T_j shows the converged answer, not the reference one.
    assert w._coupled_table.item(0, 4).text() == "105.4"
    # T_sink uses the electrothermal record too.
    assert w._coupled_table.item(0, 2).text() == "92.1"
    # final_powers_W preferred.
    assert w._coupled_table.item(0, 5).text() == "5.50"
    # Caption updates.
    assert "temperature-dependent" in w._coupled_caption.text().lower()
    # No banner — stable solve.
    assert w._runaway_banner.isHidden() is True


# ---------------------------------------------------------------------------
# 4. runaway=True → banner shown with sink name + gain
# ---------------------------------------------------------------------------


def test_runaway_record_shows_warning_banner_with_sink_and_gain(qapp, qtbot) -> None:
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result(
        devices=["Q1"],
        shared_heatsink=[{
            "name": "HS", "T_amb_C": 40.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "T_sink_C": 85.0, "devices": {"Q1": 95.0},
            "powers_W": {"Q1": 5.0},
        }],
        electrothermal=[{
            "name": "HS_PFC",
            "T_amb_C": 40.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "converged": False, "runaway": True,
            "feedback_gain": 1.07,
            "message": "Thermal runaway — ρ(M·K)=1.07 ≥ 1.",
            "reference_powers_W": {"Q1": 5.0},
        }],
    ))
    assert w._runaway_banner.isHidden() is False
    # The banner text mentions which sink + the feedback gain.
    banner_text = w._runaway_banner._text_label.text()
    assert "HS_PFC" in banner_text
    assert "1.07" in banner_text
    # Limit banner stays hidden (no trips in this result).
    assert w._limit_banner.isHidden() is True


# ---------------------------------------------------------------------------
# 5. T_j limit trip → limit banner with device + peak/T_limit
# ---------------------------------------------------------------------------


def test_thermal_limit_trip_shows_separate_banner(qapp, qtbot) -> None:
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result(
        devices=["Q1"],
        trips=[{
            "device_name": "Q1",
            "T_limit_C": 175.0,
            "hysteresis_C": 0.0,
            "tripped": True,
            "trip_time_s": 0.042,
            "trip_temperature_C": 176.4,
            "peak_temperature_C": 189.1,
            "trip_margin_C": 14.1,
        }],
    ))
    assert w._limit_banner.isHidden() is False
    text = w._limit_banner._text_label.text()
    assert "Q1" in text
    assert "189" in text  # peak rounded to 0 decimals
    assert "175" in text  # T_limit rounded to 0 decimals
    # Runaway banner stays hidden (no electrothermal record).
    assert w._runaway_banner.isHidden() is True


def test_both_banners_can_show_simultaneously(qapp, qtbot) -> None:
    """They answer independent questions ("did the design ever reach
    equilibrium?" vs "did any device cross its rated T_max during the
    run?"). Both can be true at the same time."""
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    w.set_result(_result(
        devices=["Q1"],
        electrothermal=[{
            "name": "HS", "T_amb_C": 25.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "converged": False, "runaway": True, "feedback_gain": 1.5,
            "reference_powers_W": {"Q1": 5.0},
        }],
        trips=[{
            "device_name": "Q1", "T_limit_C": 175.0,
            "hysteresis_C": 0.0, "tripped": True,
            "trip_time_s": 0.01, "trip_temperature_C": 180.0,
            "peak_temperature_C": 200.0, "trip_margin_C": 25.0,
        }],
    ))
    assert w._runaway_banner.isHidden() is False
    assert w._limit_banner.isHidden() is False


# ---------------------------------------------------------------------------
# 6. Re-clearing wipes banners + table
# ---------------------------------------------------------------------------


def test_clearing_widget_hides_banners_and_empties_table(qapp, qtbot) -> None:
    """A subsequent ``set_result(None)`` (or no-devices result) must
    wipe the stale runaway banner — leaving it visible after a new
    sim returned no results would lie to the user."""
    from pulsimgui.views.thermal.thermal_viewer import ThermalViewerWidget

    w = ThermalViewerWidget()
    qtbot.addWidget(w)
    # First, populate with a runaway.
    w.set_result(_result(
        devices=["Q1"],
        electrothermal=[{
            "name": "HS", "T_amb_C": 25.0,
            "R_th_sink_to_amb_K_per_W": 3.0,
            "converged": False, "runaway": True, "feedback_gain": 2.0,
        }],
    ))
    assert w._runaway_banner.isHidden() is False

    # Then clear.
    w.set_result(None)
    assert w._runaway_banner.isHidden() is True
    assert w._limit_banner.isHidden() is True
    assert w._coupled_table.rowCount() == 0
    assert w._tabs.isTabEnabled(w._coupled_tab_index) is False
