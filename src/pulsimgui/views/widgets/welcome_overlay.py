"""Welcome surface shown on the schematic canvas when no project is open.

Replaces the text-only "Start your schematic" empty state introduced in
v0.6 with four clickable action cards (New / Open / Recent / Template).
The card-grid is laid out 2x2 with hover lift, follows the active
theme, and emits semantic signals so the host MainWindow can wire it
to its existing project-management helpers without coupling.

Activation contract:

  - ``set_recent_paths(paths)`` — feed the most-recent file list every
    time it changes; we render up to ``MAX_RECENT`` entries.
  - ``set_theme(theme)`` — keep colors in sync with the global theme
    service.
  - User clicks → corresponding signal fires → host handles it.

The widget is intentionally lightweight: no QGraphicsView, no animation
framework, no async work. Drop-in for the existing
``_empty_state_frame`` slot in ``SchematicView``.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


MAX_RECENT = 5


class _ActionCard(QFrame):
    """Single hoverable action card."""

    clicked = Signal()

    def __init__(self, title: str, subtitle: str, glyph: str, accent: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeCard")
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(6)

        glyph_label = QLabel(glyph, self)
        glyph_label.setObjectName("WelcomeCardGlyph")
        glyph_font = glyph_label.font()
        glyph_font.setPointSize(22)
        glyph_label.setFont(glyph_font)
        layout.addWidget(glyph_label)

        title_label = QLabel(title, self)
        title_label.setObjectName("WelcomeCardTitle")
        title_font = title_label.font()
        title_font.setPointSize(13)
        title_font.setBold(True)
        title_label.setFont(title_font)
        layout.addWidget(title_label)

        subtitle_label = QLabel(subtitle, self)
        subtitle_label.setObjectName("WelcomeCardSubtitle")
        subtitle_label.setWordWrap(True)
        sub_font = subtitle_label.font()
        sub_font.setPointSize(10)
        subtitle_label.setFont(sub_font)
        layout.addWidget(subtitle_label, stretch=1)

        self._apply_style(hovered=False)

    # --- Public --------------------------------------------------------

    def accent(self) -> str:
        return self._accent

    def apply_palette(self, *, fg: str, fg_muted: str, surface: str,
                      border: str, accent: str | None = None) -> None:
        if accent is not None:
            self._accent = accent
        self._palette_fg = fg
        self._palette_fg_muted = fg_muted
        self._palette_surface = surface
        self._palette_border = border
        self._apply_style(hovered=False)

    # --- Qt event hooks ------------------------------------------------

    def enterEvent(self, event):  # noqa: D401 - Qt override
        self._apply_style(hovered=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hovered=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    # --- Internals -----------------------------------------------------

    def _apply_style(self, *, hovered: bool) -> None:
        # Use cached palette if present; else fall back to neutral defaults.
        fg = getattr(self, "_palette_fg", "#111827")
        fg_muted = getattr(self, "_palette_fg_muted", "#6b7280")
        surface = getattr(self, "_palette_surface", "#ffffff")
        border = getattr(self, "_palette_border", "#d1d5db")
        if hovered:
            surface_rgba = self._accent_rgba(self._accent, 0.10)
            border_color = self._accent
        else:
            surface_rgba = surface
            border_color = border
        self.setStyleSheet(
            f"#WelcomeCard {{"
            f"  background: {surface_rgba};"
            f"  border: 1px solid {border_color};"
            f"  border-radius: 10px;"
            f"}}"
            f"QLabel#WelcomeCardGlyph {{ color: {self._accent}; }}"
            f"QLabel#WelcomeCardTitle  {{ color: {fg}; }}"
            f"QLabel#WelcomeCardSubtitle {{ color: {fg_muted}; }}"
        )

    @staticmethod
    def _accent_rgba(accent_hex: str, alpha: float) -> str:
        # Convert ``#rrggbb`` → ``rgba(r,g,b,a)`` for hover-tint backgrounds.
        if accent_hex.startswith("#") and len(accent_hex) == 7:
            r = int(accent_hex[1:3], 16)
            g = int(accent_hex[3:5], 16)
            b = int(accent_hex[5:7], 16)
            return f"rgba({r}, {g}, {b}, {alpha})"
        return accent_hex


class WelcomeOverlay(QFrame):
    """Four-card surface shown when the canvas is empty."""

    new_project_requested = Signal()
    open_project_requested = Signal()
    recent_project_requested = Signal(str)  # absolute path
    template_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomeOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)

        self._recent_paths: list[str] = []
        self._recent_buttons: list[QPushButton] = []
        self._palette = {
            "fg": "#111827",
            "fg_muted": "#6b7280",
            "surface": "#ffffff",
            "surface_muted": "rgba(255,255,255,0.6)",
            "border": "#d1d5db",
        }

        self._setup_ui()

    # --- Public API ----------------------------------------------------

    def set_recent_paths(self, paths: list[str] | tuple[str, ...]) -> None:
        """Refresh the Recent-projects card with the supplied paths."""
        self._recent_paths = list(paths)[:MAX_RECENT]
        self._rebuild_recent_list()

    def apply_palette(
        self,
        *,
        foreground: str,
        foreground_muted: str,
        surface: str,
        surface_muted: str,
        border: str,
    ) -> None:
        """Refresh colors for the active theme."""
        self._palette = {
            "fg": foreground,
            "fg_muted": foreground_muted,
            "surface": surface,
            "surface_muted": surface_muted,
            "border": border,
        }
        self._apply_outer_style()
        for card in (self._card_new, self._card_open, self._card_recent,
                     self._card_template):
            card.apply_palette(
                fg=foreground,
                fg_muted=foreground_muted,
                surface=surface,
                border=border,
            )
        self._rebuild_recent_list()

    def preferred_size(self) -> tuple[int, int]:
        """Return ``(w, h)`` so the host can center the overlay."""
        return 720, 360

    # --- UI construction ----------------------------------------------

    def _setup_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        title = QLabel("Welcome to PulsimGui", self)
        title.setObjectName("WelcomeTitle")
        title_font = title.font()
        title_font.setPointSize(22)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        outer.addWidget(title)

        subtitle = QLabel(
            "Open a project, start a blank schematic, or grab a reference "
            "topology from the gallery.",
            self,
        )
        subtitle.setObjectName("WelcomeSubtitle")
        subtitle.setWordWrap(True)
        sub_font = subtitle.font()
        sub_font.setPointSize(11)
        subtitle.setFont(sub_font)
        outer.addWidget(subtitle)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        outer.addLayout(grid, stretch=1)

        self._card_new = _ActionCard(
            "New schematic",
            "Blank canvas with a sensible 1 ms / dt = 1 µs default.",
            "＋",
            accent="#16a34a",
            parent=self,
        )
        self._card_new.clicked.connect(self.new_project_requested)

        self._card_open = _ActionCard(
            "Open project…",
            "Pick a .pulsim file from anywhere on disk.",
            "📂",
            accent="#2563eb",
            parent=self,
        )
        self._card_open.clicked.connect(self.open_project_requested)

        self._card_recent = _ActionCard(
            "Recent projects",
            "Pick up where you left off.",
            "🕒",
            accent="#7c3aed",
            parent=self,
        )
        # Recent card's "primary" click opens the most recent entry; the
        # individual file buttons let users pick another one without
        # leaving the welcome surface.
        self._card_recent.clicked.connect(self._on_recent_card_clicked)

        self._card_template = _ActionCard(
            "From template",
            "Buck, boost, flyback, LLC, FOC, motor… 15 gallery topologies.",
            "✨",
            accent="#ea580c",
            parent=self,
        )
        self._card_template.clicked.connect(self.template_requested)

        grid.addWidget(self._card_new, 0, 0)
        grid.addWidget(self._card_open, 0, 1)
        grid.addWidget(self._card_recent, 1, 0)
        grid.addWidget(self._card_template, 1, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(0, 1)
        grid.setRowStretch(1, 1)

        # Recent-projects sub-list lives inside the Recent card.
        self._recent_inner = QWidget(self._card_recent)
        self._recent_inner.setObjectName("WelcomeRecentInner")
        self._recent_layout = QVBoxLayout(self._recent_inner)
        self._recent_layout.setContentsMargins(0, 4, 0, 0)
        self._recent_layout.setSpacing(2)
        self._card_recent.layout().addWidget(self._recent_inner)

        self._apply_outer_style()
        self._rebuild_recent_list()

    def _rebuild_recent_list(self) -> None:
        for btn in self._recent_buttons:
            btn.setParent(None)
            btn.deleteLater()
        self._recent_buttons.clear()

        if not self._recent_paths:
            placeholder = QPushButton("No recent files yet")
            placeholder.setObjectName("WelcomeRecentEmpty")
            placeholder.setEnabled(False)
            placeholder.setFlat(True)
            placeholder.setStyleSheet(
                "QPushButton#WelcomeRecentEmpty {"
                f"  color: {self._palette['fg_muted']};"
                "  background: transparent; text-align: left;"
                "  padding: 1px 0; border: 0;"
                "}"
            )
            self._recent_layout.addWidget(placeholder)
            self._recent_buttons.append(placeholder)
            return

        for path in self._recent_paths:
            name = os.path.basename(path) or path
            display = name if len(name) <= 30 else name[:27] + "…"
            btn = QPushButton(display)
            btn.setObjectName("WelcomeRecentEntry")
            btn.setToolTip(path)
            btn.setFlat(True)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setStyleSheet(
                "QPushButton#WelcomeRecentEntry {"
                f"  color: {self._palette['fg']};"
                "  background: transparent; text-align: left;"
                "  padding: 1px 0; border: 0;"
                "  font-size: 10pt;"
                "}"
                "QPushButton#WelcomeRecentEntry:hover {"
                f"  color: {self._card_recent.accent()};"
                "  text-decoration: underline;"
                "}"
            )
            btn.clicked.connect(
                lambda _checked=False, p=path: self.recent_project_requested.emit(p)
            )
            self._recent_layout.addWidget(btn)
            self._recent_buttons.append(btn)

    def _on_recent_card_clicked(self) -> None:
        # If the user clicks the card body (not one of the file buttons),
        # default to opening the topmost recent file.
        if self._recent_paths:
            self.recent_project_requested.emit(self._recent_paths[0])

    def _apply_outer_style(self) -> None:
        self.setStyleSheet(
            f"#WelcomeOverlay {{"
            f"  background: {self._palette['surface_muted']};"
            f"  border: 1px solid {self._palette['border']};"
            f"  border-radius: 16px;"
            f"}}"
            f"QLabel#WelcomeTitle    {{ color: {self._palette['fg']}; }}"
            f"QLabel#WelcomeSubtitle {{ color: {self._palette['fg_muted']}; }}"
        )


__all__ = ["WelcomeOverlay", "MAX_RECENT"]
