"""Keyboard shortcuts customization dialog."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTreeWidget,
    QTreeWidgetItem,
    QPushButton,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QHeaderView,
    QGroupBox,
    QWidget,
)

from pulsimgui.services.shortcut_service import ShortcutService, ShortcutInfo


class ShortcutEditor(QLineEdit):
    """Custom line edit for capturing keyboard shortcuts."""

    shortcut_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Press shortcut keys...")
        self.setReadOnly(True)
        self._current_shortcut = ""

    def keyPressEvent(self, event):
        """Capture key press and convert to shortcut string."""
        key = event.key()
        modifiers = event.modifiers()

        # Ignore modifier-only presses
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return

        # Build shortcut string
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")

        # Get key name
        key_seq = QKeySequence(key)
        key_str = key_seq.toString()
        if key_str:
            parts.append(key_str)

        shortcut = "+".join(parts)
        self._current_shortcut = shortcut
        self.setText(shortcut)
        self.shortcut_changed.emit(shortcut)

    def set_shortcut(self, shortcut: str):
        """Set the current shortcut."""
        self._current_shortcut = shortcut
        self.setText(shortcut)

    def get_shortcut(self) -> str:
        """Get the current shortcut."""
        return self._current_shortcut

    def clear_shortcut(self):
        """Clear the current shortcut."""
        self._current_shortcut = ""
        self.clear()


class KeyboardShortcutsDialog(QDialog):
    """Dialog for customizing keyboard shortcuts."""

    def __init__(self, shortcut_service: ShortcutService, parent=None):
        super().__init__(parent)
        self._shortcut_service = shortcut_service
        self._pending_changes: dict[str, str] = {}
        self._current_item: QTreeWidgetItem | None = None

        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(700, 500)

        self._setup_ui()
        self._load_shortcuts()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Description
        desc = QLabel(
            "Double-click on a shortcut to edit it. "
            "Click 'Clear' to remove a shortcut, or 'Reset' to restore the default."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Tree widget for shortcuts
        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Action", "Shortcut", "Default"])
        self._tree.setColumnCount(3)
        self._tree.setRootIsDecorated(True)
        self._tree.setAlternatingRowColors(True)
        self._tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.resizeSection(1, 150)
        header.resizeSection(2, 150)
        layout.addWidget(self._tree)

        # Editor group
        editor_group = QGroupBox("Edit Shortcut")
        editor_layout = QVBoxLayout(editor_group)

        self._action_label = QLabel("Select an action to edit its shortcut")
        editor_layout.addWidget(self._action_label)

        shortcut_row = QHBoxLayout()
        shortcut_row.addWidget(QLabel("New shortcut:"))
        self._shortcut_editor = ShortcutEditor()
        self._shortcut_editor.shortcut_changed.connect(self._on_shortcut_edited)
        shortcut_row.addWidget(self._shortcut_editor)

        self._clear_btn = QPushButton("Clear")
        self._clear_btn.clicked.connect(self._on_clear_shortcut)
        self._clear_btn.setEnabled(False)
        shortcut_row.addWidget(self._clear_btn)

        self._reset_btn = QPushButton("Reset to Default")
        self._reset_btn.clicked.connect(self._on_reset_shortcut)
        self._reset_btn.setEnabled(False)
        shortcut_row.addWidget(self._reset_btn)

        editor_layout.addLayout(shortcut_row)

        self._conflict_label = QLabel()
        self._conflict_label.setStyleSheet("color: red;")
        editor_layout.addWidget(self._conflict_label)

        layout.addWidget(editor_group)

        # Dialog buttons
        button_layout = QHBoxLayout()

        reset_all_btn = QPushButton("Reset All to Defaults")
        reset_all_btn.clicked.connect(self._on_reset_all)
        button_layout.addWidget(reset_all_btn)

        button_layout.addStretch()

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)

        layout.addLayout(button_layout)

    def _load_shortcuts(self) -> None:
        """Load shortcuts into the tree widget."""
        self._tree.clear()
        categories = self._shortcut_service.get_shortcuts_by_category()

        for category_name, shortcuts in sorted(categories.items()):
            category_item = QTreeWidgetItem([category_name])
            category_item.setFlags(category_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = category_item.font(0)
            font.setBold(True)
            category_item.setFont(0, font)

            for info in sorted(shortcuts, key=lambda x: x.name):
                item = QTreeWidgetItem([info.name, info.current_shortcut, info.default_shortcut])
                item.setData(0, Qt.ItemDataRole.UserRole, info.action_id)
                item.setToolTip(0, info.description)
                category_item.addChild(item)

            self._tree.addTopLevelItem(category_item)
            category_item.setExpanded(True)

    def _on_selection_changed(self) -> None:
        """Handle selection change in tree."""
        items = self._tree.selectedItems()
        if not items:
            self._current_item = None
            self._action_label.setText("Select an action to edit its shortcut")
            self._shortcut_editor.clear_shortcut()
            self._shortcut_editor.setEnabled(False)
            self._clear_btn.setEnabled(False)
            self._reset_btn.setEnabled(False)
            self._conflict_label.clear()
            return

        item = items[0]
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if not action_id:
            return

        self._current_item = item
        info = self._shortcut_service.get_all_shortcuts().get(action_id)
        if info:
            self._action_label.setText(f"<b>{info.name}</b> - {info.description}")
            # Use pending change if exists, otherwise current shortcut
            shortcut = self._pending_changes.get(action_id, info.current_shortcut)
            self._shortcut_editor.set_shortcut(shortcut)
            self._shortcut_editor.setEnabled(True)
            self._clear_btn.setEnabled(True)
            self._reset_btn.setEnabled(True)
            self._conflict_label.clear()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        """Handle double-click to edit shortcut."""
        action_id = item.data(0, Qt.ItemDataRole.UserRole)
        if action_id:
            self._shortcut_editor.setFocus()
            self._shortcut_editor.selectAll()

    def _on_shortcut_edited(self, shortcut: str) -> None:
        """Handle shortcut being edited."""
        if not self._current_item:
            return

        action_id = self._current_item.data(0, Qt.ItemDataRole.UserRole)
        if not action_id:
            return

        # Check for conflicts
        conflict = self._shortcut_service.find_conflict(action_id, shortcut)
        # Also check pending changes
        if not conflict:
            for aid, s in self._pending_changes.items():
                if aid != action_id and s == shortcut:
                    all_shortcuts = self._shortcut_service.get_all_shortcuts()
                    if aid in all_shortcuts:
                        conflict = all_shortcuts[aid]
                        break

        if conflict:
            self._conflict_label.setText(f"Conflict with: {conflict.name}")
        else:
            self._conflict_label.clear()
            # Store pending change
            self._pending_changes[action_id] = shortcut
            self._current_item.setText(1, shortcut)

    def _on_clear_shortcut(self) -> None:
        """Clear the current shortcut."""
        if self._current_item:
            action_id = self._current_item.data(0, Qt.ItemDataRole.UserRole)
            if action_id:
                self._pending_changes[action_id] = ""
                self._current_item.setText(1, "")
                self._shortcut_editor.clear_shortcut()
                self._conflict_label.clear()

    def _on_reset_shortcut(self) -> None:
        """Reset current shortcut to default."""
        if self._current_item:
            action_id = self._current_item.data(0, Qt.ItemDataRole.UserRole)
            info = self._shortcut_service.get_all_shortcuts().get(action_id)
            if info:
                self._pending_changes[action_id] = info.default_shortcut
                self._current_item.setText(1, info.default_shortcut)
                self._shortcut_editor.set_shortcut(info.default_shortcut)
                self._conflict_label.clear()

    def _on_reset_all(self) -> None:
        """Reset all shortcuts to defaults."""
        result = QMessageBox.question(
            self,
            "Reset All Shortcuts",
            "Are you sure you want to reset all keyboard shortcuts to their defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result == QMessageBox.StandardButton.Yes:
            self._pending_changes.clear()
            for info in self._shortcut_service.get_all_shortcuts().values():
                self._pending_changes[info.action_id] = info.default_shortcut
            self._load_shortcuts()
            # Re-apply pending changes to tree
            for i in range(self._tree.topLevelItemCount()):
                category = self._tree.topLevelItem(i)
                for j in range(category.childCount()):
                    item = category.child(j)
                    action_id = item.data(0, Qt.ItemDataRole.UserRole)
                    if action_id in self._pending_changes:
                        item.setText(1, self._pending_changes[action_id])

    def _on_accept(self) -> None:
        """Apply changes and close."""
        # Check for conflicts in pending changes
        for action_id, shortcut in self._pending_changes.items():
            if shortcut:
                for other_id, other_shortcut in self._pending_changes.items():
                    if other_id != action_id and other_shortcut == shortcut:
                        QMessageBox.warning(
                            self,
                            "Conflict",
                            f"Cannot save: multiple actions have the same shortcut '{shortcut}'",
                        )
                        return

        # Apply all pending changes
        for action_id, shortcut in self._pending_changes.items():
            info = self._shortcut_service.get_all_shortcuts().get(action_id)
            if info:
                info.current_shortcut = shortcut
                self._shortcut_service._shortcuts[action_id] = info

        self._shortcut_service.save_shortcuts()
        self._shortcut_service.apply_all_shortcuts()
        self._shortcut_service.shortcuts_changed.emit()
        self.accept()
