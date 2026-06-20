"""Reusable styled widgets — the component layer of the design system.

Screens compose these instead of hand-styling. Each widget:

* derives every colour from :class:`~pulsimgui.services.theme_service.ThemeColors`
  and every dimension from :mod:`pulsimgui.views.design.tokens` — **no raw hex**;
* re-themes itself when ``ThemeService.theme_changed`` fires (pass the service);
* scopes its QSS to its own ``objectName`` so it never leaks styling onto
  children.

These widgets contain the only ``setStyleSheet`` calls a screen needs — that
is intentional: centralising styling here is exactly what lets us ban inline
styling everywhere else (see ``tests/test_design/test_styling_ratchet.py``).
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.services.theme_service import LIGHT_THEME, Theme
from pulsimgui.views.design.branding import Brand
from pulsimgui.views.design.tokens import (
    FontSize,
    FontWeight,
    Radius,
    Space,
)

# --------------------------------------------------------------------------
# Theming helpers
# --------------------------------------------------------------------------


def _tint(hex_color: str, alpha: int) -> str:
    """Return an ``rgba(r, g, b, a/255)`` string from a ``#rrggbb`` token.

    Used for status tints (e.g. a success badge = success colour at ~15 %
    over the surface), the termico ``bg-primary-600/15`` convention. This
    works in BOTH light and dark themes because it's derived from the strong
    status colour, not a fixed light-mode background token.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        r, g, b = 0, 0, 0
    return f"rgba({r}, {g}, {b}, {max(0, min(255, alpha)) / 255:.3f})"


class _Themed:
    """Mixin: subscribe to a ``ThemeService`` and re-style on change.

    Subclasses implement :meth:`_style_for` returning the QSS string for a
    given :class:`Theme`. If no service is given the widget styles once with
    the light theme (fine for tests / standalone previews).
    """

    def _init_theming(self, theme_service: object | None) -> None:
        self._theme_service = theme_service
        theme = LIGHT_THEME
        if theme_service is not None:
            theme = getattr(theme_service, "current_theme", LIGHT_THEME)
            changed = getattr(theme_service, "theme_changed", None)
            if changed is not None:
                changed.connect(self._on_theme_changed)
        self._on_theme_changed(theme)

    def _on_theme_changed(self, theme: Theme) -> None:
        self.setStyleSheet(self._style_for(theme))  # type: ignore[attr-defined]

    def _style_for(self, theme: Theme) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


# --------------------------------------------------------------------------
# Branding
# --------------------------------------------------------------------------

class _LogoChip(QWidget):
    """The 22×22 rounded green-gradient logo mark with a white pulse glyph.

    Custom-painted so the gradient + the waveform mark are crisp at any DPI;
    matches the handoff's menu-bar logo chip (radius 6, the
    ``Brand.GREEN_TOP → Brand.GREEN_BOTTOM`` gradient)."""

    def __init__(self, size: int = 22, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: ARG002
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(0.5, 0.5, self._size - 1, self._size - 1)
        radius = self._size * 0.27

        grad = QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, QColor(Brand.GREEN_TOP))
        grad.setColorAt(1.0, QColor(Brand.GREEN_BOTTOM))
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, radius, radius)

        # A white switching-pulse glyph (the "Pulsim" mark): a small
        # square wave — instantly readable as power electronics.
        s = self._size
        pen = QPen(QColor(Brand.MARK))
        pen.setWidthF(max(1.4, s * 0.085))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        lo, hi = s * 0.66, s * 0.36
        path = QPainterPath(QPointF(s * 0.22, lo))
        path.lineTo(s * 0.40, lo)
        path.lineTo(s * 0.40, hi)
        path.lineTo(s * 0.60, hi)
        path.lineTo(s * 0.60, lo)
        path.lineTo(s * 0.78, lo)
        p.drawPath(path)
        p.end()


class BrandChip(_Themed, QWidget):
    """Logo chip + "Pulsim Studio" wordmark — the app's identity mark.

    Designed to sit in the menu bar's top-left corner. The green chip is a
    fixed brand colour; only the muted " Studio" suffix follows the theme.
    """

    def __init__(
        self,
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DesignBrandChip")
        row = QHBoxLayout(self)
        row.setContentsMargins(Space.MD, 0, Space.SM, 0)
        row.setSpacing(Space.SM)
        row.addWidget(_LogoChip(22))
        self._wordmark = QLabel()
        self._wordmark.setObjectName("DesignBrandWordmark")
        self._wordmark.setTextFormat(Qt.TextFormat.RichText)
        row.addWidget(self._wordmark)
        self._init_theming(theme_service)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        # Rich-text wordmark: bold "Pulsim" + muted-weight " Studio".
        self._wordmark.setText(
            f'<span style="color:{c.foreground}; font-weight:700;">Pulsim</span>'
            f'<span style="color:{c.foreground_muted}; font-weight:500;"> Studio</span>'
        )
        return (
            f"#DesignBrandChip {{ background: transparent; }}"
            f"#DesignBrandWordmark {{ font-size: {FontSize.LABEL}px; }}"
        )


# --------------------------------------------------------------------------
# Containers
# --------------------------------------------------------------------------


class Card(_Themed, QFrame):
    """A rounded surface container — the basic grouping unit of a modern UI.

    Add your own layout/children to it. Set ``muted=True`` for a recessed
    (alt-surface) variant used for nested or secondary cards.
    """

    def __init__(
        self,
        theme_service: object | None = None,
        *,
        muted: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DesignCard")
        self._muted = muted
        body = QVBoxLayout(self)
        body.setContentsMargins(*Space.inset_card())
        body.setSpacing(Space.MD)
        self._body = body
        self._init_theming(theme_service)

    def body(self) -> QVBoxLayout:
        """The card's content layout — add child widgets here."""
        return self._body

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        fill = c.background_alt if self._muted else c.background
        return (
            f"#DesignCard {{"
            f" background: {fill};"
            f" border: 1px solid {c.panel_border};"
            f" border-radius: {Radius.XL}px;"
            f" }}"
        )


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------


class PageHeader(_Themed, QWidget):
    """A page/panel header: a title with an optional one-line subtitle."""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DesignPageHeader")
        col = QVBoxLayout(self)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(Space.XS)
        self._title = QLabel(title)
        self._title.setObjectName("DesignPageHeaderTitle")
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("DesignPageHeaderSubtitle")
        self._subtitle.setVisible(bool(subtitle))
        self._subtitle.setWordWrap(True)
        col.addWidget(self._title)
        col.addWidget(self._subtitle)
        self._init_theming(theme_service)

    def set_title(self, text: str) -> None:
        self._title.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle.setText(text)
        self._subtitle.setVisible(bool(text))

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        return (
            f"#DesignPageHeaderTitle {{"
            f" color: {c.foreground};"
            f" font-size: {FontSize.HEADING}px;"
            f" font-weight: {FontWeight.SEMIBOLD};"
            f" }}"
            f"#DesignPageHeaderSubtitle {{"
            f" color: {c.foreground_muted};"
            f" font-size: {FontSize.BODY}px;"
            f" }}"
        )


class SectionHeader(_Themed, QLabel):
    """A sub-section title — smaller and lighter than a PageHeader title."""

    def __init__(
        self,
        text: str,
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("DesignSectionHeader")
        self._init_theming(theme_service)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        return (
            f"#DesignSectionHeader {{"
            f" color: {c.foreground};"
            f" font-size: {FontSize.SUBTITLE}px;"
            f" font-weight: {FontWeight.SEMIBOLD};"
            f" }}"
        )


# --------------------------------------------------------------------------
# Data display
# --------------------------------------------------------------------------


class KpiTile(_Themed, QFrame):
    """A dashboard stat tile: small caps label, big value, optional unit.

    The workhorse of the loss / thermal dashboards — the kind of forms+
    tables+stats surface where Qt looks dated today and a component system
    fixes it instantly.
    """

    def __init__(
        self,
        label: str,
        value: str = "—",
        unit: str = "",
        theme_service: object | None = None,
        *,
        accent: str = "",  # "" | "success" | "warning" | "error" | "primary"
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DesignKpiTile")
        self._accent = accent
        col = QVBoxLayout(self)
        col.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.MD)
        col.setSpacing(Space.XS)

        self._label = QLabel(label.upper())
        self._label.setObjectName("DesignKpiLabel")

        value_row = QHBoxLayout()
        value_row.setContentsMargins(0, 0, 0, 0)
        value_row.setSpacing(Space.XS)
        self._value = QLabel(value)
        self._value.setObjectName("DesignKpiValue")
        self._unit = QLabel(unit)
        self._unit.setObjectName("DesignKpiUnit")
        self._unit.setVisible(bool(unit))
        value_row.addWidget(self._value)
        value_row.addWidget(self._unit)
        value_row.addStretch(1)

        col.addWidget(self._label)
        col.addLayout(value_row)
        self._init_theming(theme_service)

    def set_value(self, value: str, unit: str | None = None) -> None:
        self._value.setText(value)
        if unit is not None:
            self._unit.setText(unit)
            self._unit.setVisible(bool(unit))

    def set_label(self, label: str) -> None:
        """Update the small-caps label (e.g. to fold a subject into it,
        like ``HOTTEST · Q_BOOST``). Uppercased to match construction."""
        self._label.setText(label.upper())

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        if self._theme_service is not None:
            self._on_theme_changed(self._theme_service.current_theme)
        else:
            self._on_theme_changed(LIGHT_THEME)

    def _accent_color(self, theme: Theme) -> str:
        c = theme.colors
        return {
            "success": c.success,
            "warning": c.warning,
            "error": c.error,
            "primary": c.primary,
        }.get(self._accent, c.foreground)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        value_color = self._accent_color(theme)
        return (
            f"#DesignKpiTile {{"
            f" background: {c.background_alt};"
            f" border: 1px solid {c.panel_border};"
            f" border-radius: {Radius.LG}px;"
            f" }}"
            f"#DesignKpiLabel {{"
            f" color: {c.foreground_muted};"
            f" font-size: {FontSize.CAPTION}px;"
            f" font-weight: {FontWeight.MEDIUM};"
            f" letter-spacing: 0.5px;"
            f" }}"
            f"#DesignKpiValue {{"
            f" color: {value_color};"
            f" font-size: {FontSize.DISPLAY}px;"
            f" font-weight: {FontWeight.SEMIBOLD};"
            f" }}"
            f"#DesignKpiUnit {{"
            f" color: {c.foreground_muted};"
            f" font-size: {FontSize.LABEL}px;"
            f" }}"
        )


class StatusBadge(_Themed, QLabel):
    """A pill badge tinted by status — OK / WARN / ERROR / INFO / neutral.

    The background is the status colour at low alpha (the termico
    ``bg-…/15`` convention), so it reads correctly in light AND dark.
    """

    _KINDS = ("neutral", "success", "warning", "error", "info", "primary")

    def __init__(
        self,
        text: str,
        kind: str = "neutral",
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("DesignStatusBadge")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._kind = kind if kind in self._KINDS else "neutral"
        self._init_theming(theme_service)

    def set_kind(self, kind: str) -> None:
        self._kind = kind if kind in self._KINDS else "neutral"
        if self._theme_service is not None:
            self._on_theme_changed(self._theme_service.current_theme)
        else:
            self._on_theme_changed(LIGHT_THEME)

    def _strong_color(self, theme: Theme) -> str:
        c = theme.colors
        return {
            "success": c.success,
            "warning": c.warning,
            "error": c.error,
            "info": c.info,
            "primary": c.primary,
        }.get(self._kind, c.foreground_muted)

    def _style_for(self, theme: Theme) -> str:
        strong = self._strong_color(theme)
        return (
            f"#DesignStatusBadge {{"
            f" color: {strong};"
            f" background: {_tint(strong, 38)};"
            f" border: 1px solid {_tint(strong, 64)};"
            f" border-radius: {Radius.PILL}px;"
            f" padding: 2px {Space.SM}px;"
            f" font-size: {FontSize.SMALL}px;"
            f" font-weight: {FontWeight.MEDIUM};"
            f" }}"
        )


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------


class PrimaryButton(_Themed, QPushButton):
    """The one emphasised action on a surface — solid primary fill."""

    def __init__(
        self,
        text: str,
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("DesignPrimaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_theming(theme_service)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        return (
            f"#DesignPrimaryButton {{"
            f" background: {c.primary};"
            f" color: {c.primary_foreground};"
            f" border: none;"
            f" border-radius: {Radius.MD}px;"
            f" padding: {Space.SM}px {Space.LG}px;"
            f" font-size: {FontSize.BODY}px;"
            f" font-weight: {FontWeight.MEDIUM};"
            f" }}"
            f"#DesignPrimaryButton:hover {{ background: {c.primary_hover}; }}"
            f"#DesignPrimaryButton:pressed {{ background: {c.primary_pressed}; }}"
            f"#DesignPrimaryButton:disabled {{"
            f" background: {_tint(c.primary, 90)};"
            f" color: {_tint(c.primary_foreground, 150)};"
            f" }}"
        )


class SecondaryButton(_Themed, QPushButton):
    """A quieter action — outlined / ghost, used next to a PrimaryButton."""

    def __init__(
        self,
        text: str,
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("DesignSecondaryButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_theming(theme_service)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        return (
            f"#DesignSecondaryButton {{"
            f" background: transparent;"
            f" color: {c.foreground};"
            f" border: 1px solid {c.border};"
            f" border-radius: {Radius.MD}px;"
            f" padding: {Space.SM}px {Space.LG}px;"
            f" font-size: {FontSize.BODY}px;"
            f" font-weight: {FontWeight.MEDIUM};"
            f" }}"
            f"#DesignSecondaryButton:hover {{"
            f" background: {c.background_alt};"
            f" border-color: {c.primary};"
            f" }}"
            f"#DesignSecondaryButton:pressed {{ background: {_tint(c.primary, 30)}; }}"
            f"#DesignSecondaryButton:disabled {{ color: {c.foreground_muted}; }}"
        )


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------


class SegmentedControl(_Themed, QWidget):
    """A row of mutually-exclusive pill options (iOS-style segmented control).

    Emits :attr:`changed` with the selected option key. A clean modern
    replacement for a cramped row of radio buttons or a combo box when there
    are 2–4 choices.
    """

    changed = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],  # [(key, label), ...]
        theme_service: object | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("DesignSegmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            btn = QPushButton(label)
            btn.setObjectName("DesignSegmentedItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._select(k))
            self._group.addButton(btn)
            self._buttons[key] = btn
            row.addWidget(btn)
        if self._buttons:
            next(iter(self._buttons.values())).setChecked(True)
        self._init_theming(theme_service)

    def _select(self, key: str) -> None:
        self._buttons[key].setChecked(True)
        self.changed.emit(key)

    def current_key(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return ""

    def set_current(self, key: str) -> None:
        if key in self._buttons:
            self._buttons[key].setChecked(True)

    def _style_for(self, theme: Theme) -> str:
        c = theme.colors
        return (
            f"#DesignSegmented {{"
            f" background: {c.background_alt};"
            f" border: 1px solid {c.panel_border};"
            f" border-radius: {Radius.MD}px;"
            f" }}"
            f"#DesignSegmentedItem {{"
            f" background: transparent;"
            f" color: {c.foreground_muted};"
            f" border: none;"
            f" border-radius: {Radius.SM}px;"
            f" padding: {Space.XS}px {Space.MD}px;"
            f" font-size: {FontSize.SMALL}px;"
            f" font-weight: {FontWeight.MEDIUM};"
            f" }}"
            f"#DesignSegmentedItem:hover {{ color: {c.foreground}; }}"
            f"#DesignSegmentedItem:checked {{"
            f" background: {c.background};"
            f" color: {c.primary};"
            f" }}"
        )
