"""Tests for theme token and palette helpers."""

from __future__ import annotations

from PySide6.QtGui import QColor

from pulsimgui.services.theme_service import BUILTIN_THEMES, ThemeService


def _rgb(color: str) -> tuple[int, int, int]:
    qcolor = QColor(color)
    return (qcolor.red(), qcolor.green(), qcolor.blue())


def test_trace_palette_starts_with_theme_primary():
    """Trace palette should keep primary accent as first signal color."""
    service = ThemeService()
    theme = BUILTIN_THEMES["light"]

    palette = service.get_trace_palette(theme)

    assert len(palette) >= 6
    assert palette[0] == _rgb(theme.colors.primary)


def test_cursor_palette_matches_error_and_primary_tokens():
    """Cursor colors should map to theme error/primary semantics."""
    service = ThemeService()

    for theme in BUILTIN_THEMES.values():
        palette = service.get_cursor_palette(theme)
        assert len(palette) == 2
        assert palette[0] == _rgb(theme.colors.error)
        assert palette[1] == _rgb(theme.colors.primary)


def test_hex_to_rgb_fallback_for_invalid_literal():
    """Invalid literals must degrade safely to magenta fallback."""
    assert ThemeService._hex_to_rgb("not-a-color") == (255, 0, 255)


def test_builtin_themes_define_plot_and_overlay_tokens():
    """All built-in themes must define valid plot/overlay tokens."""
    required = (
        "overlay_pin_highlight",
        "overlay_alignment_guides",
        "overlay_drop_preview_fill",
        "overlay_drop_preview_border",
        "overlay_minimap_viewport_fill",
        "overlay_minimap_viewport_border",
        "plot_background",
        "plot_grid",
        "plot_axis",
        "plot_text",
        "plot_legend_background",
        "plot_legend_border",
    )

    for theme in BUILTIN_THEMES.values():
        for token in required:
            value = getattr(theme.colors, token)
            assert isinstance(value, str)
            assert value
            assert QColor(value).isValid(), f"{theme.name}.{token} must be a valid color"
