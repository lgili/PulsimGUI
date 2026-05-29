"""Diagnose scope theme issues — dump exactly what styles + palette
are applied to every combo / spin / popup in the scope window.

Usage::

    PYTHONPATH=src python3 scripts/diag_scope_theme.py

Prints the palette colours, the stylesheets sitting on each form
widget AND its popup view + container, and the effective bg/text
colour Qt thinks should render. Run this when the scope visually
shows "white dropdowns" or "dark unreadable text" — the output
will pinpoint which layer is overriding the dark theme.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtGui import QPalette  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox  # noqa: E402

# Mirror __main__.py — Fusion at the app level.
app = QApplication.instance() or QApplication(sys.argv)
app.setStyle("Fusion")

from pulsimgui.services.settings_service import SettingsService  # noqa: E402
from pulsimgui.services.simulation_service import SimulationService  # noqa: E402
from pulsimgui.models.project import Project  # noqa: E402
from pulsimgui.views.scope_v2 import (  # noqa: E402
    BaseScopeWindow,
    CursorsCapability,
    FFTCapability,
    LiveStreamCapability,
    PostSimCapability,
    SMPSMacrosCapability,
    TriggerCapability,
)
from pulsimgui.views.scope_v2.resolver import resolve_scope_signal_specs  # noqa: E402
from pulsimgui.views.scope_v2.variants import ElectricalScopeVariant  # noqa: E402


def main() -> int:
    proj = Project.load(
        Path("examples/09_buck_closed_loop_loss_thermal_validation.pulsim"),
    )
    circuit = proj.get_active_circuit()
    settings = SettingsService()
    sim = SimulationService(settings_service=settings)
    scope = next(
        (c for c in circuit.components.values() if c.type.name == "ELECTRICAL_SCOPE"),
        None,
    )
    if scope is None:
        print("No scope component in project.")
        return 1
    live_specs, post_specs = resolve_scope_signal_specs(scope, circuit, sim, proj)

    sim.apply_project_simulation_settings(proj)
    sim.run_transient_project(proj)
    loop = QEventLoop()
    sim.simulation_finished.connect(loop.quit)
    sim.error.connect(loop.quit)
    loop.exec()

    w = BaseScopeWindow(
        variant=ElectricalScopeVariant(name=f"Scope: {scope.name}"),
        capabilities=[
            LiveStreamCapability(sim, live_specs),
            PostSimCapability(sim, post_specs, result_getter=lambda: sim.last_result),
            CursorsCapability(),
            TriggerCapability(),
            SMPSMacrosCapability(),
            FFTCapability(),
        ],
        version="0.12.0a9",
    )
    w.resize(1600, 900)
    w.show()
    for _ in range(20):
        app.processEvents()
        time.sleep(0.05)

    print("=" * 70)
    print("APP STYLESHEET (first 600 chars):")
    print("=" * 70)
    app_qss = app.styleSheet()
    print(f"  total: {len(app_qss)} chars")
    print(app_qss[:600] if app_qss else "(empty)")

    print()
    print("=" * 70)
    print("BASESCOPEWINDOW PALETTE:")
    print("=" * 70)
    pal = w.palette()
    for role in (
        QPalette.ColorRole.Window,
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.Button,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.Highlight,
        QPalette.ColorRole.HighlightedText,
    ):
        print(f"  {role.name:20s} {pal.color(role).name()}")

    print()
    print("=" * 70)
    print("PER-COMBO DIAGNOSTIC:")
    print("=" * 70)
    for i, combo in enumerate(w.findChildren(QComboBox)):
        view = combo.view()
        container = view.parent() if view is not None else None
        print(f"\ncombo[{i}] objectName={combo.objectName()!r}")
        print(f"  combo.styleSheet len: {len(combo.styleSheet())}")
        print(f"  combo.style: {type(combo.style()).__name__}")
        print(f"  combo palette Base: {combo.palette().color(QPalette.ColorRole.Base).name()}")
        print(f"  combo palette Text: {combo.palette().color(QPalette.ColorRole.Text).name()}")
        if view is not None:
            print(f"  view type: {type(view).__name__}")
            print(f"  view.styleSheet len: {len(view.styleSheet())}")
            print(f"  view palette Base: {view.palette().color(QPalette.ColorRole.Base).name()}")
            print(f"  view palette Text: {view.palette().color(QPalette.ColorRole.Text).name()}")
        if container is not None:
            print(f"  container type: {type(container).__name__}")
            print(f"  container.styleSheet len: {len(container.styleSheet())}")
            print(
                f"  container palette Base: "
                f"{container.palette().color(QPalette.ColorRole.Base).name()}"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
