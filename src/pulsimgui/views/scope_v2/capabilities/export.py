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
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPixmap
from PySide6.QtWidgets import QFileDialog, QMenu

if TYPE_CHECKING:
    from pulsimgui.views.scope_v2.shell import BaseScopeWindow


_LOG = logging.getLogger(__name__)


def _grab_plot_pixmap(plot_canvas) -> QPixmap | None:
    """Render the active plot canvas to a fresh :class:`QPixmap`.

    ``QWidget.grab()`` reads the on-screen framebuffer. When the
    underlying ``pg.GraphicsLayoutWidget`` runs in OpenGL mode (default
    on Qt 6 + macOS / Windows) the framebuffer is opaque to the Qt
    raster pipeline and ``grab()`` returns a blank white pixmap — the
    exact symptom users hit when "Copy plot to clipboard" produced an
    empty image. Render the graphics-view scene directly through a
    QPainter instead; this works regardless of the GL state.

    Returns ``None`` if the canvas isn't paintable (no scene, no
    visible area), so the caller can show a friendly status.
    """
    if plot_canvas is None:
        return None
    # Pick the currently visible page (time-domain vs. FFT view).
    active = getattr(plot_canvas, "_stack", None)
    target = active.currentWidget() if active is not None else None
    if target is None:
        target = plot_canvas
    scene = getattr(target, "scene", None)
    scene = scene() if callable(scene) else scene
    if scene is None:
        return None
    rect: QRectF = scene.sceneRect()
    if rect.isEmpty():
        rect = QRectF(target.rect())
    # Use the widget's device-pixel ratio so the export matches what
    # the user sees on hi-DPI displays.
    dpr = float(target.devicePixelRatioF() or 1.0)
    image = QImage(
        int(rect.width() * dpr),
        int(rect.height() * dpr),
        QImage.Format.Format_ARGB32_Premultiplied,
    )
    image.setDevicePixelRatio(dpr)
    # White-ish background matches the on-screen panel surface; the
    # scene paints opaque tiles on top so this only shows around the
    # rounded corners.
    image.fill(Qt.GlobalColor.white)
    painter = QPainter(image)
    try:
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        # pyqtgraph's GraphicsScene.render() doesn't accept the same
        # keyword args as QGraphicsScene — use positional form, which
        # both implementations support: (painter, target_rect, source_rect).
        scene.render(painter, QRectF(0, 0, image.width() / dpr, image.height() / dpr), rect)
    finally:
        painter.end()
    if image.isNull():
        return None
    return QPixmap.fromImage(image)


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
        pix = _grab_plot_pixmap(self._shell.plot_canvas)
        if pix is None:
            self._shell.drawer.summary.setText("PNG export failed: no plot to render.")
            return
        if pix.save(path, "PNG"):
            self._shell.drawer.summary.setText(f"Saved plot to {path}.")
        else:
            self._shell.drawer.summary.setText(f"PNG export failed: {path}")

    # ── Clipboard ───────────────────────────────────────────────────────

    def _copy_to_clipboard(self) -> None:
        if self._shell is None:
            return
        pix = _grab_plot_pixmap(self._shell.plot_canvas)
        if pix is None:
            self._shell.drawer.summary.setText("Copy failed: no plot to render.")
            return
        clip = QGuiApplication.clipboard()
        # Both forms — setPixmap is convenient on macOS / Linux; setImage
        # is the form some Windows clipboard targets prefer. Setting both
        # is harmless and improves paste compatibility.
        clip.setPixmap(pix)
        clip.setImage(pix.toImage())
        self._shell.drawer.summary.setText("Plot copied to clipboard.")


__all__ = ["ExportCapability"]
