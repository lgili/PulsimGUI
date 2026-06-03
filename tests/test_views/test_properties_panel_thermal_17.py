"""Tests for the pulsim 1.7 thermal fields rendering in the inspector.

The properties panel dispatches by VALUE TYPE (bool → checkbox,
float/int → SI widget with unit suffix, str with PARAM_OPTIONS → combo,
str without → line edit), so the 5 new keys we added to
``DEFAULT_THERMAL_DEVICE_PARAMS`` should appear automatically:

  * ``thermal_t_max_C``               (float → SI with °C suffix)
  * ``thermal_t_max_hysteresis_C``    (float → SI with °C suffix)
  * ``loss_a_cond_per_C``             (float → SI with 1/°C suffix)
  * ``loss_a_sw_per_C``               (float → SI with 1/°C suffix)
  * (``thermal_network`` is reused as the Foster/Cauer toggle — combo)

These tests pin:

  1. The fields render at all (widget created in the panel).
  2. Each carries the correct SI unit suffix (so the user sees
     "°C" / "1/°C" instead of a bare number).
  3. Each has a descriptive tooltip (so the user has *some* hint
     about what the field controls without reading source).
  4. ``thermal_network`` combo carries all three values (single_rc,
     foster, cauer) — this is the consolidated Foster/Cauer toggle
     that the backend reads.
"""
from __future__ import annotations

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.properties import PropertiesPanel


def _mosfet_with_thermal_port() -> Component:
    """A MOSFET_N with the thermal port enabled — that's the gate
    that surfaces every ``DEFAULT_THERMAL_DEVICE_PARAMS`` key into
    the component's params dict."""
    comp = Component(type=ComponentType.MOSFET_N, name="Q1")
    comp.parameters["enable_thermal_port"] = True
    # Ensure the new pulsim-1.7 keys are present (defaults are 0).
    for key in (
        "thermal_t_max_C", "thermal_t_max_hysteresis_C",
        "loss_a_cond_per_C", "loss_a_sw_per_C",
    ):
        comp.parameters.setdefault(key, 0.0)
    comp.parameters.setdefault("thermal_network", "foster")
    return comp


def test_new_thermal_fields_render_in_inspector(qapp) -> None:
    """When a MOSFET with ``enable_thermal_port=True`` is selected,
    every new pulsim-1.7 thermal key must end up in the panel's
    ``_widgets`` dict — confirms the type-dispatched widget loop
    picks them up without explicit per-key wiring."""
    panel = PropertiesPanel()
    panel.set_component(_mosfet_with_thermal_port())
    for key in (
        "thermal_t_max_C", "thermal_t_max_hysteresis_C",
        "loss_a_cond_per_C", "loss_a_sw_per_C",
        "thermal_network",
    ):
        assert key in panel._widgets, f"{key} missing from inspector"


def test_new_thermal_fields_have_si_unit_suffix(qapp) -> None:
    """Each numeric thermal field carries the right SI unit so the
    user sees ``150 °C`` / ``0.006 1/°C`` instead of a bare number.
    Pin via the panel's ``_get_unit_for_param`` lookup so we don't
    have to drive the SIValueWidget rendering directly."""
    panel = PropertiesPanel()
    assert panel._get_unit_for_param("thermal_t_max_C") == "°C"
    assert panel._get_unit_for_param("thermal_t_max_hysteresis_C") == "°C"
    assert panel._get_unit_for_param("loss_a_cond_per_C") == "1/°C"
    assert panel._get_unit_for_param("loss_a_sw_per_C") == "1/°C"


def test_new_thermal_fields_have_descriptive_tooltips(qapp) -> None:
    """Each new field has a non-empty tooltip. The string content is
    a soft promise (it'll evolve as docs improve), but the *presence*
    is a hard contract — the user must have *some* hint about what
    each field does without reading source."""
    panel = PropertiesPanel()
    for key in (
        "thermal_t_max_C", "thermal_t_max_hysteresis_C",
        "loss_a_cond_per_C", "loss_a_sw_per_C",
        "thermal_network",
        # HEATSINK component fields too — they didn't have tooltips
        # before this slice either.
        "R_th_sink_to_amb_K_per_W", "C_th_sink_J_per_K", "T_amb_C",
        "case_to_sink_R_th_csv", "n_devices",
    ):
        tooltip = panel._get_tooltip_for_param(key)
        assert tooltip, f"{key} missing tooltip"
        assert len(tooltip) > 20, f"{key} tooltip too short: {tooltip!r}"


def test_thermal_network_combo_carries_all_three_values(qapp) -> None:
    """The consolidated Foster/Cauer/Single_RC toggle must expose all
    three options to the user — the backend reads "cauer" → Cauer
    stages, anything else → Foster stages. Hiding the option from the
    combo would silently lock users out of the Cauer path."""
    from pulsimgui.models.component import PARAM_OPTIONS
    options = PARAM_OPTIONS.get("thermal_network", [])
    assert set(options) == {"single_rc", "foster", "cauer"}
