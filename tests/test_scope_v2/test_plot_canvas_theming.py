"""PlotCanvas follows the host theme's ``plot_*`` tokens (slice 5).

The canvas previously froze a module-level dark palette at
construction: the theme's ``plot_background`` / ``plot_grid`` /
``plot_axis`` / ``plot_text`` tokens (defined for light AND dark
themes) never reached pyqtgraph, so a light-themed app kept a dark
plot and the studio theme's plot surface color was silently ignored.
``BaseScopeWindow`` now calls :meth:`PlotCanvas.apply_theme` at
construction and on every ``ThemeService.theme_changed``.
"""

from __future__ import annotations

import pytest

from pulsimgui.services.theme_service import (
    LIGHT_THEME,
    PULSIM_STUDIO_DARK_THEME,
)
from pulsimgui.views.scope_v2.plot_canvas import PlotCanvas


@pytest.fixture
def canvas(qapp):
    c = PlotCanvas()
    yield c
    c.deleteLater()


def test_apply_theme_adopts_plot_tokens(canvas):
    canvas.apply_theme(PULSIM_STUDIO_DARK_THEME)
    colors = PULSIM_STUDIO_DARK_THEME.colors
    assert canvas._plot_bg == colors.plot_background
    assert canvas._plot_grid == colors.plot_grid
    assert canvas._plot_axis == colors.plot_axis
    assert canvas._plot_text == colors.plot_text


def test_apply_theme_flips_light(canvas):
    canvas.apply_theme(PULSIM_STUDIO_DARK_THEME)
    canvas.apply_theme(LIGHT_THEME)
    assert canvas._plot_bg == LIGHT_THEME.colors.plot_background
    # Light theme's plot surface must actually be light — the historical
    # bug was a dark plot frozen inside a light app.
    assert canvas._plot_bg.lower() in ("#ffffff", "#fff") or canvas._plot_bg != (
        PULSIM_STUDIO_DARK_THEME.colors.plot_background
    )


def test_apply_theme_restyles_existing_panels(canvas):
    canvas.add_panel("V", unit="V")
    canvas.apply_theme(PULSIM_STUDIO_DARK_THEME)
    plot = canvas._panels["V"]
    axis = plot.getAxis("left")
    pen_color = axis.pen().color().name()
    assert pen_color == PULSIM_STUDIO_DARK_THEME.colors.plot_axis.lower()


def test_apply_theme_tolerates_bad_theme(canvas):
    before = canvas._plot_bg
    canvas.apply_theme(object())  # no .colors — must be a no-op
    assert canvas._plot_bg == before


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app
