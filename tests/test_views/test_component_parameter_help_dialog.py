"""Tests for component parameter help content generation."""

from urllib.parse import parse_qs, unquote_plus, urlparse

from pulsimgui.models.component import Component, ComponentType
from pulsimgui.views.dialogs.component_parameter_help_dialog import (
    build_datasheet_search_url,
    build_component_help_rows,
    render_component_help_html,
)


def test_resistor_help_rows_include_resistance_reference() -> None:
    component = Component(type=ComponentType.RESISTOR, name="R1")
    rows = build_component_help_rows(component)
    by_name = {row.name: row for row in rows}

    assert "resistance" in by_name
    assert by_name["resistance"].default_value == "1000"
    assert "Datasheet" in by_name["resistance"].where_to_find


def test_pi_help_uses_controller_specific_kp_description() -> None:
    component = Component(type=ComponentType.PI_CONTROLLER, name="PI1")
    rows = build_component_help_rows(component)
    by_name = {row.name: row for row in rows}

    assert "kp" in by_name
    assert "Controller tuning" in by_name["kp"].where_to_find


def test_pwm_hidden_parameter_is_not_rendered() -> None:
    component = Component(type=ComponentType.PWM_GENERATOR, name="PWM1")
    names = {row.name for row in build_component_help_rows(component)}

    assert "frequency" in names
    assert "amplitude" not in names


def test_render_help_html_contains_parameter_table() -> None:
    component = Component(type=ComponentType.RESISTOR, name="R1")
    html = render_component_help_html(component)

    assert "Parameter" in html
    assert "Where to get it" in html
    assert "Open Datasheet Search" in html
    assert "resistance" in html


def test_build_datasheet_search_url_uses_part_number_and_datasheet_terms() -> None:
    component = Component(type=ComponentType.MOSFET_N, name="Q1")
    component.parameters["part_number"] = "IRF3205"

    url = build_datasheet_search_url(component, "vth")
    parsed = urlparse(url)
    query_raw = parse_qs(parsed.query)["q"][0]
    query = unquote_plus(query_raw)

    assert parsed.netloc == "www.google.com"
    assert "IRF3205" in query
    assert "VGS(th)" in query
    assert "datasheet" in query
