"""Unit tests for the TIM + Convection thermal-sizing dialog.

The dialog is a thin Qt wrapper around three pulsim 1.7 helpers
(``tim_resistance``, ``convection_resistance``, ``TIM_CATALOG``). We
hit the pure-Python module-level wrappers directly — they don't need
a QApplication — and exercise the widget tier only for construction
+ live-recompute wiring.
"""
from __future__ import annotations

import pytest

from pulsimgui.views.dialogs.thermal_sizing_dialog import (
    compute_convection_resistance,
    compute_tim_resistance,
    get_tim_catalog,
)


# ---------------------------------------------------------------------------
# compute_tim_resistance
# ---------------------------------------------------------------------------


def test_tim_resistance_custom_k_matches_closed_form() -> None:
    """``R_th = thickness / (k · area)`` — hand-check via the same
    formula pulsim documents. The GUI converts cm² → m² and mm → m at
    the boundary, so a 1 cm² × 0.1 mm × 3 W/m·K layer gives
    ``0.0001 m / (3 · 1e-4 m²)`` = 0.333 K/W."""
    r_th = compute_tim_resistance(
        area_cm2=1.0, thickness_mm=0.1, material=None, k_W_per_mK=3.0,
    )
    assert r_th == pytest.approx(0.3333, rel=1e-3)


def test_tim_resistance_catalog_material_pulls_k_from_pulsim() -> None:
    """A catalog material (``thermal_grease`` → 3 W/m·K per pulsim 1.7)
    yields the same answer as the explicit k=3 case. The test pins
    that pulsim's catalog is being consulted, not a hard-coded GUI
    map."""
    r_catalog = compute_tim_resistance(
        area_cm2=1.0, thickness_mm=0.1, material="thermal_grease",
        k_W_per_mK=None,
    )
    r_custom = compute_tim_resistance(
        area_cm2=1.0, thickness_mm=0.1, material=None, k_W_per_mK=3.0,
    )
    assert r_catalog == pytest.approx(r_custom, rel=1e-6)


def test_tim_resistance_zero_area_raises_value_error() -> None:
    """The dialog catches this and shows a friendly readout — but the
    pure function rejects so the test can pin the contract."""
    with pytest.raises(ValueError, match="area"):
        compute_tim_resistance(
            area_cm2=0.0, thickness_mm=0.1, material=None, k_W_per_mK=3.0,
        )


def test_tim_resistance_zero_thickness_raises_value_error() -> None:
    """Zero thickness is non-physical (and would give R_th=0). Reject
    early so the dialog surfaces the issue instead of a divide-by-zero."""
    with pytest.raises(ValueError, match="thickness"):
        compute_tim_resistance(
            area_cm2=1.0, thickness_mm=0.0, material=None, k_W_per_mK=3.0,
        )


# ---------------------------------------------------------------------------
# compute_convection_resistance
# ---------------------------------------------------------------------------


def test_convection_resistance_natural_air_for_200cm2_sink() -> None:
    """200 cm² heatsink in still air via pulsim's default
    ``convection_coefficient(0)`` ≈ 10 W/m²K → R_th = 1/(10 · 0.02) =
    5 K/W. We hand-check against pulsim's exact value rather than
    asserting "around 5" — the test pins the wrapper, not the
    estimator."""
    r_th_no_h = compute_convection_resistance(
        area_cm2=200.0, airflow_m_per_s=0.0, h_W_per_m2K=None,
    )
    # Re-derive what pulsim's helper alone gives us for h, then build
    # the closed-form check from the SI conversion.
    import pulsim.thermal as pt
    h = pt.convection_coefficient(airflow_m_per_s=0.0)
    expected = 1.0 / (h * 200e-4)
    assert r_th_no_h == pytest.approx(expected, rel=1e-6)


def test_convection_resistance_explicit_h_overrides_airflow_estimate() -> None:
    """When the user passes ``h``, the airflow value should be
    ignored. We pass airflow=99 m/s (would yield a tiny R_th) along
    with h=10 W/m²K and verify the result tracks the explicit h, not
    the airflow."""
    r_th = compute_convection_resistance(
        area_cm2=200.0, airflow_m_per_s=99.0, h_W_per_m2K=10.0,
    )
    expected = 1.0 / (10.0 * 200e-4)  # 5 K/W
    assert r_th == pytest.approx(expected, rel=1e-6)


def test_convection_resistance_zero_area_raises_value_error() -> None:
    with pytest.raises(ValueError, match="area"):
        compute_convection_resistance(
            area_cm2=0.0, airflow_m_per_s=2.0, h_W_per_m2K=None,
        )


def test_convection_resistance_negative_airflow_raises_value_error() -> None:
    """Negative airflow is meaningless. We reject up-front so the
    spin's clamp behaviour can't leak garbage through."""
    with pytest.raises(ValueError, match="airflow"):
        compute_convection_resistance(
            area_cm2=200.0, airflow_m_per_s=-1.0, h_W_per_m2K=None,
        )


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


def test_tim_catalog_contains_expected_materials() -> None:
    """Sanity check that pulsim 1.7's catalog is reachable through the
    wrapper. Loose check — we don't pin exact values (pulsim may tune
    them), just that a few canonical materials are present with
    positive k."""
    catalog = get_tim_catalog()
    assert len(catalog) >= 4
    expected = {"thermal_grease", "silicone_pad", "ceramic_grease"}
    found = set(catalog.keys()) & expected
    assert len(found) >= 2, f"missing canonical materials: {expected - found}"
    for name, k in catalog.items():
        assert k > 0, f"{name} has non-positive conductivity {k}"


# ---------------------------------------------------------------------------
# Widget tier — construction + live-recompute via qtbot
# ---------------------------------------------------------------------------


def test_tim_sizer_widget_starts_with_finite_R_th(qtbot) -> None:
    """Default-constructed widget shows a non-None ``current_R_th``
    so the user immediately sees a sensible starting answer rather
    than an empty placeholder."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import TIMSizerWidget

    w = TIMSizerWidget()
    qtbot.addWidget(w)
    r_th = w.current_R_th()
    assert r_th is not None
    assert r_th > 0


def test_tim_sizer_widget_recomputes_when_area_changes(qtbot) -> None:
    """Doubling the contact area halves R_th. This exercises the
    valueChanged → _recompute wiring without touching pulsim's math."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import TIMSizerWidget

    w = TIMSizerWidget()
    qtbot.addWidget(w)
    initial = w.current_R_th()
    assert initial is not None
    # Bump area 1 cm² → 2 cm². R_th ∝ 1/area → result halves.
    w._area_spin.setValue(2.0)
    after = w.current_R_th()
    assert after is not None
    assert after == pytest.approx(initial / 2.0, rel=1e-3)


def test_convection_sizer_widget_starts_with_finite_R_th(qtbot) -> None:
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ConvectionSizerWidget,
    )

    w = ConvectionSizerWidget()
    qtbot.addWidget(w)
    r_th = w.current_R_th()
    assert r_th is not None
    assert r_th > 0


def test_full_dialog_constructs_all_three_tabs(qtbot) -> None:
    """End-to-end construction check — the dialog has 3 tabs and
    exposes the two calculators via properties so callers (and tests)
    can inspect their values."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )

    dialog = ThermalSizingDialog()
    qtbot.addWidget(dialog)
    assert dialog._tabs.count() == 3
    assert dialog.tim_sizer.current_R_th() is not None
    assert dialog.convection_sizer.current_R_th() is not None


# ---------------------------------------------------------------------------
# Apply-to-selected callbacks
# ---------------------------------------------------------------------------


def _fake_main_window(*, selected_items: list, captured_commands: list):
    """A QWidget subclass that quacks like enough of a MainWindow for
    the dialog's Apply buttons + duck-typed selection walk to work.

    Two reasons we need a real QWidget rather than a SimpleNamespace:
      * ``QDialog(parent=...)`` validates the parent's runtime type.
      * The dialog uses ``self.parent()`` (a Qt accessor) to reach
        the main window — that only returns objects Qt set via the
        parent slot.

    Quacks like:
      * ``_schematic_scene.selectedItems()`` → list of fake items
        (each with a ``.component`` attribute, duck-typed against
        the dialog's filter).
      * ``_execute_schematic_command(cmd, **k)`` → records the cmd.
      * ``_current_circuit()`` → returns None (the command snapshots
        don't need a real circuit, just the component dict shape).
    """
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
    """An object that duck-types as a ComponentItem for the dialog's
    selection walk — it just exposes ``.component``."""
    import types
    return types.SimpleNamespace(component=component)


def test_apply_callback_omitted_when_no_main_window_parent(qtbot) -> None:
    """Without a MainWindow-shaped parent the Apply buttons must not
    render — otherwise the user gets a button that crashes on click."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )

    dialog = ThermalSizingDialog()
    qtbot.addWidget(dialog)
    assert dialog.tim_sizer._apply_button is None
    assert dialog.convection_sizer._apply_button is None


def test_apply_buttons_present_when_parent_looks_like_main_window(qtbot) -> None:
    """A parent that quacks like a MainWindow enables the Apply
    buttons. Both sub-widgets must show one."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    fake_mw = _fake_main_window(selected_items=[], captured_commands=[])
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    assert dialog.tim_sizer._apply_button is not None
    assert dialog.convection_sizer._apply_button is not None


def test_apply_with_no_selection_returns_user_friendly_message(qtbot) -> None:
    """Click "Apply to HS" when nothing is selected → status label
    asks the user to select a HEATSINK first; no mutation attempted."""
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    captured: list = []
    fake_mw = _fake_main_window(selected_items=[], captured_commands=captured)
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    status = dialog._apply_to_selected_heatsink_convection(5.0)
    assert "Select a HEATSINK" in status
    assert captured == []


def test_apply_convection_writes_R_th_sink_to_amb_on_selected_heatsink(qtbot) -> None:
    """Selected HEATSINK + clicked Apply → an
    ``UpdateComponentStateCommand`` runs through the schematic pipeline
    with the new ``R_th_sink_to_amb_K_per_W`` in its patch."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    hs = Component(type=ComponentType.HEATSINK, name="HS1")

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(hs)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    status = dialog._apply_to_selected_heatsink_convection(7.5)

    assert "HS1" in status
    assert "7.5" in status
    assert len(captured) == 1
    cmd = captured[0]
    # ``UpdateComponentStateCommand`` exposes ``new_state``.
    new_state = getattr(cmd, "new_state", None) or getattr(cmd, "_new_state", None)
    assert new_state is not None
    assert new_state["parameters"]["R_th_sink_to_amb_K_per_W"] == 7.5


def test_apply_tim_appends_into_first_slot_of_case_csv(qtbot) -> None:
    """The TIM tab writes into ``case_to_sink_R_th_csv`` slot 1 while
    preserving slots 2+. This lets the user fill the first device's
    TIM via the dialog and edit the rest manually."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    hs = Component(type=ComponentType.HEATSINK, name="HS_PFC")
    hs.parameters["case_to_sink_R_th_csv"] = "0.3, 0.5, 0.7"

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(hs)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    status = dialog._apply_to_selected_heatsink_tim(0.42)

    assert "HS_PFC" in status
    assert "slot 1" in status
    assert len(captured) == 1
    new_state = getattr(captured[0], "new_state", None) or getattr(
        captured[0], "_new_state", None,
    )
    csv = new_state["parameters"]["case_to_sink_R_th_csv"]
    parts = [t.strip() for t in csv.split(",")]
    assert parts[0] == "0.42"
    assert parts[1] == "0.5"
    assert parts[2] == "0.7"


def test_apply_tim_on_empty_csv_creates_first_slot(qtbot) -> None:
    """A HEATSINK that has never had case_to_sink CSV edited starts
    with an empty string. Applying TIM creates a single-entry CSV
    (the converter reads remaining slots as 0, which is the right
    default)."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    hs = Component(type=ComponentType.HEATSINK, name="HS")
    hs.parameters["case_to_sink_R_th_csv"] = ""

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(hs)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    dialog._apply_to_selected_heatsink_tim(0.5)

    new_state = getattr(captured[0], "new_state", None) or getattr(
        captured[0], "_new_state", None,
    )
    assert new_state["parameters"]["case_to_sink_R_th_csv"] == "0.5"


def test_apply_ignores_non_heatsink_selection(qtbot) -> None:
    """If the user has a MOSFET selected (not a HEATSINK), the Apply
    button must refuse — not write to the wrong component."""
    from pulsimgui.models.component import Component, ComponentType
    from pulsimgui.views.dialogs.thermal_sizing_dialog import (
        ThermalSizingDialog,
    )
    mosfet = Component(type=ComponentType.MOSFET_N, name="Q1")

    captured: list = []
    fake_mw = _fake_main_window(
        selected_items=[_fake_item(mosfet)], captured_commands=captured,
    )
    qtbot.addWidget(fake_mw)
    dialog = ThermalSizingDialog(parent=fake_mw)
    qtbot.addWidget(dialog)
    status = dialog._apply_to_selected_heatsink_convection(5.0)
    assert "Select a HEATSINK" in status
    assert captured == []
