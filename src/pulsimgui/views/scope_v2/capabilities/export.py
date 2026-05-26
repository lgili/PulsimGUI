"""``ExportCapability`` — save the current canvas as CSV / PNG / clipboard.

Clicking the toolbar's download icon opens a small menu with three
choices:

  * **CSV** — one column per signal, plus a leading time column.
  * **PNG** — grabs the plot canvas as an image (whatever's on screen,
    including cursors).
  * **Copy as image** — same PNG but routed to the system clipboard for
    quick pasting into a slide / Slack / lab notebook.

Reuses the curve data the canvas already caches via ``_SignalState``
so no extra streaming infrastructure is required.
"""

from __future__ import annotations

import csv
import logging
from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QFileDialog, QMenu

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


class ExportCapability:
    """Toolbar ↓ button → CSV / PNG / clipboard menu."""

    def __init__(self) -> None:
        self._shell: BaseScopeWindow | None = None

    def attach(self, shell: BaseScopeWindow) -> None:
        self._shell = shell
        shell.toolbar.btn_export.clicked.connect(self._open_menu)

    def _open_menu(self) -> None:
        if self._shell is None:
            return
        menu = QMenu(self._shell)
        act_csv = menu.addAction("Export waveforms as CSV…")
        act_png = menu.addAction("Save plot as PNG…")
        act_clipboard = menu.addAction("Copy plot to clipboard")
        chosen = menu.exec(self._shell.toolbar.btn_export.mapToGlobal(
            self._shell.toolbar.btn_export.rect().bottomLeft()
        ))
        if chosen is act_csv:
            self._export_csv()
        elif chosen is act_png:
            self._export_png()
        elif chosen is act_clipboard:
            self._copy_to_clipboard()

    # ── CSV ──────────────────────────────────────────────────────────────

    def _export_csv(self) -> None:
        if self._shell is None:
            return
        canvas = self._shell.plot_canvas
        signals = list(canvas.signals())
        if not signals:
            self._shell.drawer.summary.setText("Export: nothing to save — run the simulation first.")
            return

        # Find the longest time vector — used as the master grid; other
        # signals are interpolated onto it so the CSV stays rectangular.
        master_t: np.ndarray | None = None
        per_signal: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for name in signals:
            state = canvas._signals[name]  # noqa: SLF001
            t, y = state.merged()
            if t.size == 0:
                continue
            per_signal[name] = (t, y)
            if master_t is None or t.size > master_t.size:
                master_t = t
        if master_t is None:
            self._shell.drawer.summary.setText("Export: no samples captured.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self._shell, "Export waveforms as CSV", "waveforms.csv", "CSV files (*.csv)"
        )
        if not path:
            return

        # Build the rows on the master grid.
        try:
            with open(path, "w", newline="") as fh:
                writer = csv.writer(fh)
                header = ["time_s"] + signals
                writer.writerow(header)
                interpolated: dict[str, np.ndarray] = {}
                for name in signals:
                    if name not in per_signal:
                        interpolated[name] = np.full(master_t.size, np.nan)
                        continue
                    t, y = per_signal[name]
                    interpolated[name] = np.interp(master_t, t, y, left=np.nan, right=np.nan)
                for i, t_val in enumerate(master_t):
                    row = [float(t_val)] + [float(interpolated[name][i]) for name in signals]
                    writer.writerow(row)
        except OSError as exc:
            self._shell.drawer.summary.setText(f"CSV export failed: {exc}")
            return
        self._shell.drawer.summary.setText(
            f"Exported {len(signals)} signals × {master_t.size} samples to {path}."
        )

    # ── PNG ──────────────────────────────────────────────────────────────

    def _export_png(self) -> None:
        if self._shell is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self._shell, "Save plot as PNG", "scope.png", "PNG files (*.png)"
        )
        if not path:
            return
        pix = self._shell.plot_canvas.grab()
        if pix.save(path, "PNG"):
            self._shell.drawer.summary.setText(f"Saved plot to {path}.")
        else:
            self._shell.drawer.summary.setText(f"PNG export failed: {path}")

    # ── Clipboard ───────────────────────────────────────────────────────

    def _copy_to_clipboard(self) -> None:
        if self._shell is None:
            return
        pix = self._shell.plot_canvas.grab()
        clip = QGuiApplication.clipboard()
        clip.setPixmap(pix)
        self._shell.drawer.summary.setText("Plot copied to clipboard.")


__all__ = ["ExportCapability"]
