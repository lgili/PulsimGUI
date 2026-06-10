"""Example browser — PLECS-demo-library-style picker with a doc pane.

Three columns: category filter · example list (with search) · documentation
pane (title, component mix, sim settings, description). Double-click or the
Open button hands the chosen ``.pulsim`` path back to the caller.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
)

from pulsimgui.services.example_catalog import (
    ExampleInfo,
    categories,
    scan_examples,
)

_ALL = "All examples"


class ExampleBrowserDialog(QDialog):
    """Browse the bundled examples with category filter + doc pane."""

    example_chosen = Signal(str)   # absolute path of the picked .pulsim

    def __init__(self, parent=None, *, infos: list[ExampleInfo] | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Example Browser")
        self.resize(900, 520)
        self._infos = infos if infos is not None else scan_examples()
        self._selected_path: str | None = None

        root = QVBoxLayout(self)

        self._search = QLineEdit()
        self._search.setPlaceholderText(
            "Search examples… (name, topology, component)")
        self._search.textChanged.connect(self._refill_examples)
        root.addWidget(self._search)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # Column 1 — categories.
        self._cat_list = QListWidget()
        self._cat_list.addItem(_ALL)
        for cat in categories(self._infos):
            self._cat_list.addItem(cat)
        self._cat_list.setCurrentRow(0)
        self._cat_list.currentTextChanged.connect(self._refill_examples)
        split.addWidget(self._cat_list)

        # Column 2 — examples in the active category.
        self._ex_list = QListWidget()
        self._ex_list.currentItemChanged.connect(self._on_example_selected)
        self._ex_list.itemDoubleClicked.connect(self._on_open)
        split.addWidget(self._ex_list)

        # Column 3 — documentation pane.
        self._doc = QTextBrowser()
        self._doc.setOpenExternalLinks(False)
        split.addWidget(self._doc)
        split.setSizes([180, 300, 420])

        self._count = QLabel("")
        root.addWidget(self._count)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Open
            | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_open)
        buttons.rejected.connect(self.reject)
        self._open_btn = buttons.button(QDialogButtonBox.StandardButton.Open)
        self._open_btn.setEnabled(False)
        root.addWidget(buttons)

        self._refill_examples()

    # ── selection plumbing ──────────────────────────────────────────────

    @property
    def selected_path(self) -> str | None:
        """Absolute path of the chosen example (after accept)."""
        return self._selected_path

    def _active_infos(self) -> list[ExampleInfo]:
        cat = self._cat_list.currentItem()
        cat_name = cat.text() if cat else _ALL
        needle = self._search.text().strip().lower()
        out = []
        for info in self._infos:
            if cat_name != _ALL and info.category != cat_name:
                continue
            if needle:
                hay = " ".join(
                    [info.title, info.path.stem, info.category,
                     info.component_summary, *info.tags]).lower()
                if needle not in hay:
                    continue
            out.append(info)
        return out

    def _refill_examples(self, *_args) -> None:
        self._ex_list.clear()
        active = self._active_infos()
        for info in active:
            item = QListWidgetItem(info.title)
            item.setData(Qt.ItemDataRole.UserRole, info)
            item.setToolTip(str(info.path))
            self._ex_list.addItem(item)
        self._count.setText(f"{len(active)} example(s)")
        if active:
            self._ex_list.setCurrentRow(0)
        else:
            self._doc.setHtml("")
            self._open_btn.setEnabled(False)

    def _on_example_selected(self, current, _previous=None) -> None:
        if current is None:
            self._open_btn.setEnabled(False)
            return
        info: ExampleInfo = current.data(Qt.ItemDataRole.UserRole)
        self._open_btn.setEnabled(True)
        rows = [
            f"<h2>{info.title}</h2>",
            f"<p><b>Category:</b> {info.category}</p>",
            f"<p><b>File:</b> <code>{info.path.name}</code></p>",
        ]
        if info.component_summary:
            rows.append(
                f"<p><b>Components ({info.n_components}):</b> "
                f"{info.component_summary}</p>")
        if info.tstop is not None:
            rows.append(f"<p><b>Simulates:</b> {info.tstop:g} s</p>")
        if info.description:
            rows.append(f"<hr><p>{info.description}</p>")
        self._doc.setHtml("\n".join(rows))

    def _on_open(self, *_args) -> None:
        item = self._ex_list.currentItem()
        if item is None:
            return
        info: ExampleInfo = item.data(Qt.ItemDataRole.UserRole)
        self._selected_path = str(Path(info.path).resolve())
        self.example_chosen.emit(self._selected_path)
        self.accept()
