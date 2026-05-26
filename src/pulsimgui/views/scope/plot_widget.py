"""Plot widgets used by the scope: ``ScopePlotViewBox`` + ``ScopePlotWidget``.

Split out of ``scope_window.py`` so the (large) scope-window module no
longer owns pyqtgraph subclasses inline. Together these add scope-
oriented mouse handling (wheel-zoom, selection, context menu) and drag-
and-drop signal-name routing on top of pyqtgraph's ``ViewBox`` /
``PlotWidget``.
"""

from __future__ import annotations

from collections.abc import Callable

import pyqtgraph as pg
from PySide6.QtCore import Qt

from pulsimgui.views.waveform.waveform_viewer import SignalListPanel


class ScopePlotViewBox(pg.ViewBox):
    """Custom ViewBox to handle scope-oriented wheel zoom and plot selection."""

    def __init__(
        self,
        *,
        group_leader: str,
        wheel_handler: Callable[[pg.ViewBox, object, str], bool] | None = None,
        select_handler: Callable[[str], None] | None = None,
        context_handler: Callable[[str, object], None] | None = None,
    ) -> None:
        super().__init__(enableMenu=False)
        self._group_leader = group_leader
        self._wheel_handler = wheel_handler
        self._select_handler = select_handler
        self._context_handler = context_handler

    def wheelEvent(self, ev, axis=None):
        if self._wheel_handler is not None and self._wheel_handler(self, ev, self._group_leader):
            return
        super().wheelEvent(ev, axis=axis)

    def mouseClickEvent(self, ev) -> None:
        if (
            self._select_handler is not None
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            self._select_handler(self._group_leader)
        elif (
            self._context_handler is not None
            and ev.button() == Qt.MouseButton.RightButton
        ):
            self._context_handler(self._group_leader, ev.screenPos())
        super().mouseClickEvent(ev)


class ScopePlotWidget(pg.PlotWidget):
    """Plot widget that accepts signal drops onto a specific plot group."""

    def __init__(
        self,
        *,
        group_leader: str,
        drop_handler: Callable[[str, str | None], bool] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._group_leader = group_leader
        self._drop_handler = drop_handler
        self.setAcceptDrops(True)

    def _dragged_signal_name(self, event) -> str | None:
        return SignalListPanel.signal_name_from_mime(event.mimeData())

    def dragEnterEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._dragged_signal_name(event):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        signal_name = self._dragged_signal_name(event)
        if signal_name and self._drop_handler is not None:
            if self._drop_handler(signal_name, self._group_leader):
                event.acceptProposedAction()
                return
        super().dropEvent(event)


__all__ = ["ScopePlotViewBox", "ScopePlotWidget"]
