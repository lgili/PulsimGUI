"""Smoke tests for ``BaseScopeWindow`` shell construction."""

from __future__ import annotations


def test_shell_boots_with_electrical_variant(qapp) -> None:
    """A bare shell with the electrical variant has no signals + no capabilities."""
    from pulsimgui.views.scope_v2 import BaseScopeWindow
    from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant

    window = BaseScopeWindow(variant=ElectricalScopeVariant(name="Scope: test"))
    try:
        assert window.windowTitle() == "Scope: test"
        # No capabilities attached → no signals registered.
        assert list(window.plot_canvas.signals()) == []
        # Both sidebar + inspector are visible (not collapsed).
        assert not window.sidebar._collapsed
        assert not window.inspector._collapsed
    finally:
        window.close()


def test_shell_boots_with_thermal_variant(qapp) -> None:
    """The thermal variant flips the accent + badge but keeps the same chrome."""
    from pulsimgui.views.scope_v2 import BaseScopeWindow
    from pulsimgui.views.scope_v2.variants import ThermalScopeVariant

    window = BaseScopeWindow(variant=ThermalScopeVariant(name="Thermal Scope: Q1"))
    try:
        assert window.windowTitle() == "Thermal Scope: Q1"
        # The header badge mirrors the variant's ``type_label`` field.
        assert window.header._variant.type_label == "thermal"
        # Variant uses the orange accent (vs electrical's blue).
        assert window.header._variant.accent_color == "#f59e0b"
    finally:
        window.close()


def test_shell_toolbar_buttons_are_present(qapp) -> None:
    """All 11 toolbar buttons exist with the expected toggle state."""
    from pulsimgui.views.scope_v2 import BaseScopeWindow
    from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant

    window = BaseScopeWindow(variant=ElectricalScopeVariant())
    try:
        toolbar = window.toolbar
        # Transport: run / pause / stop are not toggles.
        assert not toolbar.btn_run.isCheckable()
        assert not toolbar.btn_pause.isCheckable()
        assert not toolbar.btn_stop.isCheckable()
        # View toggles default to "panel visible".
        assert toolbar.btn_sidebar.isCheckable()
        assert toolbar.btn_sidebar.isChecked()
        assert toolbar.btn_inspector.isCheckable()
        assert toolbar.btn_inspector.isChecked()
        # Cursor is off by default; grid is on by default.
        assert toolbar.btn_cursor.isCheckable() and not toolbar.btn_cursor.isChecked()
        assert toolbar.btn_grid.isCheckable() and toolbar.btn_grid.isChecked()
        # FFT is a toggle, math + export are buttons.
        assert toolbar.btn_fft.isCheckable() and not toolbar.btn_fft.isChecked()
        assert not toolbar.btn_math.isCheckable()
        assert not toolbar.btn_export.isCheckable()
    finally:
        window.close()
