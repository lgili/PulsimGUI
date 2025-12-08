"""Status bar widgets with icons and visual feedback."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel

from pulsimgui.resources.icons import IconService


class IconLabel(QWidget):
    """A label with an icon prefix."""

    def __init__(
        self,
        icon_name: str,
        text: str = "",
        icon_color: str = "#666666",
        parent=None,
    ):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_color = icon_color
        self._dark_mode = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Icon label
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(14, 14)
        self._update_icon()
        layout.addWidget(self._icon_label)

        # Text label
        self._text_label = QLabel(text)
        layout.addWidget(self._text_label)

    def _update_icon(self) -> None:
        """Update the icon with current color."""
        color = "#d1d5db" if self._dark_mode else self._icon_color
        icon = IconService.get_icon(self._icon_name, color)
        if not icon.isNull():
            pixmap = icon.pixmap(14, 14)
            self._icon_label.setPixmap(pixmap)

    def setText(self, text: str) -> None:
        """Set the text."""
        self._text_label.setText(text)

    def text(self) -> str:
        """Get the text."""
        return self._text_label.text()

    def setIconColor(self, color: str) -> None:
        """Set icon color."""
        self._icon_color = color
        self._update_icon()

    def setIcon(self, icon_name: str) -> None:
        """Change the icon."""
        self._icon_name = icon_name
        self._update_icon()

    def setDarkMode(self, dark: bool) -> None:
        """Set dark mode."""
        self._dark_mode = dark
        self._update_icon()

    def setMinimumWidth(self, width: int) -> None:
        """Set minimum width for text label."""
        self._text_label.setMinimumWidth(width - 22)  # Account for icon and spacing


class CoordinateWidget(QWidget):
    """Widget showing current cursor coordinates with click-to-edit."""

    coordinate_entered = Signal(float, float)  # Emitted when user enters coordinates

    def __init__(self, parent=None):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._editing = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        from PySide6.QtWidgets import QLineEdit, QStackedWidget

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(14, 14)
        icon = IconService.get_icon("crosshairs", "#0078D4")
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(14, 14))
        layout.addWidget(self._icon_label)

        # Stacked widget for display/edit modes
        self._stack = QStackedWidget()

        # Display label (clickable)
        self._display_label = QLabel("X: 0, Y: 0")
        self._display_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._display_label.setToolTip("Click to enter coordinates")
        self._display_label.mousePressEvent = self._start_editing
        self._stack.addWidget(self._display_label)

        # Edit widget
        edit_widget = QWidget()
        edit_layout = QHBoxLayout(edit_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(2)

        self._x_edit = QLineEdit()
        self._x_edit.setFixedWidth(50)
        self._x_edit.setPlaceholderText("X")
        edit_layout.addWidget(self._x_edit)

        edit_layout.addWidget(QLabel(","))

        self._y_edit = QLineEdit()
        self._y_edit.setFixedWidth(50)
        self._y_edit.setPlaceholderText("Y")
        self._y_edit.returnPressed.connect(self._finish_editing)
        edit_layout.addWidget(self._y_edit)

        self._stack.addWidget(edit_widget)

        layout.addWidget(self._stack)

        # Apply styling
        self.setStyleSheet("""
            QLineEdit {
                border: 1px solid #93c5fd;
                border-radius: 3px;
                padding: 1px 4px;
                font-size: 11px;
            }
        """)

    def _start_editing(self, event) -> None:
        """Enter edit mode."""
        self._x_edit.setText(f"{self._x:.0f}")
        self._y_edit.setText(f"{self._y:.0f}")
        self._stack.setCurrentIndex(1)
        self._x_edit.setFocus()
        self._x_edit.selectAll()
        self._editing = True

    def _finish_editing(self) -> None:
        """Finish editing and emit coordinates."""
        try:
            x = float(self._x_edit.text())
            y = float(self._y_edit.text())
            self.coordinate_entered.emit(x, y)
        except ValueError:
            pass  # Invalid input, just close

        self._stack.setCurrentIndex(0)
        self._editing = False

    def setCoordinates(self, x: float, y: float) -> None:
        """Set coordinates."""
        self._x = x
        self._y = y
        if not self._editing:
            self._display_label.setText(f"X: {x:.0f}, Y: {y:.0f}")

    def focusOutEvent(self, event) -> None:
        """Handle focus loss - cancel editing."""
        if self._editing:
            self._stack.setCurrentIndex(0)
            self._editing = False
        super().focusOutEvent(event)


class ZoomWidget(IconLabel):
    """Widget showing current zoom level."""

    def __init__(self, parent=None):
        super().__init__("zoom", "100%", "#0078D4", parent)
        self.setToolTip("Current zoom level")

    def setZoom(self, percent: float) -> None:
        """Set zoom percentage."""
        self.setText(f"{percent:.0f}%")


class SelectionWidget(IconLabel):
    """Widget showing selection count."""

    def __init__(self, parent=None):
        super().__init__("cursor", "", "#666666", parent)
        self.setToolTip("Number of selected items")

    def setCount(self, count: int) -> None:
        """Set selection count."""
        if count > 0:
            self.setText(f"{count} selected")
            self.setIconColor("#0078D4")
            self.show()
        else:
            self.setText("")
            self.hide()


class ModifiedWidget(IconLabel):
    """Widget showing document modified state."""

    def __init__(self, parent=None):
        super().__init__("saved", "", "#22c55e", parent)
        self._is_modified = False
        self.setToolTip("Document status")

    def setModified(self, modified: bool) -> None:
        """Set modified state."""
        self._is_modified = modified
        if modified:
            self.setIcon("modified")
            self.setIconColor("#f59e0b")  # Orange/amber
            self.setText("Modified")
            self.setToolTip("Document has unsaved changes")
        else:
            self.setIcon("saved")
            self.setIconColor("#22c55e")  # Green
            self.setText("")
            self.setToolTip("Document saved")
        self.setVisible(modified)


class SimulationStatusWidget(IconLabel):
    """Widget showing simulation status."""

    def __init__(self, parent=None):
        super().__init__("sim-ready", "Ready", "#666666", parent)
        self.setToolTip("Simulation status")

    def setStatus(self, status: str, is_running: bool = False, is_error: bool = False) -> None:
        """Set simulation status."""
        if is_error:
            self.setIcon("sim-error")
            self.setIconColor("#ef4444")  # Red
        elif is_running:
            self.setIcon("play")
            self.setIconColor("#0078D4")  # Blue
        elif status.lower() in ("complete", "done", "finished"):
            self.setIcon("sim-done")
            self.setIconColor("#22c55e")  # Green
        else:
            self.setIcon("sim-ready")
            self.setIconColor("#666666")  # Gray

        self.setText(status)

    def setDarkMode(self, dark: bool) -> None:
        """Override to keep status colors."""
        self._dark_mode = dark
        # Don't update icon - keep status-specific colors


class StatusBanner(QWidget):
    """A styled banner for displaying status messages in dialogs."""

    # Status types with their colors
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    _STYLES = {
        "success": {
            "bg": "#dcfce7",
            "border": "#86efac",
            "text": "#166534",
            "icon": "check",
            "icon_color": "#22c55e",
        },
        "error": {
            "bg": "#fee2e2",
            "border": "#fca5a5",
            "text": "#991b1b",
            "icon": "error",
            "icon_color": "#ef4444",
        },
        "warning": {
            "bg": "#fef3c7",
            "border": "#fcd34d",
            "text": "#92400e",
            "icon": "warning",
            "icon_color": "#f59e0b",
        },
        "info": {
            "bg": "#dbeafe",
            "border": "#93c5fd",
            "text": "#1e40af",
            "icon": "info",
            "icon_color": "#3b82f6",
        },
    }

    def __init__(
        self,
        text: str,
        status_type: str = "info",
        parent=None,
    ):
        super().__init__(parent)
        self._status_type = status_type
        self._text = text

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self) -> None:
        """Set up the banner UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)

        # Icon
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(20, 20)
        layout.addWidget(self._icon_label)

        # Text
        self._text_label = QLabel(self._text)
        self._text_label.setWordWrap(True)
        layout.addWidget(self._text_label, 1)

    def _apply_style(self) -> None:
        """Apply the style based on status type."""
        style = self._STYLES.get(self._status_type, self._STYLES["info"])

        # Set icon
        icon = IconService.get_icon(style["icon"], style["icon_color"])
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(20, 20))

        # Set text color
        self._text_label.setStyleSheet(
            f"color: {style['text']}; font-weight: 500; font-size: 12px;"
        )

        # Set banner style
        self.setStyleSheet(f"""
            StatusBanner {{
                background-color: {style['bg']};
                border: 1px solid {style['border']};
                border-radius: 6px;
            }}
        """)

    def setText(self, text: str) -> None:
        """Set the banner text."""
        self._text = text
        self._text_label.setText(text)

    def setStatusType(self, status_type: str) -> None:
        """Set the status type and update styling."""
        self._status_type = status_type
        self._apply_style()

    @classmethod
    def success(cls, text: str, parent=None) -> "StatusBanner":
        """Create a success banner."""
        return cls(text, cls.SUCCESS, parent)

    @classmethod
    def error(cls, text: str, parent=None) -> "StatusBanner":
        """Create an error banner."""
        return cls(text, cls.ERROR, parent)

    @classmethod
    def warning(cls, text: str, parent=None) -> "StatusBanner":
        """Create a warning banner."""
        return cls(text, cls.WARNING, parent)

    @classmethod
    def info(cls, text: str, parent=None) -> "StatusBanner":
        """Create an info banner."""
        return cls(text, cls.INFO, parent)
