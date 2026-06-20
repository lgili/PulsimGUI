"""Smoke + behaviour tests for the design-system component layer.

These keep the styled primitives honest: every one must build headless,
carry its scoped ``objectName`` (so its QSS doesn't leak), survive a live
theme switch, and produce a non-empty stylesheet from the tokens. They do
NOT pixel-compare — that's what scripts/design_gallery.py is for.
"""
from __future__ import annotations

import sys

import pytest
from PySide6.QtWidgets import QApplication, QLabel

from pulsimgui.services.theme_service import ThemeService
from pulsimgui.views.design import (
    BrandChip,
    Card,
    KpiTile,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SectionHeader,
    SegmentedControl,
    StatusBadge,
)
from pulsimgui.views.design.components import _tint


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication(sys.argv)


@pytest.fixture
def theme_service():
    return ThemeService()


def test_every_component_builds_with_scoped_object_name(theme_service) -> None:
    """Each primitive builds and tags itself with a Design* objectName so
    its ``#ObjectName`` QSS selector stays scoped to itself."""
    cases = [
        (Card(theme_service), "DesignCard"),
        (PageHeader("T", "S", theme_service), "DesignPageHeader"),
        (SectionHeader("S", theme_service), "DesignSectionHeader"),
        (KpiTile("L", "1", "V", theme_service), "DesignKpiTile"),
        (StatusBadge("OK", "success", theme_service), "DesignStatusBadge"),
        (PrimaryButton("Run", theme_service), "DesignPrimaryButton"),
        (SecondaryButton("Cancel", theme_service), "DesignSecondaryButton"),
        (SegmentedControl([("a", "A"), ("b", "B")], theme_service), "DesignSegmented"),
    ]
    for widget, name in cases:
        assert widget.objectName() == name
        # The QSS came from tokens and is non-trivial.
        assert name in widget.styleSheet()


def test_components_restyle_on_theme_change(theme_service) -> None:
    """Switching the theme re-applies each component's stylesheet — the
    whole point of routing styling through the service instead of a
    one-shot inline setStyleSheet."""
    theme_service.set_theme("light")
    card = Card(theme_service)
    light_qss = card.styleSheet()
    theme_service.set_theme("dark")
    dark_qss = card.styleSheet()
    assert light_qss != dark_qss, "card did not re-theme on theme_changed"
    # And it tracked the dark surface token.
    assert theme_service.current_theme.colors.background in dark_qss


def test_components_work_without_a_theme_service() -> None:
    """A None service must not crash (standalone previews / tests) — it
    falls back to the light theme."""
    w = KpiTile("L", "42", "W")  # no service
    assert "DesignKpiTile" in w.styleSheet()


def test_status_badge_kind_switch_recolours(theme_service) -> None:
    badge = StatusBadge("X", "neutral", theme_service)
    neutral = badge.styleSheet()
    badge.set_kind("error")
    err = badge.styleSheet()
    assert neutral != err
    assert theme_service.current_theme.colors.error in err


def test_kpi_accent_recolours_value(theme_service) -> None:
    tile = KpiTile("L", "1", "V", theme_service)
    plain = tile.styleSheet()
    tile.set_accent("warning")
    warn = tile.styleSheet()
    assert plain != warn
    assert theme_service.current_theme.colors.warning in warn


def test_kpi_set_label_updates_uppercased(theme_service) -> None:
    """set_label folds a subject into the tile (e.g. HOTTEST · Q_BOOST),
    uppercased to match construction."""
    tile = KpiTile("Hottest", "127", "°C", theme_service)
    tile.set_label("Hottest · Q_boost")
    assert tile._label.text() == "HOTTEST · Q_BOOST"


def test_segmented_control_emits_and_tracks_selection(theme_service, qtbot=None) -> None:
    seg = SegmentedControl([("pwl", "PWL"), ("dsed", "DSED")], theme_service)
    assert seg.current_key() == "pwl"  # first is default-selected
    received: list[str] = []
    seg.changed.connect(received.append)
    seg._select("dsed")
    assert seg.current_key() == "dsed"
    assert received == ["dsed"]


def test_brand_chip_builds_and_carries_wordmark(theme_service) -> None:
    """The menu-bar brand mark builds, tags its objectName, and renders the
    'Pulsim' + muted 'Studio' wordmark in the active theme's colours."""
    chip = BrandChip(theme_service)
    assert chip.objectName() == "DesignBrandChip"
    # The wordmark is set from theme tokens (rich text).
    wordmark = chip.findChild(QLabel, "DesignBrandWordmark")
    assert wordmark is not None
    assert "Pulsim" in wordmark.text() and "Studio" in wordmark.text()
    assert theme_service.current_theme.colors.foreground in wordmark.text()


def test_tint_produces_rgba_from_hex() -> None:
    assert _tint("#2563eb", 38) == "rgba(37, 99, 235, 0.149)"
    # short form + missing-# tolerated
    assert _tint("fff", 255) == "rgba(255, 255, 255, 1.000)"
    # garbage degrades to black, never raises
    assert _tint("nothex", 255).startswith("rgba(0, 0, 0")
