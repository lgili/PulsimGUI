"""Breadcrumb widget for hierarchical navigation."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QSizePolicy,
)

from pulsimgui.services.hierarchy_service import HierarchyLevel


class BreadcrumbWidget(QWidget):
    """Widget displaying breadcrumb navigation for hierarchical schematics.

    Shows the path from root to current level, with clickable items
    for navigation.

    Signals:
        level_clicked: Emitted when a breadcrumb level is clicked (index)
        home_clicked: Emitted when the home button is clicked
    """

    level_clicked = Signal(int)  # Index of the clicked level
    home_clicked = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._levels: list[HierarchyLevel] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Home button
        self._home_btn = QPushButton()
        self._home_btn.setText("\u2302")  # House symbol
        self._home_btn.setToolTip("Go to root")
        self._home_btn.setFixedSize(24, 24)
        self._home_btn.clicked.connect(self._on_home_clicked)
        layout.addWidget(self._home_btn)

        # Container for breadcrumb items
        self._items_layout = QHBoxLayout()
        self._items_layout.setContentsMargins(0, 0, 0, 0)
        self._items_layout.setSpacing(2)
        layout.addLayout(self._items_layout)

        # Spacer
        layout.addStretch()

        # Initially hidden
        self.setVisible(False)

    def update_breadcrumb(self, levels: list[HierarchyLevel]) -> None:
        """Update the breadcrumb with a new path.

        Args:
            levels: List of hierarchy levels from root to current
        """
        self._levels = levels

        # Clear existing items
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Only show if we're not at root (more than one level)
        if len(levels) <= 1:
            self.setVisible(False)
            return

        self.setVisible(True)

        # Add breadcrumb items
        for i, level in enumerate(levels):
            # Add separator (except for first item)
            if i > 0:
                sep = QLabel(">")
                sep.setStyleSheet("color: gray; padding: 0 2px;")
                self._items_layout.addWidget(sep)

            # Create button for this level
            btn = QPushButton(level.circuit_name)
            btn.setFlat(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

            # Style differently if it's the current (last) level
            if i == len(levels) - 1:
                btn.setEnabled(False)
                btn.setStyleSheet("""
                    QPushButton {
                        font-weight: bold;
                        color: palette(text);
                        padding: 2px 6px;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        color: palette(link);
                        padding: 2px 6px;
                    }
                    QPushButton:hover {
                        text-decoration: underline;
                        background: palette(highlight);
                        color: palette(highlighted-text);
                    }
                """)
                # Connect to navigation
                btn.clicked.connect(lambda checked, idx=i: self._on_level_clicked(idx))

            self._items_layout.addWidget(btn)

    def _on_level_clicked(self, index: int) -> None:
        """Handle click on a breadcrumb level."""
        self.level_clicked.emit(index)

    def _on_home_clicked(self) -> None:
        """Handle click on home button."""
        self.home_clicked.emit()


class HierarchyBar(QWidget):
    """Bar widget showing hierarchy navigation and current level info.

    This combines breadcrumb navigation with additional controls.

    Signals:
        navigate_up: Emitted when user requests to go up one level
        navigate_to_level: Emitted with level index when user clicks breadcrumb
    """

    navigate_up = Signal()
    navigate_to_level = Signal(int)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        # Up button
        self._up_btn = QPushButton("\u2191")  # Up arrow
        self._up_btn.setToolTip("Go up one level (Backspace)")
        self._up_btn.setFixedSize(24, 24)
        self._up_btn.clicked.connect(self.navigate_up.emit)
        self._up_btn.setEnabled(False)
        layout.addWidget(self._up_btn)

        # Breadcrumb
        self._breadcrumb = BreadcrumbWidget()
        self._breadcrumb.level_clicked.connect(self.navigate_to_level.emit)
        self._breadcrumb.home_clicked.connect(lambda: self.navigate_to_level.emit(0))
        layout.addWidget(self._breadcrumb, 1)

        # Current level label
        self._level_label = QLabel("Root")
        self._level_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self._level_label)

        # Initially hidden
        self.setVisible(False)

    def update_hierarchy(self, levels: list[HierarchyLevel]) -> None:
        """Update the hierarchy display.

        Args:
            levels: List of hierarchy levels from root to current
        """
        # Update breadcrumb
        self._breadcrumb.update_breadcrumb(levels)

        # Update up button state
        self._up_btn.setEnabled(len(levels) > 1)

        # Update level label
        if levels:
            current = levels[-1]
            if len(levels) == 1:
                self._level_label.setText("Root")
            else:
                self._level_label.setText(f"In: {current.circuit_name}")

        # Show/hide the whole bar based on depth
        self.setVisible(len(levels) > 1)
