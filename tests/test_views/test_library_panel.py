"""Tests for component library panel density and layout behavior."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel

from pulsimgui.models.component import ComponentType
from pulsimgui.views.library.library_panel import CategorySection, ComponentCard, LibraryPanel


def test_library_panel_uses_compact_search_bar_without_duplicate_title(qapp) -> None:
    """The dock title should remain the single library title; the panel stays compact."""

    panel = LibraryPanel()
    try:
        assert panel.findChildren(QLabel, "LibraryPanelTitle") == []
        assert panel._search_edit.placeholderText() == "Search components..."
        assert panel._summary_label.text().endswith("components")
    finally:
        panel.close()


def test_category_section_reflows_cards_when_width_changes(qapp) -> None:
    """Component cards should adapt column count to the available dock width."""

    section = CategorySection("Circuit", "#0f766e")
    try:
        for comp_type, name, shortcut in (
            (ComponentType.RESISTOR, "Resistor", "R"),
            (ComponentType.CAPACITOR, "Capacitor", "C"),
            (ComponentType.INDUCTOR, "Inductor", "L"),
            (ComponentType.DIODE, "Diode", "D"),
        ):
            section.add_component(comp_type, name, shortcut)

        section.resize(380, 320)
        section.show()
        qapp.processEvents()
        section._grid_container.resize(380, section._grid_container.height() or 200)
        section._rebuild_grid()
        wide_columns = section._column_count
        assert section._grid_layout.count() == len(section._cards)

        section.resize(210, 320)
        section._grid_container.resize(210, section._grid_container.height() or 200)
        section._rebuild_grid()
        qapp.processEvents()
        narrow_columns = section._column_count

        assert wide_columns >= 3
        assert narrow_columns < wide_columns
        assert narrow_columns >= 1
    finally:
        section.close()


def test_component_card_centers_icon_and_name_on_same_axis(qapp) -> None:
    """Icon and label should share the same visual center inside the card."""

    card = ComponentCard(ComponentType.RESISTOR, "Resistor", "R")
    try:
        card.show()
        qapp.processEvents()

        icon_rect = card._icon_label.geometry()
        name_rect = card._name_label.geometry()
        icon_center = icon_rect.x() + (icon_rect.width() / 2)
        name_center = name_rect.x() + (name_rect.width() / 2)

        assert abs(icon_center - name_center) <= 1.0
    finally:
        card.close()
