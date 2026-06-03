"""Unit tests for the datasheet-Z_th → Foster fit dialog.

The dialog itself is a thin Qt wrapper; the real logic lives in the
module-level pure-Python helpers (``parse_zth_csv``,
``fit_zth_to_foster``, ``evaluate_foster_zth``, ``FosterFitResult``).
We hit those directly — they don't need a QApplication — and round-trip
a synthetic 3-stage Foster curve to verify pulsim's fitter recovers
the original R / τ within tolerance and that the dialog's
``C = τ / R`` conversion matches the GUI's persistence schema.
"""
from __future__ import annotations

import numpy as np
import pytest

from pulsimgui.views.dialogs.foster_fit_dialog import (
    FosterFitResult,
    evaluate_foster_zth,
    fit_zth_to_foster,
    parse_zth_csv,
)


# ---------------------------------------------------------------------------
# parse_zth_csv
# ---------------------------------------------------------------------------


def test_parse_zth_csv_accepts_comma_tab_semicolon_and_whitespace() -> None:
    """User pastes from PDF / Excel / plain CSV — all should parse."""
    text = (
        "# header comment\n"
        "1e-5, 0.024\n"
        "3e-5;0.041\n"
        "1e-4\t0.069\n"
        "  3e-4   0.107\n"
        "\n"
        "1e-3,0.169\n"
    )
    t, z = parse_zth_csv(text)
    assert t.tolist() == [1e-5, 3e-5, 1e-4, 3e-4, 1e-3]
    assert z.tolist() == [0.024, 0.041, 0.069, 0.107, 0.169]


def test_parse_zth_csv_rejects_under_3_samples() -> None:
    with pytest.raises(ValueError, match="at least 3"):
        parse_zth_csv("1e-5, 0.024\n3e-5, 0.041\n")


def test_parse_zth_csv_rejects_nonmonotonic_time() -> None:
    text = "1e-3, 0.169\n1e-4, 0.069\n1e-5, 0.024\n"
    with pytest.raises(ValueError, match="strictly increasing"):
        parse_zth_csv(text)


def test_parse_zth_csv_rejects_negative_z() -> None:
    text = "1e-5, 0.024\n3e-5, -0.041\n1e-4, 0.069\n"
    with pytest.raises(ValueError, match="Z_th samples must be"):
        parse_zth_csv(text)


def test_parse_zth_csv_rejects_zero_or_negative_time() -> None:
    text = "0.0, 0.024\n3e-5, 0.041\n1e-4, 0.069\n"
    with pytest.raises(ValueError, match="time samples must be"):
        parse_zth_csv(text)


def test_parse_zth_csv_truncates_extra_columns() -> None:
    """A datasheet CSV with units / device column shouldn't break the
    parser — first two numeric tokens win."""
    text = "1e-5, 0.024, K/W\n3e-5, 0.041, K/W\n1e-4, 0.069, K/W\n"
    t, z = parse_zth_csv(text)
    assert t.tolist() == [1e-5, 3e-5, 1e-4]
    assert z.tolist() == [0.024, 0.041, 0.069]


# ---------------------------------------------------------------------------
# fit_zth_to_foster — round-trip a synthetic 3-stage curve.
# ---------------------------------------------------------------------------


def _synthetic_three_stage_zth(
    r_true: list[float], tau_true: list[float],
) -> tuple[np.ndarray, np.ndarray]:
    """Generate Z_th(t) on a log-spaced grid from a known Foster stack."""
    t = np.logspace(-5, 0, 80)
    z = np.zeros_like(t)
    for r, tau in zip(r_true, tau_true):
        z = z + r * (1.0 - np.exp(-t / tau))
    return t, z


def test_fit_zth_to_foster_recovers_known_three_stage_stack() -> None:
    r_true = [0.2, 0.4, 0.3]
    tau_true = [0.001, 0.01, 0.05]
    t, zth = _synthetic_three_stage_zth(r_true, tau_true)

    result = fit_zth_to_foster(t, zth, n_stages=3)

    assert result.n_stages == 3
    # Order by tau ascending so we can compare against the truth.
    order = np.argsort(result.tau_s)
    r_fit = [result.r_th_K_per_W[i] for i in order]
    tau_fit = [result.tau_s[i] for i in order]
    for r_f, r_t in zip(r_fit, r_true):
        assert abs(r_f - r_t) / r_t < 0.05, (
            f"R fit drift {r_f:.4g} vs truth {r_t:.4g} > 5 %"
        )
    for tau_f, tau_t in zip(tau_fit, tau_true):
        assert abs(tau_f - tau_t) / tau_t < 0.05, (
            f"τ fit drift {tau_f:.4g} vs truth {tau_t:.4g} > 5 %"
        )

    # C = τ / R for every stage (the GUI's persistence schema).
    for tau_f, r_f, c_f in zip(
        result.tau_s, result.r_th_K_per_W, result.c_th_J_per_K,
    ):
        assert abs(c_f - tau_f / r_f) < 1e-12


def test_fit_zth_evaluator_round_trips_within_tolerance() -> None:
    """``evaluate_foster_zth`` with the fitted stages must reconstruct
    the input curve to within the fitter's residual."""
    r_true = [0.2, 0.4, 0.3]
    tau_true = [0.001, 0.01, 0.05]
    t, zth = _synthetic_three_stage_zth(r_true, tau_true)
    result = fit_zth_to_foster(t, zth, n_stages=3)
    z_back = evaluate_foster_zth(t, result.r_th_K_per_W, result.tau_s)
    rms = float(np.sqrt(np.mean((z_back - zth) ** 2)))
    assert rms < 1e-3, f"Foster reconstruction RMS = {rms:.4g} K/W > 1 mK/W"


# ---------------------------------------------------------------------------
# FosterFitResult helpers
# ---------------------------------------------------------------------------


def test_foster_fit_result_csv_strings_round_trip() -> None:
    result = FosterFitResult(
        r_th_K_per_W=(0.2, 0.4, 0.3),
        tau_s=(0.001, 0.01, 0.05),
        c_th_J_per_K=(0.005, 0.025, 0.16666666666666666),
    )
    assert result.n_stages == 3
    r_csv = result.r_csv()
    c_csv = result.c_csv()

    # Re-parse the CSVs the way the GUI will: just split on comma + float().
    r_back = tuple(float(x) for x in r_csv.split(","))
    c_back = tuple(float(x) for x in c_csv.split(","))

    # Default format is ``{:.6g}`` — 6 significant figures, so the
    # repeating ``1/6`` truncates after the 6th digit. That's well
    # below any engineering tolerance for a thermal capacitance, so
    # we round-trip with a 0.001 % relative tolerance.
    assert r_back == pytest.approx(result.r_th_K_per_W, rel=1e-5)
    assert c_back == pytest.approx(result.c_th_J_per_K, rel=1e-5)


# ---------------------------------------------------------------------------
# Dialog widget construction (just enough to catch import + wire errors).
# ---------------------------------------------------------------------------


def test_dialog_constructs_and_responds_to_fit_button(qtbot) -> None:
    """Build the real dialog, paste the bundled example, click Fit, and
    confirm the CSV labels populate. Smoke test against signal-wiring
    regressions — not a math test."""
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    dialog = FosterFitDialog()
    qtbot.addWidget(dialog)

    # Click "Insert example" so we have data without filesystem I/O.
    dialog._on_insert_example()
    # And run the fit.
    dialog._on_fit_clicked()

    assert dialog._fit_result is not None
    assert dialog._fit_result.n_stages == 3
    assert dialog._copy_r_button.isEnabled()
    assert dialog._copy_c_button.isEnabled()
    # CSV labels should now hold tt-wrapped numbers, not "—".
    assert "—" not in dialog._r_csv_label.text()
    assert "—" not in dialog._c_csv_label.text()


# ---------------------------------------------------------------------------
# Apply-to-selected-device button
# ---------------------------------------------------------------------------


def _fake_main_window(*, selected_items: list, captured_commands: list):
    """A QWidget that quacks like a MainWindow for the dialog's Apply
    button + duck-typed selection walk. See the Thermal Sizing
    dialog's analogous test helper — same shape, different attributes
    don't matter for this dialog."""
    from PySide6.QtWidgets import QWidget

    class _FakeMainWindow(QWidget):
        def __init__(self):
            super().__init__()
            self._schematic_scene = type(
                "Scene", (), {"selectedItems": staticmethod(
                    lambda: list(selected_items),
                )},
            )()
            self._current_circuit = lambda: None

        def _execute_schematic_command(self, cmd, **kwargs):
            captured_commands.append(cmd)

    return _FakeMainWindow()


def _fake_item(component):
    import types
    return types.SimpleNamespace(component=component)


def test_apply_button_absent_when_no_main_window_parent(qtbot) -> None:
    """Standalone construction (no MainWindow-shaped parent) renders
    just the Copy buttons — no Apply, no status label. Avoids a
    button that would crash on click without the plumbing."""
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    dialog = FosterFitDialog()
    qtbot.addWidget(dialog)
    assert dialog._apply_button is None
    assert dialog._apply_status is None


def test_apply_button_present_when_parent_quacks_like_main_window(qtbot) -> None:
    """A MainWindow-shaped parent enables the Apply button — but it
    starts DISABLED until a fit runs (clicking before a fit would
    have no payload)."""
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    fake_mw = _fake_main_window(selected_items=[], captured_commands=[])
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    assert dialog._apply_button is not None
    assert dialog._apply_button.isEnabled() is False  # no fit yet
    # After a fit, the button enables.
    dialog._on_insert_example()
    dialog._on_fit_clicked()
    assert dialog._apply_button.isEnabled() is True


def test_apply_with_no_selection_returns_friendly_status(qtbot) -> None:
    """Click Apply when nothing is selected → status label asks the
    user to select a thermal-port device first; no command dispatched."""
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    captured: list = []
    fake_mw = _fake_main_window(selected_items=[], captured_commands=captured)
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._on_insert_example()
    dialog._on_fit_clicked()

    dialog._on_apply_clicked()
    assert dialog._apply_status is not None
    assert "thermal port" in dialog._apply_status.text().lower()
    assert captured == []


def test_apply_writes_both_csvs_and_sets_thermal_network_to_foster(qtbot) -> None:
    """The Apply button is the whole point of this slice — it writes
    BOTH CSVs into the selected device AND flips thermal_network to
    "foster" (the topology the fitter produces). Pin every parameter
    that lands in the dispatched command."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    mosfet = Component(type=ComponentType.MOSFET_N, name="Q_drive")
    mosfet.parameters["enable_thermal_port"] = True
    # Seed the legacy topology to ensure Apply flips it.
    mosfet.parameters["thermal_network"] = "cauer"

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(mosfet)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._on_insert_example()
    dialog._on_fit_clicked()
    fit = dialog._fit_result
    assert fit is not None

    dialog._on_apply_clicked()
    assert len(captured) == 1
    cmd = captured[0]
    new_state = getattr(cmd, "new_state", None) or getattr(cmd, "_new_state", None)
    assert new_state is not None
    params = new_state["parameters"]
    # Both CSVs land verbatim from the fit result.
    assert params["thermal_rth_stages"] == fit.r_csv()
    assert params["thermal_cth_stages"] == fit.c_csv()
    # Topology was forcibly flipped to "foster" — the Cauer interpretation
    # would silently miscompute T_j(t) from these τ-based stages.
    assert params["thermal_network"] == "foster"
    # Status text is success-shaped.
    assert dialog._apply_status is not None
    assert "Q_drive" in dialog._apply_status.text()


def test_apply_refuses_on_device_without_thermal_port(qtbot) -> None:
    """A MOSFET with ``enable_thermal_port=False`` should be REJECTED
    — writing thermal_rth_stages into a device that won't even
    instantiate a Foster network would silently produce stale-data
    bugs later."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    mosfet = Component(type=ComponentType.MOSFET_N, name="Q_no_port")
    mosfet.parameters["enable_thermal_port"] = False
    mosfet.parameters["thermal_enabled"] = False

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(mosfet)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._on_insert_example()
    dialog._on_fit_clicked()

    dialog._on_apply_clicked()
    assert captured == []
    assert dialog._apply_status is not None
    assert "thermal port" in dialog._apply_status.text().lower()


def test_apply_refuses_on_heatsink_selection(qtbot) -> None:
    """A HEATSINK has its own sink-side R + C fields — the Foster fit
    is for a DEVICE's junction-to-case ladder, not the sink-to-ambient
    path. Writing thermal_rth_stages to a HEATSINK would be silently
    nonsense, so refuse."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    hs = Component(type=ComponentType.HEATSINK, name="HS1")
    # HEATSINK doesn't have enable_thermal_port — irrelevant here, the
    # type check should refuse before even looking at flags.

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(hs)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._on_insert_example()
    dialog._on_fit_clicked()

    dialog._on_apply_clicked()
    assert captured == []


def test_apply_accepts_diode_with_thermal_enabled_legacy_flag(qtbot) -> None:
    """The dialog also accepts ``thermal_enabled=True`` (legacy /
    SharedHeatsink path), not just ``enable_thermal_port=True`` —
    they're synonyms in different places of the model layer."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.foster_fit_dialog import FosterFitDialog

    diode = Component(type=ComponentType.DIODE, name="D_freewheel")
    diode.parameters["thermal_enabled"] = True
    diode.parameters["enable_thermal_port"] = False

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(diode)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = FosterFitDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._on_insert_example()
    dialog._on_fit_clicked()

    dialog._on_apply_clicked()
    assert len(captured) == 1
    # CSVs landed, thermal_network forced to foster.
    new_state = getattr(captured[0], "new_state", None) or getattr(
        captured[0], "_new_state", None,
    )
    assert new_state["parameters"]["thermal_network"] == "foster"
