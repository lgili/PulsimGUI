"""Loading indicator widgets for showing progress during long operations."""

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QWidget,
    QDialog,
    QVBoxLayout,
    QLabel,
    QPushButton,
    QApplication,
)


class SpinnerWidget(QWidget):
    """A spinning circle loading indicator."""

    def __init__(self, parent=None, size: int = 32, color: QColor | None = None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self._size = size
        self._color = color or QColor(70, 130, 180)  # Steel blue
        self._line_count = 12
        self._line_width = 3

        self.setFixedSize(size, size)

    def _get_angle(self) -> int:
        return self._angle

    def _set_angle(self, angle: int) -> None:
        self._angle = angle
        self.update()

    angle = Property(int, _get_angle, _set_angle)

    def start(self) -> None:
        """Start the spinner animation."""
        self._timer.start(80)  # ~12 fps

    def stop(self) -> None:
        """Stop the spinner animation."""
        self._timer.stop()

    def _rotate(self) -> None:
        """Rotate the spinner."""
        self._angle = (self._angle + 30) % 360
        self.update()

    def set_color(self, color: QColor) -> None:
        """Set the spinner color."""
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the spinner."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Center the drawing
        painter.translate(self._size / 2, self._size / 2)
        painter.rotate(self._angle)

        # Draw lines
        for i in range(self._line_count):
            # Calculate opacity (fade out as we go around)
            opacity = 1.0 - (i / self._line_count) * 0.7

            color = QColor(self._color)
            color.setAlphaF(opacity)

            pen = QPen(color, self._line_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)

            # Draw line from inner to outer radius
            inner_radius = self._size * 0.25
            outer_radius = self._size * 0.45
            painter.drawLine(int(inner_radius), 0, int(outer_radius), 0)

            # Rotate for next line
            painter.rotate(360 / self._line_count)


class LoadingOverlay(QWidget):
    """A semi-transparent overlay with a loading spinner."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._message = ""

        # Make widget transparent
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        # Layout
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Spinner
        self._spinner = SpinnerWidget(self, size=48)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)

        # Message label
        self._label = QLabel()
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet(
            """
            QLabel {
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                background-color: rgba(0, 0, 0, 150);
                border-radius: 5px;
            }
            """
        )
        layout.addWidget(self._label, 0, Qt.AlignmentFlag.AlignCenter)

        self.hide()

    def show_loading(self, message: str = "Loading...") -> None:
        """Show the loading overlay with a message."""
        self._message = message
        self._label.setText(message)
        self._spinner.start()

        # Resize to cover parent
        if self.parent():
            self.resize(self.parent().size())

        self.show()
        self.raise_()

    def hide_loading(self) -> None:
        """Hide the loading overlay."""
        self._spinner.stop()
        self.hide()

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self._message = message
        self._label.setText(message)

    def paintEvent(self, event) -> None:
        """Paint the semi-transparent background."""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

    def resizeEvent(self, event) -> None:
        """Handle resize to stay centered."""
        super().resizeEvent(event)


class LoadingDialog(QDialog):
    """A modal dialog with a loading spinner."""

    def __init__(self, parent=None, title: str = "Please Wait", cancellable: bool = True):
        super().__init__(parent)
        self._cancelled = False

        self.setWindowTitle(title)
        self.setModal(True)
        self.setFixedSize(300, 150)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(15)

        # Spinner
        self._spinner = SpinnerWidget(self, size=40)
        layout.addWidget(self._spinner, 0, Qt.AlignmentFlag.AlignCenter)

        # Message label
        self._label = QLabel("Loading...")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)

        # Cancel button
        if cancellable:
            self._cancel_btn = QPushButton("Cancel")
            self._cancel_btn.clicked.connect(self._on_cancel)
            layout.addWidget(self._cancel_btn, 0, Qt.AlignmentFlag.AlignCenter)

    def show_loading(self, message: str = "Loading...") -> None:
        """Show the dialog with a message."""
        self._cancelled = False
        self._label.setText(message)
        self._spinner.start()
        self.show()
        QApplication.processEvents()  # Ensure UI updates

    def hide_loading(self) -> None:
        """Hide the dialog."""
        self._spinner.stop()
        self.accept()

    def update_message(self, message: str) -> None:
        """Update the loading message."""
        self._label.setText(message)
        QApplication.processEvents()

    def _on_cancel(self) -> None:
        """Handle cancel button click."""
        self._cancelled = True
        self._spinner.stop()
        self.reject()

    @property
    def was_cancelled(self) -> bool:
        """Check if the operation was cancelled."""
        return self._cancelled


class BusyCursor:
    """Context manager for showing a busy cursor during operations."""

    def __enter__(self):
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        QApplication.restoreOverrideCursor()
        return False


def with_busy_cursor(func):
    """Decorator to show busy cursor during a function call."""

    def wrapper(*args, **kwargs):
        with BusyCursor():
            return func(*args, **kwargs)

    return wrapper
