"""Animated dock widget with smooth collapse/expand."""

from PySide6.QtCore import (
    Qt,
    QPropertyAnimation,
    QEasingCurve,
    Property,
    Signal,
)
from PySide6.QtWidgets import (
    QDockWidget,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFrame,
    QSizePolicy,
)

from pulsimgui.resources.icons import IconService


class AnimatedDockWidget(QDockWidget):
    """Dock widget with animated collapse/expand functionality."""

    collapsed_changed = Signal(bool)

    ANIMATION_DURATION = 200  # ms

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._collapsed = False
        self._saved_height = 200
        self._animation: QPropertyAnimation | None = None

        # Custom title bar
        self._title_bar = DockTitleBar(title, self)
        self._title_bar.collapse_clicked.connect(self._toggle_collapse)
        self.setTitleBarWidget(self._title_bar)

        # Set features
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )

    def _toggle_collapse(self) -> None:
        """Toggle collapsed state with animation."""
        if self._collapsed:
            self._expand()
        else:
            self._collapse()

    def _collapse(self) -> None:
        """Collapse the dock with animation."""
        if self._collapsed:
            return

        # Save current height
        self._saved_height = self.widget().height() if self.widget() else 200

        # Animate to collapsed height
        if self.widget():
            self.widget().setMaximumHeight(0)
            self.widget().setVisible(False)

        self._collapsed = True
        self._title_bar.set_collapsed(True)
        self.collapsed_changed.emit(True)

    def _expand(self) -> None:
        """Expand the dock with animation."""
        if not self._collapsed:
            return

        # Restore widget visibility and height
        if self.widget():
            self.widget().setVisible(True)
            self.widget().setMaximumHeight(16777215)  # Reset max height

        self._collapsed = False
        self._title_bar.set_collapsed(False)
        self.collapsed_changed.emit(False)

    def is_collapsed(self) -> bool:
        """Check if dock is collapsed."""
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        """Set collapsed state."""
        if collapsed != self._collapsed:
            if collapsed:
                self._collapse()
            else:
                self._expand()


class DockTitleBar(QFrame):
    """Custom title bar for dock widgets with collapse button."""

    collapse_clicked = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self._collapsed = False

        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Set up the title bar UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 4, 4)
        layout.setSpacing(6)

        # Collapse button
        self._collapse_btn = QPushButton()
        self._collapse_btn.setFixedSize(18, 18)
        self._collapse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._collapse_btn.clicked.connect(self.collapse_clicked)
        self._update_collapse_icon()
        layout.addWidget(self._collapse_btn)

        # Title label
        self._title_label = QLabel(self._title)
        self._title_label.setStyleSheet("font-weight: 600; font-size: 11px;")
        layout.addWidget(self._title_label)

        layout.addStretch()

    def _apply_styles(self) -> None:
        """Apply modern styling."""
        self.setStyleSheet("""
            DockTitleBar {
                background-color: #f9fafb;
                border-bottom: 1px solid #e5e7eb;
            }
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
            }
        """)

    def _update_collapse_icon(self) -> None:
        """Update the collapse button icon."""
        icon_name = "chevron-right" if self._collapsed else "chevron-down"
        icon = IconService.get_icon(icon_name, "#6b7280")
        self._collapse_btn.setIcon(icon)

    def set_collapsed(self, collapsed: bool) -> None:
        """Update collapsed state display."""
        self._collapsed = collapsed
        self._update_collapse_icon()

    def set_title(self, title: str) -> None:
        """Set the title text."""
        self._title = title
        self._title_label.setText(title)
