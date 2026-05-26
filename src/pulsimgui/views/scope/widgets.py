"""Custom scope widgets: ``TimeRangeSlider``, ``BottomDrawerResizeHandle``,
``ScopeWorkspaceDropArea``.

Split out of ``scope_window.py`` so the (large) scope-window module no
longer ships custom QWidget primitives inline. Each class here is
self-contained and intended for reuse inside the scope shell.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from pulsimgui.services.theme_service import LIGHT_THEME
from pulsimgui.views.waveform.waveform_viewer import SignalListPanel


class TimeRangeSlider(QWidget):
    """Two-handle range slider used for the scope's timeline scrubber."""

    rangeChanged = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scopeTimelineSlider")
        self.setMinimumHeight(28)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._minimum = 0
        self._maximum = 1000
        self._low = 0
        self._high = 1000
        self._drag_target: str | None = None
        self._handle_radius = 6
        self._track_height = 4

        self._track_bg = QColor(LIGHT_THEME.colors.divider)
        self._track_border = QColor(LIGHT_THEME.colors.border)
        self._selected_fill = QColor(LIGHT_THEME.colors.primary)
        self._handle_fill = QColor(LIGHT_THEME.colors.input_background)
        self._handle_border = QColor(LIGHT_THEME.colors.input_focus_border)

    def set_theme_colors(
        self,
        *,
        track_bg: QColor,
        track_border: QColor,
        selected_fill: QColor,
        handle_fill: QColor,
        handle_border: QColor,
    ) -> None:
        """Update theme_colors for this widget."""
        self._track_bg = track_bg
        self._track_border = track_border
        self._selected_fill = selected_fill
        self._handle_fill = handle_fill
        self._handle_border = handle_border
        self.update()

    def setRange(self, minimum: int, maximum: int) -> None:
        """Update the slider numeric range."""
        self._minimum = int(minimum)
        self._maximum = max(int(maximum), self._minimum + 1)
        self.setValues(self._low, self._high)

    def setValues(self, low: int, high: int) -> None:
        """Update the low/high slider values."""
        low_clamped = max(self._minimum, min(int(low), self._maximum - 1))
        high_clamped = max(low_clamped + 1, min(int(high), self._maximum))
        changed = (low_clamped != self._low) or (high_clamped != self._high)
        self._low = low_clamped
        self._high = high_clamped
        if changed:
            self.rangeChanged.emit(self._low, self._high)
        self.update()

    def lowValue(self) -> int:
        """Return the current low value value."""
        return self._low

    def highValue(self) -> int:
        """Return the current high value value."""
        return self._high

    def minimum(self) -> int:
        """Return the current minimum value."""
        return self._minimum

    def maximum(self) -> int:
        """Return the current maximum value."""
        return self._maximum

    def _track_geometry(self) -> tuple[int, int, int, int]:
        left = self._handle_radius + 4
        right = max(left + 20, self.width() - self._handle_radius - 4)
        y = (self.height() - self._track_height) // 2
        return left, right, y, self._track_height

    def _value_to_x(self, value: int) -> int:
        left, right, _, _ = self._track_geometry()
        span = max(1, self._maximum - self._minimum)
        ratio = (value - self._minimum) / span
        return int(round(left + ratio * (right - left)))

    def _x_to_value(self, x: int) -> int:
        left, right, _, _ = self._track_geometry()
        clamped_x = min(max(x, left), right)
        span_px = max(1, right - left)
        ratio = (clamped_x - left) / span_px
        value = self._minimum + ratio * (self._maximum - self._minimum)
        return int(round(value))

    def paintEvent(self, _event) -> None:
        """Render the widget contents for the current frame."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        left, right, y, h = self._track_geometry()
        low_x = self._value_to_x(self._low)
        high_x = self._value_to_x(self._high)

        painter.setPen(QPen(self._track_border, 1))
        painter.setBrush(QBrush(self._track_bg))
        painter.drawRoundedRect(left, y, max(1, right - left), h, 3, 3)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._selected_fill))
        painter.drawRoundedRect(low_x, y, max(1, high_x - low_x), h, 3, 3)

        for x in (low_x, high_x):
            painter.setPen(QPen(self._handle_border, 1.2))
            painter.setBrush(QBrush(self._handle_fill))
            painter.drawEllipse(
                x - self._handle_radius,
                (self.height() // 2) - self._handle_radius,
                self._handle_radius * 2,
                self._handle_radius * 2,
            )

        if self.hasFocus():
            focus_pen = QPen(self._handle_border, 1.4)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle the Qt mousePressEvent callback."""
        if not self.isEnabled() or event.button() != Qt.MouseButton.LeftButton:
            return
        low_x = self._value_to_x(self._low)
        high_x = self._value_to_x(self._high)
        click_x = int(event.position().x())

        if abs(click_x - low_x) <= abs(click_x - high_x):
            self._drag_target = "low"
        else:
            self._drag_target = "high"
        self._update_from_mouse(click_x)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle the Qt mouseMoveEvent callback."""
        if not self.isEnabled() or self._drag_target is None:
            return
        self._update_from_mouse(int(event.position().x()))

    def mouseReleaseEvent(self, _event: QMouseEvent) -> None:
        """Handle the Qt mouseReleaseEvent callback."""
        self._drag_target = None

    def keyPressEvent(self, event) -> None:
        """Pan the active timeline window using keyboard arrows."""
        key = event.key()
        if key not in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            super().keyPressEvent(event)
            return
        delta = -10 if key == Qt.Key.Key_Left else 10
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta = int(delta / 2)
            if delta == 0:
                delta = -1 if key == Qt.Key.Key_Left else 1
        low = self._low + delta
        high = self._high + delta
        width = self._high - self._low
        if low < self._minimum:
            low = self._minimum
            high = min(self._maximum, low + width)
        if high > self._maximum:
            high = self._maximum
            low = max(self._minimum, high - width)
        self.setValues(low, high)
        event.accept()

    def _update_from_mouse(self, x: int) -> None:
        value = self._x_to_value(x)
        if self._drag_target == "low":
            self.setValues(value, self._high)
        elif self._drag_target == "high":
            self.setValues(self._low, value)


class BottomDrawerResizeHandle(QWidget):
    """Thin drag handle used to resize the analysis drawer body."""

    resize_delta_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("scopeBottomDrawerResizeHandle")
        self.setFixedHeight(6)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self._last_global_y: int | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._last_global_y = int(event.globalPosition().y())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._last_global_y is None:
            super().mouseMoveEvent(event)
            return
        current_y = int(event.globalPosition().y())
        delta = self._last_global_y - current_y
        if delta != 0:
            self.resize_delta_requested.emit(delta)
            self._last_global_y = current_y
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._last_global_y = None
        super().mouseReleaseEvent(event)


class ScopeWorkspaceDropArea(QWidget):
    """Central workspace drop area for assigning a signal to a dedicated pane."""

    def __init__(
        self,
        *,
        drop_handler: Callable[[str, str | None], bool] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
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
            if self._drop_handler(signal_name, None):
                event.acceptProposedAction()
                return
        super().dropEvent(event)


__all__ = [
    "TimeRangeSlider",
    "BottomDrawerResizeHandle",
    "ScopeWorkspaceDropArea",
]
