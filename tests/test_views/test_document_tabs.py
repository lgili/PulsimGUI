"""Tests for the PSIM-style document tabs in MainWindow.

Each tab is an independent :class:`~pulsimgui.models.project.Project`
(its own file, dirty flag, circuits). A single shared scene/view renders
whichever document is active; switching rebinds that scene and saves /
restores per-tab viewport state. These tests exercise the tab lifecycle
(create / switch / close / rename / open-dedup) and the dirty guards,
all headless (no simulation).
"""
from __future__ import annotations

import pytest

import pulsimgui.views.main_window as main_window_module
from pulsimgui.models.component import ComponentType
from pulsimgui.models.project import Project
from pulsimgui.views.editor_document import EditorDocument
from pulsimgui.views.main_window import MainWindow


@pytest.fixture(autouse=True)
def _no_close_prompt(monkeypatch):
    """Neutralize the save-on-close prompt.

    Several of these tests intentionally leave a tab dirty. On a real Qt
    platform ``window.close()`` would then pop a modal ``QMessageBox`` via
    ``_check_save_all`` and block the headless run forever. Closing the
    window is not what we're asserting here, so stub the all-tabs guard to
    a clean exit. The per-tab ``_check_save`` used by ``_close_document``
    is a different method and stays live (the cancel/proceed tests patch
    it directly)."""
    monkeypatch.setattr(MainWindow, "_check_save_all", lambda self: True)


# ---------------------------------------------------------------------------
# EditorDocument label semantics
# ---------------------------------------------------------------------------
def test_title_shows_dirty_dot_and_prefers_display_name() -> None:
    """``title`` prefers an explicit rename, falls back to file stem then
    project name, and prefixes a bullet when the project is dirty."""
    doc = EditorDocument(Project(name="Buck"))
    assert doc.title == "Buck"  # clean, untitled → project name

    doc.project.mark_dirty()
    assert doc.title == "• Buck"  # dirty → bullet

    doc.display_name = "Renamed"
    assert doc.title == "• Renamed"  # explicit rename wins
    assert doc.tooltip == "(unsaved)"


# ---------------------------------------------------------------------------
# Creating tabs
# ---------------------------------------------------------------------------
def test_starts_with_single_tab(qapp) -> None:
    window = MainWindow()
    try:
        assert window._tab_bar.count() == 1
        assert len(window._documents) == 1
        assert window._active_doc == 0
        assert window._project is window._documents[0].project
    finally:
        window.close()


def test_new_on_pristine_tab_is_reused(qapp) -> None:
    """New on a blank/untitled/clean tab reuses it (no clutter)."""
    window = MainWindow()
    try:
        window._on_new_project()
        assert window._tab_bar.count() == 1
    finally:
        window.close()


def test_new_on_dirty_tab_opens_new_tab(qapp) -> None:
    """New when the active tab has unsaved content opens a fresh tab and
    leaves the original intact (never destroys unsaved work)."""
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        first_project = window._project
        assert first_project.is_dirty

        window._on_new_project()
        assert window._tab_bar.count() == 2
        assert window._active_doc == 1
        # Original tab still holds the resistor.
        assert window._documents[0].project is first_project
        assert window._documents[0].project.get_active_circuit().components
        # New tab is a fresh empty project.
        assert not window._project.get_active_circuit().components
    finally:
        window.close()


def test_plus_button_handler_adds_tab(qapp) -> None:
    window = MainWindow()
    try:
        window._on_new_tab_clicked()
        assert window._tab_bar.count() == 2
        assert window._active_doc == 1
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Switching tabs
# ---------------------------------------------------------------------------
def test_switch_follows_active_project(qapp) -> None:
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        doc0 = window._documents[0].project
        window._on_new_project()  # tab1 active
        doc1 = window._documents[1].project
        assert window._project is doc1

        # User-style switch via the tab bar (emits currentChanged).
        window._tab_bar.setCurrentIndex(0)
        assert window._active_doc == 0
        assert window._project is doc0

        window._tab_bar.setCurrentIndex(1)
        assert window._project is doc1
    finally:
        window.close()


def test_switch_saves_and_restores_view_transform(qapp) -> None:
    from PySide6.QtGui import QTransform

    window = MainWindow()
    try:
        window._on_new_tab_clicked()  # now 2 tabs, active=1
        # Give each tab a distinct zoom.
        window._schematic_view.setTransform(QTransform().scale(3.0, 3.0))
        window._capture_view_state(1)
        window._tab_bar.setCurrentIndex(0)
        window._schematic_view.setTransform(QTransform().scale(1.5, 1.5))
        window._capture_view_state(0)

        # Switch back to tab1 → its 3.0x zoom returns.
        window._tab_bar.setCurrentIndex(1)
        assert round(window._schematic_view.transform().m11(), 3) == 3.0
        # And tab0 keeps its 1.5x.
        window._tab_bar.setCurrentIndex(0)
        assert round(window._schematic_view.transform().m11(), 3) == 1.5
    finally:
        window.close()


def test_keyboard_next_prev_tab(qapp) -> None:
    window = MainWindow()
    try:
        window._on_new_tab_clicked()
        window._on_new_tab_clicked()  # 3 tabs, active=2
        window._on_next_tab()
        assert window._active_doc == 0  # wraps
        window._on_prev_tab()
        assert window._active_doc == 2  # wraps back
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Closing tabs
# ---------------------------------------------------------------------------
def test_close_background_tab_keeps_active(qapp) -> None:
    window = MainWindow()
    try:
        window._on_new_tab_clicked()
        window._on_new_tab_clicked()  # 3 tabs, active=2
        active_project = window._project
        # Close tab 0 (a background tab).
        window._close_document(0)
        assert window._tab_bar.count() == 2
        # Active document identity is preserved (index shifted 2 → 1).
        assert window._project is active_project
        assert window._active_doc == 1
    finally:
        window.close()


def test_close_active_tab_selects_neighbor(qapp) -> None:
    window = MainWindow()
    try:
        window._on_new_tab_clicked()  # 2 tabs, active=1
        survivor = window._documents[0].project
        window._close_document(1)  # close the active tab
        assert window._tab_bar.count() == 1
        assert window._active_doc == 0
        assert window._project is survivor
    finally:
        window.close()


def test_close_last_tab_blanks_it(qapp) -> None:
    """Closing the only tab resets it to a fresh blank project rather than
    leaving the editor with zero tabs."""
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        # Mark clean so close doesn't prompt.
        window._project.mark_clean()
        old_project = window._project

        window._close_document(0)
        assert window._tab_bar.count() == 1
        assert window._project is not old_project
        assert not window._project.get_active_circuit().components
    finally:
        window.close()


def test_close_dirty_tab_can_be_cancelled(monkeypatch, qapp) -> None:
    """A dirty tab prompts to save; cancelling aborts the close."""
    window = MainWindow()
    try:
        window._on_new_tab_clicked()  # 2 tabs
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        assert window._project.is_dirty
        # Simulate the user pressing Cancel in the save dialog.
        monkeypatch.setattr(window, "_check_save", lambda: False)
        window._close_document(window._active_doc)
        # Nothing was closed.
        assert window._tab_bar.count() == 2
    finally:
        window.close()


def test_cancel_closing_dirty_background_tab_restores_focus(monkeypatch, qapp) -> None:
    """Cancelling the close of a dirty *background* tab must not leave the
    user parked on the tab they declined to close — focus returns to where
    they were."""
    window = MainWindow()
    try:
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)  # tab0 dirty
        window._on_new_tab_clicked()  # tab1 created + active
        assert window._active_doc == 1
        # User cancels the save prompt when closing the background dirty tab0.
        monkeypatch.setattr(window, "_check_save", lambda: False)
        window._close_document(0)
        assert window._tab_bar.count() == 2  # nothing closed
        assert window._active_doc == 1  # focus restored to where we were
    finally:
        window.close()


def test_close_dirty_tab_proceeds_when_saved(monkeypatch, qapp) -> None:
    window = MainWindow()
    try:
        window._on_new_tab_clicked()  # 2 tabs, active=1
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)
        monkeypatch.setattr(window, "_check_save", lambda: True)
        window._close_document(window._active_doc)
        assert window._tab_bar.count() == 1
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Renaming tabs
# ---------------------------------------------------------------------------
def test_rename_updates_label_and_display_name(monkeypatch, qapp) -> None:
    window = MainWindow()
    try:
        monkeypatch.setattr(
            main_window_module.QInputDialog,
            "getText",
            staticmethod(lambda *a, **k: ("My Inverter", True)),
        )
        window._rename_document(0)
        assert window._documents[0].display_name == "My Inverter"
        assert window._tab_bar.tabText(0) == "• My Inverter"  # rename marks dirty
    finally:
        window.close()


def test_rename_cancelled_is_noop(monkeypatch, qapp) -> None:
    window = MainWindow()
    try:
        before = window._tab_bar.tabText(0)
        monkeypatch.setattr(
            main_window_module.QInputDialog,
            "getText",
            staticmethod(lambda *a, **k: ("ignored", False)),
        )
        window._rename_document(0)
        assert window._documents[0].display_name is None
        assert window._tab_bar.tabText(0) == before
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Opening files
# ---------------------------------------------------------------------------
def test_open_already_open_file_switches_instead_of_duplicating(
    monkeypatch, qapp, tmp_path
) -> None:
    saved = tmp_path / "circuit_a.pulsim"
    Project(name="A").save(saved)

    window = MainWindow()
    try:
        monkeypatch.setattr(window._settings, "add_recent_project", lambda _p: None)
        # Dirty the first tab so the open lands in a NEW tab (not a reuse).
        window._add_component_at(ComponentType.RESISTOR, 0.0, 0.0)

        window._open_project_file(str(saved))
        assert window._tab_bar.count() == 2
        opened_index = window._active_doc
        opened_project = window._project
        assert opened_project.path is not None

        # Opening the same file again must switch, not add a third tab.
        window._open_project_file(str(saved))
        assert window._tab_bar.count() == 2
        assert window._active_doc == opened_index
        assert window._project is opened_project
    finally:
        window.close()


def test_save_clears_display_name_override(monkeypatch, qapp, tmp_path) -> None:
    """After saving, the on-disk filename becomes the tab identity, so any
    earlier double-click rename override is dropped."""
    saved = tmp_path / "renamed_then_saved.pulsim"
    window = MainWindow()
    try:
        window._documents[0].display_name = "Scratch"
        monkeypatch.setattr(window._settings, "add_recent_project", lambda _p: None)
        monkeypatch.setattr(
            main_window_module.QFileDialog,
            "getSaveFileName",
            staticmethod(lambda *a, **k: (str(saved), "")),
        )
        window._on_save_as()
        assert window._documents[0].display_name is None
        assert window._tab_bar.tabText(0) == "renamed_then_saved"
    finally:
        window.close()


# ---------------------------------------------------------------------------
# Auto-save covers every open tab
# ---------------------------------------------------------------------------
def test_autosave_backs_up_all_dirty_tabs(qapp, tmp_path) -> None:
    """A timer auto-save writes a ``.bak`` for every dirty tab, not just
    the active one (background tabs must be recoverable too)."""
    a = tmp_path / "a.pulsim"
    b = tmp_path / "b.pulsim"
    Project(name="A").save(a)
    Project(name="B").save(b)

    window = MainWindow()
    try:
        window._replace_active_document(Project.load(a))
        window._add_document(Project.load(b))
        window._documents[0].project.mark_dirty()
        window._documents[1].project.mark_dirty()

        window._on_autosave()

        assert (tmp_path / "a.pulsim.bak").exists()
        assert (tmp_path / "b.pulsim.bak").exists()
    finally:
        window.close()
