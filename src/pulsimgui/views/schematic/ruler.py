"""Ruler widgets for schematic view measurement."""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import QWidget


class RulerWidget(QWidget):
    """Base class for ruler widgets that display measurement ticks along edges."""

    # Appearance settings
    BACKGROUND_COLOR = QColor(245, 245, 250)
    BACKGROUND_COLOR_DARK = QColor(40, 44, 52)
    TICK_COLOR = QColor(120, 120, 130)
    TICK_COLOR_DARK = QColor(150, 150, 160)
    TEXT_COLOR = QColor(80, 80, 90)
    TEXT_COLOR_DARK = QColor(180, 180, 190)
    BORDER_COLOR = QColor(200, 200, 210)
    BORDER_COLOR_DARK = QColor(60, 64, 72)

    # Tick settings
    MAJOR_TICK_LENGTH = 12
    MINOR_TICK_LENGTH = 6
    TINY_TICK_LENGTH = 3
    MAJOR_INTERVAL = 100  # pixels between major ticks at 100% zoom
    MINOR_DIVISIONS = 5   # minor ticks between major ticks

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark_mode = False
        self._scroll_offset = 0.0
        self._zoom_level = 1.0
        self._origin_offset = 0.0  # scene origin position

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode appearance."""
        self._dark_mode = dark
        self.update()

    def set_scroll_offset(self, offset: float) -> None:
        """Set the scroll offset in scene coordinates."""
        self._scroll_offset = offset
        self.update()

    def set_zoom_level(self, zoom: float) -> None:
        """Set the zoom level (1.0 = 100%)."""
        self._zoom_level = zoom
        self.update()

    def set_origin_offset(self, offset: float) -> None:
        """Set the origin offset (scene coordinate of ruler start)."""
        self._origin_offset = offset
        self.update()

    def _get_colors(self) -> tuple[QColor, QColor, QColor, QColor]:
        """Get colors based on current mode."""
        if self._dark_mode:
            return (
                self.BACKGROUND_COLOR_DARK,
                self.TICK_COLOR_DARK,
                self.TEXT_COLOR_DARK,
                self.BORDER_COLOR_DARK,
            )
        return (
            self.BACKGROUND_COLOR,
            self.TICK_COLOR,
            self.TEXT_COLOR,
            self.BORDER_COLOR,
        )

    def _calculate_tick_interval(self) -> tuple[float, int]:
        """Calculate appropriate tick interval based on zoom level.

        Returns:
            Tuple of (major_interval_pixels, minor_divisions)
        """
        # Base interval at 100% zoom
        base_interval = self.MAJOR_INTERVAL

        # Adjust for zoom - we want labels to be readable
        scaled_interval = base_interval * self._zoom_level

        # Find a nice interval that keeps labels from overlapping
        nice_intervals = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]

        for interval in nice_intervals:
            pixel_spacing = interval * self._zoom_level
            if pixel_spacing >= 50:  # Minimum spacing for readability
                return interval, self.MINOR_DIVISIONS

        return nice_intervals[-1], self.MINOR_DIVISIONS


class HorizontalRuler(RulerWidget):
    """Horizontal ruler displayed along the top of the schematic view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setMinimumWidth(100)

    def paintEvent(self, event):
        """Paint the horizontal ruler."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color, tick_color, text_color, border_color = self._get_colors()

        # Background
        painter.fillRect(self.rect(), bg_color)

        # Bottom border
        painter.setPen(QPen(border_color, 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        # Calculate tick interval
        major_interval, minor_divs = self._calculate_tick_interval()
        minor_interval = major_interval / minor_divs

        # Calculate visible range in scene coordinates
        start_scene = self._scroll_offset - self._origin_offset
        end_scene = start_scene + self.width() / self._zoom_level

        # Find first major tick
        first_major = int(start_scene / major_interval) * major_interval
        if first_major < start_scene:
            first_major += major_interval

        # Draw ticks and labels
        painter.setPen(QPen(tick_color, 1))
        font = QFont()
        font.setPointSize(8)
        painter.setFont(font)

        # Draw minor ticks first
        first_minor = int(start_scene / minor_interval) * minor_interval
        scene_pos = first_minor
        while scene_pos <= end_scene:
            screen_x = (scene_pos - start_scene) * self._zoom_level

            # Check if this is a major tick
            is_major = abs(scene_pos % major_interval) < 0.1

            if is_major:
                # Major tick
                painter.drawLine(
                    int(screen_x), self.height() - self.MAJOR_TICK_LENGTH,
                    int(screen_x), self.height() - 1
                )
                # Label
                label = str(int(scene_pos))
                painter.setPen(text_color)
                text_rect = QRectF(screen_x - 30, 2, 60, 12)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
                painter.setPen(QPen(tick_color, 1))
            else:
                # Minor tick
                tick_len = self.MINOR_TICK_LENGTH
                painter.drawLine(
                    int(screen_x), self.height() - tick_len,
                    int(screen_x), self.height() - 1
                )

            scene_pos += minor_interval


class VerticalRuler(RulerWidget):
    """Vertical ruler displayed along the left of the schematic view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(25)
        self.setMinimumHeight(100)

    def paintEvent(self, event):
        """Paint the vertical ruler."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        bg_color, tick_color, text_color, border_color = self._get_colors()

        # Background
        painter.fillRect(self.rect(), bg_color)

        # Right border
        painter.setPen(QPen(border_color, 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())

        # Calculate tick interval
        major_interval, minor_divs = self._calculate_tick_interval()
        minor_interval = major_interval / minor_divs

        # Calculate visible range in scene coordinates
        start_scene = self._scroll_offset - self._origin_offset
        end_scene = start_scene + self.height() / self._zoom_level

        # Draw ticks and labels
        painter.setPen(QPen(tick_color, 1))
        font = QFont()
        font.setPointSize(7)
        painter.setFont(font)

        # Draw minor ticks first
        first_minor = int(start_scene / minor_interval) * minor_interval
        scene_pos = first_minor
        while scene_pos <= end_scene:
            screen_y = (scene_pos - start_scene) * self._zoom_level

            # Check if this is a major tick
            is_major = abs(scene_pos % major_interval) < 0.1

            if is_major:
                # Major tick
                painter.drawLine(
                    self.width() - self.MAJOR_TICK_LENGTH, int(screen_y),
                    self.width() - 1, int(screen_y)
                )
                # Label (rotated or short)
                label = str(int(scene_pos))
                painter.setPen(text_color)

                # Draw text vertically centered on tick
                painter.save()
                painter.translate(2, screen_y)
                painter.rotate(-90)
                text_rect = QRectF(-20, 0, 40, 20)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
                painter.restore()

                painter.setPen(QPen(tick_color, 1))
            else:
                # Minor tick
                tick_len = self.MINOR_TICK_LENGTH
                painter.drawLine(
                    self.width() - tick_len, int(screen_y),
                    self.width() - 1, int(screen_y)
                )

            scene_pos += minor_interval


class RulerCorner(QWidget):
    """Corner widget where horizontal and vertical rulers meet."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(25, 20)
        self._dark_mode = False

    def set_dark_mode(self, dark: bool) -> None:
        """Set dark mode appearance."""
        self._dark_mode = dark
        self.update()

    def paintEvent(self, event):
        """Paint the corner."""
        painter = QPainter(self)

        if self._dark_mode:
            bg_color = RulerWidget.BACKGROUND_COLOR_DARK
            border_color = RulerWidget.BORDER_COLOR_DARK
        else:
            bg_color = RulerWidget.BACKGROUND_COLOR
            border_color = RulerWidget.BORDER_COLOR

        painter.fillRect(self.rect(), bg_color)

        # Draw borders
        painter.setPen(QPen(border_color, 1))
        painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
