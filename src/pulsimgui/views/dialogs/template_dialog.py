"""New from Template dialog for creating projects from predefined templates."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QLabel,
    QTextBrowser,
    QDialogButtonBox,
    QSplitter,
    QGroupBox,
    QFrame,
    QWidget,
)

from pulsimgui.services.template_service import (
    TemplateService,
    TemplateInfo,
    TemplateCategory,
)


class TemplateListItem(QListWidgetItem):
    """Custom list item for templates."""

    def __init__(self, template_info: TemplateInfo):
        super().__init__(template_info.name)
        self.template_info = template_info
        self.setToolTip(template_info.description)


class TemplateDialog(QDialog):
    """Dialog for selecting and creating a new project from a template."""

    template_selected = Signal(str)  # Emits template_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_template: TemplateInfo | None = None

        self.setWindowTitle("New from Template")
        self.setMinimumSize(700, 500)
        self.resize(800, 550)

        self._setup_ui()
        self._load_templates()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Select a template to start a new project:")
        header.setStyleSheet("font-size: 14px; margin-bottom: 10px;")
        layout.addWidget(header)

        # Main splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left side - Category and template list
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Category selector
        category_group = QGroupBox("Categories")
        category_layout = QVBoxLayout(category_group)
        self._category_list = QListWidget()
        self._category_list.currentRowChanged.connect(self._on_category_changed)
        category_layout.addWidget(self._category_list)
        left_layout.addWidget(category_group)

        # Template list
        template_group = QGroupBox("Templates")
        template_layout = QVBoxLayout(template_group)
        self._template_list = QListWidget()
        self._template_list.currentItemChanged.connect(self._on_template_changed)
        self._template_list.itemDoubleClicked.connect(self._on_template_double_clicked)
        template_layout.addWidget(self._template_list)
        left_layout.addWidget(template_group)

        splitter.addWidget(left_widget)

        # Right side - Template details
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        details_group = QGroupBox("Template Details")
        details_layout = QVBoxLayout(details_group)

        # Template name
        self._name_label = QLabel()
        name_font = QFont()
        name_font.setPointSize(14)
        name_font.setBold(True)
        self._name_label.setFont(name_font)
        details_layout.addWidget(self._name_label)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        details_layout.addWidget(separator)

        # Description
        self._description_browser = QTextBrowser()
        self._description_browser.setOpenExternalLinks(False)
        self._description_browser.setStyleSheet(
            "QTextBrowser { background-color: transparent; border: none; }"
        )
        details_layout.addWidget(self._description_browser)

        # Tags
        self._tags_label = QLabel()
        self._tags_label.setWordWrap(True)
        self._tags_label.setStyleSheet("color: gray; font-style: italic;")
        details_layout.addWidget(self._tags_label)

        # Component info
        self._components_label = QLabel()
        self._components_label.setWordWrap(True)
        details_layout.addWidget(self._components_label)

        right_layout.addWidget(details_group)

        splitter.addWidget(right_widget)

        # Set splitter proportions
        splitter.setSizes([300, 500])
        layout.addWidget(splitter)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._ok_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        self._ok_button.setText("Create Project")
        self._ok_button.setEnabled(False)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _load_templates(self) -> None:
        """Load categories and templates."""
        # Add "All" category first
        all_item = QListWidgetItem("All Templates")
        all_item.setData(Qt.ItemDataRole.UserRole, None)
        self._category_list.addItem(all_item)

        # Add categories
        for category, name in TemplateService.get_categories():
            # Only add if there are templates in this category
            templates = TemplateService.get_templates_by_category(category)
            if templates:
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, category)
                self._category_list.addItem(item)

        # Select "All" by default
        self._category_list.setCurrentRow(0)

    def _on_category_changed(self, row: int) -> None:
        """Handle category selection change."""
        if row < 0:
            return

        item = self._category_list.item(row)
        category = item.data(Qt.ItemDataRole.UserRole)

        self._template_list.clear()

        if category is None:
            # Show all templates
            templates = TemplateService.get_all_templates()
        else:
            templates = TemplateService.get_templates_by_category(category)

        for template_info in templates:
            list_item = TemplateListItem(template_info)
            self._template_list.addItem(list_item)

        # Clear details if nothing selected
        if self._template_list.count() > 0:
            self._template_list.setCurrentRow(0)
        else:
            self._clear_details()

    def _on_template_changed(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """Handle template selection change."""
        if current is None or not isinstance(current, TemplateListItem):
            self._clear_details()
            return

        template_info = current.template_info
        self._selected_template = template_info
        self._show_template_details(template_info)
        self._ok_button.setEnabled(True)

    def _on_template_double_clicked(self, item: QListWidgetItem) -> None:
        """Handle double-click on template."""
        if isinstance(item, TemplateListItem):
            self._selected_template = item.template_info
            self._on_accept()

    def _show_template_details(self, info: TemplateInfo) -> None:
        """Display template details."""
        self._name_label.setText(info.name)

        # Format description
        desc_html = f"<p>{info.description}</p>"
        self._description_browser.setHtml(desc_html)

        # Format tags
        if info.tags:
            tags_text = "Tags: " + ", ".join(info.tags)
            self._tags_label.setText(tags_text)
            self._tags_label.setVisible(True)
        else:
            self._tags_label.setVisible(False)

        # Get component count from a sample circuit
        circuit = TemplateService.create_circuit_from_template(info.id)
        if circuit:
            comp_count = len(circuit.components)
            self._components_label.setText(f"Components: {comp_count}")
            self._components_label.setVisible(True)
        else:
            self._components_label.setVisible(False)

    def _clear_details(self) -> None:
        """Clear template details display."""
        self._name_label.setText("Select a template")
        self._description_browser.clear()
        self._tags_label.clear()
        self._components_label.clear()
        self._selected_template = None
        self._ok_button.setEnabled(False)

    def _on_accept(self) -> None:
        """Handle OK button click."""
        if self._selected_template:
            self.template_selected.emit(self._selected_template.id)
            self.accept()

    def get_selected_template_id(self) -> str | None:
        """Get the selected template ID."""
        if self._selected_template:
            return self._selected_template.id
        return None
