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
