"""Render a gallery of the design-system components to PNGs (light + dark).

A visual smoke test + a reference sheet. Run headless:

    QT_QPA_PLATFORM=offscreen python scripts/design_gallery.py

Writes design_gallery_light.png and design_gallery_dark.png to the repo root.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.theme_service import ThemeService
from pulsimgui.views.design import (
    Card,
    KpiTile,
    PageHeader,
    PrimaryButton,
    SecondaryButton,
    SectionHeader,
    SegmentedControl,
    Space,
    StatusBadge,
)

REPO = Path(__file__).resolve().parents[1]


def _build(theme_service: ThemeService) -> QWidget:
    root = QWidget()
    root.setObjectName("GalleryRoot")
    c = theme_service.current_theme.colors
    root.setStyleSheet(f"#GalleryRoot {{ background: {c.background_alt}; }}")
    page = QVBoxLayout(root)
    page.setContentsMargins(*Space.inset_page())
    page.setSpacing(Space.XL)

    page.addWidget(PageHeader(
        "Design System",
        "Reusable styled primitives driven by ThemeColors + structural tokens.",
        theme_service,
    ))

    # KPI grid
    kpis = Card(theme_service)
    kpis.body().addWidget(SectionHeader("KPI tiles", theme_service))
    grid = QGridLayout()
    grid.setSpacing(Space.MD)
    specs = [
        ("Bus Voltage", "398.2", "V", ""),
        ("Peak T_j", "118", "°C", "warning"),
        ("Total Loss", "42.7", "W", ""),
        ("Efficiency", "97.4", "%", "success"),
    ]
    for i, (lbl, val, unit, accent) in enumerate(specs):
        grid.addWidget(KpiTile(lbl, val, unit, theme_service, accent=accent), 0, i)
    kpis.body().addLayout(grid)
    page.addWidget(kpis)

    # Badges + buttons + segmented
    controls = Card(theme_service)
    controls.body().addWidget(SectionHeader("Badges, buttons & controls", theme_service))

    badges = QHBoxLayout()
    badges.setSpacing(Space.SM)
    for text, kind in [("CONVERGED", "success"), ("DERATING", "warning"),
                       ("RUNAWAY", "error"), ("STREAMING", "info"),
                       ("DRAFT", "neutral")]:
        badges.addWidget(StatusBadge(text, kind, theme_service))
    badges.addStretch(1)
    controls.body().addLayout(badges)

    buttons = QHBoxLayout()
    buttons.setSpacing(Space.SM)
    buttons.addWidget(PrimaryButton("Run Simulation", theme_service))
    buttons.addWidget(SecondaryButton("Cancel", theme_service))
    disabled = PrimaryButton("Disabled", theme_service)
    disabled.setEnabled(False)
    buttons.addWidget(disabled)
    buttons.addStretch(1)
    seg = SegmentedControl(
        [("pwl", "PWL"), ("dsed", "DSED"), ("auto", "Auto")], theme_service
    )
    buttons.addWidget(seg)
    controls.body().addLayout(buttons)
    page.addWidget(controls)

    # Nested / muted card
    nested = Card(theme_service)
    nested.body().addWidget(SectionHeader("Cards (default + muted)", theme_service))
    inner = Card(theme_service, muted=True)
    inner_lbl = QLabel("A muted (recessed) card nested inside a default card.")
    inner_lbl.setStyleSheet(f"color: {c.foreground_muted};")
    inner.body().addWidget(inner_lbl)
    nested.body().addWidget(inner)
    page.addWidget(nested)

    page.addStretch(1)
    root.resize(720, 760)
    return root


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    svc = ThemeService()
    for theme_name, out in [("light", "design_gallery_light.png"),
                            ("dark", "design_gallery_dark.png")]:
        svc.set_theme(theme_name)
        w = _build(svc)
        w.show()
        app.processEvents()
        pm = QPixmap(w.size())
        w.render(pm)
        path = REPO / out
        pm.save(str(path))
        print(f"wrote {path.relative_to(REPO)}  ({theme_name})")
        w.deleteLater()


if __name__ == "__main__":
    main()
