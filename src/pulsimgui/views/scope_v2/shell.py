"""``BaseScopeWindow`` — the single modular scope window.

PLECS-style single-window viewer. The shell renders the chrome and
owns no behaviour: capabilities are plugged in by each variant
(``ElectricalScope``, ``ThermalScope``, …) at construction time.

Layout (PLECS-like, dark-first):

    ┌──────────────────────────────────────────────────────────────┐
    │  ScopeHeader (brand + scope title + type badge + win ctrl)   │
    │  Menubar     (File / View / Simulation / Tools / Window / …)  │
    │  Toolbar     (transport | view | cursor | math | export)     │
    ├─────┬──────────────────────────────────────────────┬─────────┤
    │ Sig │                                              │ Insp.   │
    │ nal │                                              │ (cur-   │
    │  s  │            PlotCanvas (stacked panes)         │  sors,  │
    │     │                                              │  trig., │
    │ rail│                                              │  meas.) │
    ├─────┴──────────────────────────────────────────────┴─────────┤
    │              Bottom drawer (measurements + events)            │
    ├──────────────────────────────────────────────────────────────┤
    │       Timeline scrubber  | Fit | Range ▾ | + Measure | …      │
    └──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen, QPolygonF
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QProxyStyle,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.resources.icons import IconService
from pulsimgui.services import font_service
from pulsimgui.services.theme_service import DARK_THEME

from .plot_canvas import PlotCanvas

# ── Palette tokens ──────────────────────────────────────────────────────────
# The scope's palette is *derived* from the host's ``ThemeService.current_theme``
# at construction time so the scope window always matches the rest of the
# app (no more Frankenstein clash when the main window is in light theme and
# the scope is hard-locked to dark). ``_palette_from_theme`` does the mapping
# from the rich :class:`ThemeColors` schema down to the small token dict
# the rest of the shell uses.
#
# When the host doesn't pass a theme_service (tests, headless renders,
# legacy callers) we fall back to ``_DARK_FALLBACK`` — the same mapping
# applied to the built-in dark theme's ``ThemeColors``, so the fallback
# stays pixel-identical to the themed dark path instead of drifting on
# its own hand-tuned hex. (Defined after ``_palette_from_theme`` below.)


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    """Convert ``"#RRGGBB"`` to a CSS ``rgba(r,g,b,a)`` string.

    Used to derive the soft accent / success / warning fills from the
    theme's solid colours.
    """
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) < 6:
        return f"rgba(0, 0, 0, {alpha})"
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


class _ComboArrowProxy(QProxyStyle):
    """QProxyStyle that swaps the macOS native ``=`` combo chevron for
    a clean down-triangle in our theme's text-dim colour.

    Per-widget setStyleSheet AND ``QComboBox::down-arrow`` QSS rules
    are BOTH ignored by QMacStyle for the sub-control rendering of
    ``PE_IndicatorComboBoxArrow`` — the only reliable override is at
    the QStyle layer. Each scope combo gets one of these via
    ``combo.setStyle(_ComboArrowProxy(combo.style(), colour))`` in
    ``_normalize_form_widgets`` below.
    """

    def __init__(self, parent_style, colour: str) -> None:
        super().__init__(parent_style)
        self._arrow_colour = QColor(colour)

    def _paint_down_triangle(self, painter, rect) -> None:
        cx = rect.center().x()
        cy = rect.center().y()
        tri = QPolygonF([
            QPointF(cx - 4.0, cy - 2.5),
            QPointF(cx + 4.0, cy - 2.5),
            QPointF(cx, cy + 2.5),
        ])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(self._arrow_colour))
        painter.drawPolygon(tri)
        painter.restore()

    def drawComplexControl(self, control, option, painter, widget=None) -> None:  # noqa: D401
        """Override the whole CC_ComboBox draw so we paint the field
        ourselves and skip QMacStyle's native NSPopUpButton path.

        ``drawPrimitive(PE_IndicatorArrowDown)`` doesn't fire on macOS
        because QMacStyle short-circuits at the complex-control level
        for combos. Painting the field via the stylesheet's QSS and
        then layering our triangle on top is the only reliable way.
        """
        if control == QStyle.ComplexControl.CC_ComboBox:
            # Let the parent style paint the body (QSS-respecting), then
            # paint our chevron over the arrow sub-control rect.
            super().drawComplexControl(control, option, painter, widget)
            arrow_rect = self.subControlRect(
                control,
                option,
                QStyle.SubControl.SC_ComboBoxArrow,
                widget,
            )
            if arrow_rect.isValid():
                self._paint_down_triangle(painter, arrow_rect)
            return
        super().drawComplexControl(control, option, painter, widget)

    def drawPrimitive(self, element, option, painter, widget=None) -> None:  # noqa: D401
        # On PySide6 6.x the combo's chevron is drawn via
        # ``PE_IndicatorArrowDown`` (older Qt had a dedicated
        # ``PE_IndicatorComboBoxArrow`` but it was retired). Spin
        # boxes use ``PE_IndicatorSpinDown``.
        down_elements = {
            QStyle.PrimitiveElement.PE_IndicatorArrowDown,
            QStyle.PrimitiveElement.PE_IndicatorSpinDown,
        }
        if element in down_elements:
            rect = option.rect
            # Centred 8×5 down-triangle inside the sub-control rect.
            cx = rect.center().x()
            cy = rect.center().y()
            tri = QPolygonF([
                QPointF(cx - 4.0, cy - 2.5),
                QPointF(cx + 4.0, cy - 2.5),
                QPointF(cx, cy + 2.5),
            ])
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._arrow_colour))
            painter.drawPolygon(tri)
            painter.restore()
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorSpinUp:
            rect = option.rect
            cx = rect.center().x()
            cy = rect.center().y()
            tri = QPolygonF([
                QPointF(cx - 4.0, cy + 2.5),
                QPointF(cx + 4.0, cy + 2.5),
                QPointF(cx, cy - 2.5),
            ])
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(self._arrow_colour))
            painter.drawPolygon(tri)
            painter.restore()
            return
        super().drawPrimitive(element, option, painter, widget)


def _palette_from_theme(theme) -> dict[str, str]:
    """Map the host ``ThemeColors`` schema down to the scope token dict.

    Works for both light and dark themes — we map the rich
    ``background / panel_background / input_background`` ladder to the
    scope's ``bg / surface / surface_alt`` ladder. ``surface_hi`` is
    derived from ``menu_background`` so popups feel "lifted" from the
    main surface. Soft accent/success/etc. fills come from
    :func:`_hex_to_rgba` so they pick up the theme's exact accent
    instead of a hard-coded blue.
    """
    c = theme.colors
    return {
        "bg":            c.background,
        "surface":       c.background_alt,
        "surface_alt":   c.panel_background,
        "surface_hi":    c.menu_background,
        "border":        c.border,
        "border_soft":   c.divider,
        "text":          c.foreground,
        "text_dim":      c.foreground_muted,
        "muted":         c.input_placeholder,
        "accent":        c.primary,
        "accent_soft":   _hex_to_rgba(c.primary, 0.16),
        "accent_strong": c.primary_hover,
        "success":       c.success,
        "success_soft":  _hex_to_rgba(c.success, 0.16),
        "warning":       c.warning,
        "warning_soft":  _hex_to_rgba(c.warning, 0.16),
        "error":         c.error,
        "error_soft":    _hex_to_rgba(c.error, 0.16),
        "plot_bg":       c.plot_background,
        "plot_grid":     c.plot_grid,
        "plot_axis":     c.plot_axis,
    }


# Token-derived fallback for theme-service-less construction (tests,
# headless renders, ad-hoc embedding) — the built-in dark theme mapped
# through the exact same ladder the themed path uses.
_DARK_FALLBACK = _palette_from_theme(DARK_THEME)


# ── Scope variant / capability protocols ────────────────────────────────────


class ScopeVariant(Protocol):
    """Describes one scope flavour (electrical, thermal, …).

    A variant tells the shell what to render in the header badge, what
    glyph to use, what signal-naming convention to apply, and which
    units the Y axes default to. The shell itself is variant-agnostic.
    """

    name: str          # ``"Scope: V_out"`` — shown in the header
    type_label: str    # ``"electrical"`` / ``"thermal"`` — small badge
    type_glyph: str    # ``"⚡"`` / ``"🌡"`` — single-glyph icon
    accent_color: str  # variant-specific accent (e.g. orange for thermal)
    default_unit: str  # ``"V"`` / ``"°C"``


class ScopeCapability(Protocol):
    """Plug-in module that adds behaviour to the shell.

    Capabilities are constructed by the variant and attached to the
    shell. The shell calls ``attach(shell)`` once after the chrome has
    been built so the capability can hook into menus, toolbar, side
    panels, and the plot canvas.
    """

    def attach(self, shell: "BaseScopeWindow") -> None: ...


# ── Header ──────────────────────────────────────────────────────────────────


class _ScopeHeader(QFrame):
    """Top header bar: type badge + scope name + version + window controls."""

    def __init__(self, *, variant: ScopeVariant, version: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeHeader")
        self.setFixedHeight(40)
        self._variant = variant

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 14, 0)
        layout.setSpacing(12)

        # Type glyph — accent-coloured, slightly larger for visual weight.
        self._glyph = QLabel(variant.type_glyph)
        self._glyph.setObjectName("ScopeHeaderGlyph")
        f = QFont()
        f.setPointSize(15)
        self._glyph.setFont(f)
        layout.addWidget(self._glyph)

        # Scope title — slightly heavier for hierarchy.
        self._title = QLabel(variant.name)
        self._title.setObjectName("ScopeHeaderTitle")
        tf = QFont()
        tf.setPointSize(13)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        layout.addWidget(self._title)

        # Type badge — accent-tinted chip with UPPERCASE letter-spacing.
        self._badge = QLabel(variant.type_label.upper())
        self._badge.setObjectName("ScopeHeaderBadge")
        bf = QFont()
        bf.setPointSize(8)
        bf.setWeight(QFont.Weight.Bold)
        bf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        self._badge.setFont(bf)
        layout.addWidget(self._badge)

        layout.addStretch(1)

        # Version — small, monospace, muted.
        self._version = QLabel(f"v{version}" if version else "")
        self._version.setObjectName("ScopeHeaderVersion")
        vf = QFont()
        vf.setPointSize(9)
        vf.setFamilies(font_service.MONO_FAMILIES)
        self._version.setFont(vf)
        layout.addWidget(self._version)


# ── Menubar ────────────────────────────────────────────────────────────────


class _ScopeMenuBar(QMenuBar):
    """Standard menus shared by every scope variant.

    Variants extend menus with their own actions via the public
    ``file_menu`` / ``view_menu`` / … attributes; the shell only
    builds the empty structure.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeMenuBar")
        self.file_menu = self.addMenu("File")
        self.view_menu = self.addMenu("View")
        self.sim_menu = self.addMenu("Simulation")
        self.tools_menu = self.addMenu("Tools")
        self.window_menu = self.addMenu("Window")
        self.help_menu = self.addMenu("Help")


# ── Toolbar ─────────────────────────────────────────────────────────────────


class _ScopeToolbar(QFrame):
    """Top toolbar split into semantic groups separated by thin dividers.

    Each group exposes the buttons it owns publicly so capabilities can
    attach handlers without the shell knowing about them.
    """

    # Signals emitted by the standard buttons every scope shows; capabilities
    # connect to these to wire behaviour without subclassing the shell.
    run_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    fit_clicked = Signal()
    cursor_toggled = Signal(bool)
    grid_toggled = Signal(bool)
    sidebar_toggled = Signal(bool)
    inspector_toggled = Signal(bool)

    # Map (button_name → icon_key) so the variant can re-tint icons when
    # the active theme switches (capabilities call _retint_icons()).
    _ICON_MAP = {
        "run": "play",
        "pause": "pause",
        "stop": "stop",
        "sidebar": "panel-left",
        "inspector": "panel-right",
        "fit": "fit-view",
        "cursor": "crosshairs",
        "grid": "grid",
        "math": "math-function",
        "fft": "fft-chart",
        "export": "download",
    }

    def __init__(self, *, accent_color: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeToolbar")
        self.setFixedHeight(44)
        self._accent_color = accent_color or _DARK_FALLBACK["accent"]
        # Seed icon tone from the token-derived fallback; the shell
        # re-tints via ``retint_icons`` with the live palette right
        # after construction (and again on every theme change).
        self._icon_color = _DARK_FALLBACK["text_dim"]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(2)

        # Transport group — green/yellow/red accents.
        self.btn_run = self._mk_btn("run", "Run simulation (F5)", accent="success")
        self.btn_pause = self._mk_btn("pause", "Pause (F8)")
        self.btn_stop = self._mk_btn("stop", "Stop (Shift+F5)", accent="error")
        self.btn_run.clicked.connect(self.run_clicked)
        self.btn_pause.clicked.connect(self.pause_clicked)
        self.btn_stop.clicked.connect(self.stop_clicked)
        for b in (self.btn_run, self.btn_pause, self.btn_stop):
            layout.addWidget(b)

        layout.addWidget(self._mk_sep())

        # View group — sidebar/inspector toggles + fit.
        self.btn_sidebar = self._mk_btn("sidebar", "Toggle Signals panel (Ctrl+B)", checkable=True, checked=True)
        self.btn_inspector = self._mk_btn("inspector", "Toggle Inspector panel (Ctrl+I)", checkable=True, checked=True)
        self.btn_fit = self._mk_btn("fit", "Fit view to data (F)")
        self.btn_sidebar.toggled.connect(self.sidebar_toggled)
        self.btn_inspector.toggled.connect(self.inspector_toggled)
        self.btn_fit.clicked.connect(self.fit_clicked)
        for b in (self.btn_sidebar, self.btn_inspector, self.btn_fit):
            layout.addWidget(b)

        layout.addWidget(self._mk_sep())

        # Cursor / Grid group.
        self.btn_cursor = self._mk_btn("cursor", "Toggle cursors (C)", checkable=True)
        self.btn_grid = self._mk_btn("grid", "Toggle grid (G)", checkable=True, checked=True)
        self.btn_cursor.toggled.connect(self.cursor_toggled)
        self.btn_grid.toggled.connect(self.grid_toggled)
        for b in (self.btn_cursor, self.btn_grid):
            layout.addWidget(b)

        layout.addWidget(self._mk_sep())

        # Math / FFT / Export group — capabilities will hook here.
        self.btn_math = self._mk_btn("math", "Add math signal")
        self.btn_fft = self._mk_btn("fft", "Toggle FFT view", checkable=True)
        self.btn_export = self._mk_btn("export", "Export waveforms (CSV/PNG)")
        for b in (self.btn_math, self.btn_fft, self.btn_export):
            layout.addWidget(b)

        layout.addStretch(1)

        # Scope identity pill on the right (e.g. ``Scope1``).
        self.scope_pill = QLabel("Scope1")
        self.scope_pill.setObjectName("ScopeToolbarPill")
        self.scope_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scope_pill.setMinimumWidth(72)
        layout.addWidget(self.scope_pill)

    # ── helpers ────────────────────────────────────────────────────────────
    def _mk_btn(self, icon_key: str, tip: str, *, accent: str = "", checkable: bool = False, checked: bool = False) -> QToolButton:
        b = QToolButton()
        b.setObjectName("ScopeToolbarBtn")
        b.setToolTip(tip)
        b.setFixedSize(34, 32)
        b.setCheckable(checkable)
        if checkable:
            b.setChecked(checked)
        if accent:
            b.setProperty("accent", accent)
        # Resolve icon now — _ICON_MAP keys are passed in.
        icon_name = self._ICON_MAP.get(icon_key)
        if icon_name is not None:
            # Accent-tone icons (success/error) get their tone; the rest
            # use the neutral icon tone derived from the theme. These
            # seeds are replaced by the live palette via ``retint_icons``.
            tone = {
                "success": _DARK_FALLBACK["success"],
                "error":   _DARK_FALLBACK["error"],
            }.get(accent, self._icon_color)
            b.setIcon(IconService.get_icon(icon_name, tone, 18))
            b.setIconSize(QSize(18, 18))
            b.setProperty("iconKey", icon_key)
        return b

    def _mk_sep(self) -> QFrame:
        s = QFrame()
        s.setObjectName("ScopeToolbarSep")
        s.setFrameShape(QFrame.Shape.VLine)
        s.setFixedWidth(1)
        return s

    def retint_icons(self, neutral: str, success: str, error: str) -> None:
        """Re-render every toolbar icon with the new theme colours.

        Called from ``BaseScopeWindow._apply_palette`` on init AND on
        ``theme_changed`` so the toolbar flips between dark / light
        without requiring a window restart. ``neutral`` is the tone
        for the bulk of icons (sidebar / cursor / math / fft / etc.);
        success/error tint the transport buttons.
        """
        self._icon_color = neutral
        for btn in self.findChildren(QToolButton, "ScopeToolbarBtn"):
            icon_key = btn.property("iconKey")
            if not icon_key:
                continue
            icon_name = self._ICON_MAP.get(icon_key)
            if icon_name is None:
                continue
            accent = btn.property("accent") or ""
            tone = (
                success if accent == "success"
                else error if accent == "error"
                else neutral
            )
            btn.setIcon(IconService.get_icon(icon_name, tone, 18))


# ── Sidebar ────────────────────────────────────────────────────────────────


class _ScopeSidebar(QFrame):
    """Left sidebar — Signals / Saved Views. Collapses to an icon rail."""

    expanded_width = 240
    rail_width = 44

    collapsed = Signal(bool)  # True when collapsed to the rail

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeSidebar")
        self.setFixedWidth(self.expanded_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Header row with title + collapse button (right-aligned).
        head = QHBoxLayout()
        head.setSpacing(8)
        title = QLabel("Signals")
        title.setObjectName("ScopeSidebarTitle")
        tf = QFont()
        tf.setPointSize(12)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
        head.addWidget(title)
        head.addStretch(1)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setObjectName("ScopeSidebarCollapseBtn")
        self._collapse_btn.setIcon(
            IconService.get_icon("chevron-left", _DARK_FALLBACK["muted"], 14),
        )
        self._collapse_btn.setIconSize(QSize(14, 14))
        self._collapse_btn.setFixedSize(22, 22)
        self._collapse_btn.setToolTip("Collapse sidebar (Ctrl+B)")
        self._collapse_btn.clicked.connect(self.toggle_collapsed)
        head.addWidget(self._collapse_btn)
        layout.addLayout(head)

        # Signal-list placeholder with empty hint until capabilities
        # populate it. ``add_signal_row`` swaps the hint for actual rows.
        self.signal_list_host = QFrame()
        self.signal_list_host.setObjectName("ScopeSidebarListHost")
        self.signal_list_host.setMinimumHeight(180)
        self._signal_list_layout = QVBoxLayout(self.signal_list_host)
        self._signal_list_layout.setContentsMargins(10, 10, 10, 10)
        self._signal_list_layout.setSpacing(4)
        self._signal_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._signal_list_hint = QLabel(
            "No signals available yet.\nConnect probes to the scope on\nthe schematic, then click Run.",
        )
        self._signal_list_hint.setObjectName("ScopeSidebarHint")
        self._signal_list_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._signal_list_hint.setWordWrap(True)
        hf = QFont()
        hf.setPointSize(9)
        self._signal_list_hint.setFont(hf)
        self._signal_list_layout.addStretch(1)
        self._signal_list_layout.addWidget(self._signal_list_hint)
        self._signal_list_layout.addStretch(2)
        self._signal_rows: list[QWidget] = []
        layout.addWidget(self.signal_list_host, stretch=3)

        # Subtle divider between Signals and Saved Views sections.
        sep = QFrame()
        sep.setObjectName("ScopeSidebarSectionSep")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # Saved-views header row: title + "+" save button.
        sv_head = QHBoxLayout()
        sv_head.setSpacing(6)
        sv_title = QLabel("SAVED VIEWS")
        sv_title.setObjectName("ScopeSidebarSubTitle")
        sf = QFont()
        sf.setPointSize(8)
        sf.setWeight(QFont.Weight.Bold)
        sf.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        sv_title.setFont(sf)
        sv_head.addWidget(sv_title)
        sv_head.addStretch(1)
        # Save-current-view button — the shell wires its click to
        # ``BaseScopeWindow._save_current_view``.
        self.btn_save_view = QToolButton()
        self.btn_save_view.setObjectName("ScopeSidebarSaveBtn")
        self.btn_save_view.setText("+ Save")
        self.btn_save_view.setToolTip("Save current zoom + cursors as a named view")
        sbf = QFont()
        sbf.setPointSize(8)
        sbf.setWeight(QFont.Weight.DemiBold)
        self.btn_save_view.setFont(sbf)
        sv_head.addWidget(self.btn_save_view)
        layout.addLayout(sv_head)

        # Saved views container — empty-state hint until the first
        # view is captured, then rows replace it. 110 px gives a 2-line
        # hint room to breathe without being clipped (the previous
        # 56 px was squashed in the user's report).
        self.views_list_host = QFrame()
        self.views_list_host.setObjectName("ScopeSidebarViewsHost")
        self.views_list_host.setMinimumHeight(110)
        self._views_layout = QVBoxLayout(self.views_list_host)
        self._views_layout.setContentsMargins(10, 12, 10, 12)
        self._views_layout.setSpacing(4)
        self._views_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._views_hint = QLabel(
            "Click + Save above to\ncapture the current zoom\nand cursor positions."
        )
        self._views_hint.setObjectName("ScopeSidebarHint")
        self._views_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._views_hint.setWordWrap(True)
        self._views_hint.setFont(hf)
        self._views_layout.addWidget(self._views_hint)
        self._view_rows: list[QWidget] = []
        layout.addWidget(self.views_list_host, stretch=0)

        self._collapsed = False

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        # Resolve chevron tone from the parent BaseScopeWindow's palette
        # when available so the icon flips with the host theme.
        tone = self._chevron_tone()
        if self._collapsed:
            self.setFixedWidth(self.rail_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-right", tone, 14))
            self._collapse_btn.setToolTip("Expand sidebar (Ctrl+B)")
        else:
            self.setFixedWidth(self.expanded_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-left", tone, 14))
            self._collapse_btn.setToolTip("Collapse sidebar (Ctrl+B)")
        self.collapsed.emit(self._collapsed)

    def _chevron_tone(self) -> str:
        """Look up the current ``muted`` palette colour from the host shell.

        Falls back to the legacy dark-theme grey when the parent isn't
        a ``BaseScopeWindow`` (tests, ad-hoc embedding).
        """
        host = self.window()
        palette = getattr(host, "_palette", None)
        if isinstance(palette, dict) and "muted" in palette:
            return palette["muted"]
        return _DARK_FALLBACK["muted"]

    # ── Signal-row management ───────────────────────────────────────────
    def add_signal_row(self, name: str, color: str, *, unit: str = "") -> None:
        """Render one signal entry in the signal list (called by capabilities).

        Replaces the placeholder hint on first call so the list reads as
        a real channel list once probes are resolved.
        """
        # Tear down the placeholder layout the first time.
        if self._signal_list_hint is not None:
            self._signal_list_hint.setParent(None)
            self._signal_list_hint.deleteLater()
            self._signal_list_hint = None
            # Drop both stretch items the placeholder layout had added.
            while self._signal_list_layout.count():
                item = self._signal_list_layout.takeAt(0)
                w = item.widget() if item is not None else None
                if w is not None:
                    w.setParent(None)
                    w.deleteLater()

        row = QFrame()
        row.setObjectName("ScopeSidebarSignalRow")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 5, 8, 5)
        rl.setSpacing(8)
        # Color chip with subtle inner shadow for a more "chip" feel.
        chip = QLabel()
        chip.setFixedSize(10, 10)
        chip.setStyleSheet(
            f"background-color: {color}; border-radius: 5px; "
            f"border: 1px solid rgba(0,0,0,0.4);"
        )
        rl.addWidget(chip)
        # Name label takes available space, name is text-toned.
        label = QLabel(name)
        label.setObjectName("ScopeSidebarSignalName")
        lf = QFont()
        lf.setPointSize(10)
        label.setFont(lf)
        rl.addWidget(label, stretch=1)
        # Unit as a small right-aligned pill, only when known.
        if unit:
            unit_lbl = QLabel(unit)
            unit_lbl.setObjectName("ScopeSidebarSignalUnit")
            uf = QFont()
            uf.setPointSize(8)
            uf.setWeight(QFont.Weight.DemiBold)
            uf.setFamilies(font_service.MONO_FAMILIES)
            unit_lbl.setFont(uf)
            unit_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            unit_lbl.setMinimumWidth(22)
            rl.addWidget(unit_lbl)
        self._signal_list_layout.addWidget(row)
        self._signal_rows.append(row)

    # ── Saved-views row management ──────────────────────────────────────
    def add_view_row(self, name: str, on_restore, on_delete) -> None:
        """Render one saved-view entry with restore + delete actions.

        The two callables are wired without arguments — the host owns
        the captured state and decides what restore/delete mean.
        """
        if self._views_hint is not None:
            self._views_hint.setParent(None)
            self._views_hint.deleteLater()
            self._views_hint = None

        row = QFrame()
        row.setObjectName("ScopeSidebarViewRow")
        rl = QHBoxLayout(row)
        rl.setContentsMargins(8, 4, 4, 4)
        rl.setSpacing(6)
        label_btn = QPushButton(name)
        label_btn.setObjectName("ScopeSidebarViewName")
        label_btn.setFlat(True)
        label_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        lbf = QFont()
        lbf.setPointSize(10)
        label_btn.setFont(lbf)
        label_btn.clicked.connect(on_restore)
        rl.addWidget(label_btn, stretch=1)
        del_btn = QToolButton()
        del_btn.setObjectName("ScopeSidebarViewDelBtn")
        del_btn.setText("×")
        del_btn.setFixedSize(20, 20)
        del_btn.setToolTip(f"Delete view {name!r}")
        del_btn.clicked.connect(on_delete)
        rl.addWidget(del_btn)
        self._views_layout.addWidget(row)
        self._view_rows.append(row)

    def remove_view_row(self, index: int) -> None:
        if 0 <= index < len(self._view_rows):
            row = self._view_rows.pop(index)
            row.setParent(None)
            row.deleteLater()
            if not self._view_rows and self._views_hint is None:
                self._views_hint = QLabel(
                    "Capture the current zoom + cursors\nwith + Save.",
                )
                self._views_hint.setObjectName("ScopeSidebarHint")
                self._views_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._views_hint.setWordWrap(True)
                hf = QFont()
                hf.setPointSize(9)
                self._views_hint.setFont(hf)
                self._views_layout.addWidget(self._views_hint)

    def clear_signal_rows(self) -> None:
        """Drop every registered signal row and restore the empty-state hint."""
        for row in self._signal_rows:
            row.setParent(None)
            row.deleteLater()
        self._signal_rows.clear()
        if self._signal_list_hint is None:
            self._signal_list_hint = QLabel(
                "No signals available yet.\nConnect probes to the scope on\nthe schematic, then click Run.",
            )
            self._signal_list_hint.setObjectName("ScopeSidebarHint")
            self._signal_list_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._signal_list_hint.setWordWrap(True)
            hf = QFont()
            hf.setPointSize(9)
            self._signal_list_hint.setFont(hf)
            self._signal_list_layout.addStretch(1)
            self._signal_list_layout.addWidget(self._signal_list_hint)
            self._signal_list_layout.addStretch(2)


# ── Inspector ──────────────────────────────────────────────────────────────


class _ScopeInspector(QFrame):
    """Right panel — Cursors / Trigger / Measurements / Analysis groups."""

    # 296 px gives the Trigger combos breathing room for the longest
    # values ("Free Run", "rising", "(none)") plus the dropdown chevron
    # without the chevron crowding the value text. 240 clipped; 280
    # showed the value but the chevron sat on top of the last glyph;
    # 296 is the sweet spot.
    expanded_width = 296
    rail_width = 44

    collapsed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeInspector")
        self.setFixedWidth(self.expanded_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        # 16 px between Inspector group cards — gives Cursors and SMPS
        # Measure visible breathing room now that Trigger is hidden by
        # default. The previous 10 px crowded the cards.
        layout.setSpacing(16)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setObjectName("ScopeInspectorCollapseBtn")
        self._collapse_btn.setIcon(
            IconService.get_icon("chevron-right", _DARK_FALLBACK["muted"], 14),
        )
        self._collapse_btn.setIconSize(QSize(14, 14))
        self._collapse_btn.setFixedSize(22, 22)
        self._collapse_btn.setToolTip("Collapse inspector (Ctrl+I)")
        self._collapse_btn.clicked.connect(self.toggle_collapsed)
        head.addWidget(self._collapse_btn)
        title = QLabel("Inspector")
        title.setObjectName("ScopeInspectorTitle")
        tf = QFont()
        tf.setPointSize(12)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
        head.addWidget(title)
        head.addStretch(1)
        layout.addLayout(head)

        # Group placeholders — capabilities populate these on attach().
        self.cursor_group = self._mk_group(
            "Cursors",
            "Toggle from the toolbar to place A/B markers; ΔT, ΔY and 1/ΔT appear here.",
        )
        layout.addWidget(self.cursor_group)
        self.trigger_group = self._mk_group(
            "Trigger",
            "Free Run captures continuously. Single freezes when the chosen signal crosses the level.",
        )
        # Trigger group is hidden by default — re-shown only when a
        # TriggerCapability attaches and populates it. Keeps the
        # Inspector compact when the feature isn't in use.
        self.trigger_group.hide()
        layout.addWidget(self.trigger_group)
        self.smps_group = self._mk_group(
            "SMPS Measure",
            "Tsw / Duty / Ripple macros on the visible window. Choose a source after the first run.",
        )
        layout.addWidget(self.smps_group)
        layout.addStretch(1)

        self._collapsed = False

    def _mk_group(self, title: str, hint: str) -> QFrame:
        box = QFrame()
        box.setObjectName("ScopeInspectorGroup")
        v = QVBoxLayout(box)
        v.setContentsMargins(12, 10, 12, 12)
        v.setSpacing(8)
        # Section header — UPPERCASE with letter-spacing for clear
        # section affordance + slightly bolder weight.
        lbl = QLabel(title.upper())
        lbl.setObjectName("ScopeInspectorGroupTitle")
        f = QFont()
        f.setPointSize(8)
        f.setWeight(QFont.Weight.Bold)
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.8)
        lbl.setFont(f)
        v.addWidget(lbl)
        hint_label = QLabel(hint)
        hint_label.setObjectName("ScopeInspectorGroupHint")
        hint_label.setWordWrap(True)
        hf = QFont()
        hf.setPointSize(9)
        hint_label.setFont(hf)
        v.addWidget(hint_label)
        return box

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        tone = self._chevron_tone()
        if self._collapsed:
            self.setFixedWidth(self.rail_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-left", tone, 14))
        else:
            self.setFixedWidth(self.expanded_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-right", tone, 14))
        self.collapsed.emit(self._collapsed)

    def _chevron_tone(self) -> str:
        """Look up the current ``muted`` palette colour from the host shell."""
        host = self.window()
        palette = getattr(host, "_palette", None)
        if isinstance(palette, dict) and "muted" in palette:
            return palette["muted"]
        return _DARK_FALLBACK["muted"]


# ── Plot canvas (skeleton — capabilities/variants populate panes) ──────────


class _PlotPaneStack(QFrame):
    """Stacked plot canvas placeholder. Real panes are added later.

    For now renders a dark surface with grid hint + "No signals yet"
    message so the empty-state reads correctly before any capability
    has had a chance to populate panes.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopePlotCanvas")
        self.setMinimumHeight(280)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Empty-state label rendered on top of the dark surface.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label = QLabel("No signals yet")
        self._empty_label.setObjectName("ScopeEmptyTitle")
        f = QFont()
        f.setPointSize(13)
        f.setWeight(QFont.Weight.DemiBold)
        self._empty_label.setFont(f)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)
        self._empty_hint = QLabel(
            "Drop a signal here from the sidebar, or click Run to start streaming."
        )
        self._empty_hint.setObjectName("ScopeEmptyHint")
        fh = QFont()
        fh.setPointSize(10)
        self._empty_hint.setFont(fh)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_hint)

    def _grid_tone(self) -> str:
        """Current ``plot_grid`` colour from the host shell's live palette.

        Falls back to the token-derived dark palette when the parent
        isn't a ``BaseScopeWindow`` (tests, ad-hoc embedding) — same
        pattern as the sidebar/inspector chevron tone lookup. Without
        this, the empty-state grid hint would stay locked to the dark
        fallback after a live theme switch.
        """
        host = self.window()
        palette = getattr(host, "_palette", None)
        if isinstance(palette, dict) and "plot_grid" in palette:
            return palette["plot_grid"]
        return _DARK_FALLBACK["plot_grid"]

    def paintEvent(self, event):  # noqa: D401 - Qt override
        super().paintEvent(event)
        # Subtle grid hint behind the empty-state label so the surface
        # reads as a plot area, not just a blank rectangle.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(QColor(self._grid_tone()))
        pen.setWidth(1)
        painter.setPen(pen)
        step = 32
        w, h = self.width(), self.height()
        for x in range(step, w, step):
            painter.drawLine(x, 0, x, h)
        for y in range(step, h, step):
            painter.drawLine(0, y, w, y)
        painter.end()


# ── Bottom drawer ──────────────────────────────────────────────────────────


class _ScopeDrawer(QFrame):
    """Bottom drawer — collapses to a single-line summary by default.

    Expanded, it reveals ``extra_host``: a vertical area capabilities can
    drop widgets into (e.g. the measurement table).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeDrawer")
        self.setFixedHeight(32)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        summary_row = QWidget(self)
        summary_row.setFixedHeight(32)
        layout = QHBoxLayout(summary_row)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)
        outer.addWidget(summary_row)

        # Status dot — capabilities can flip its colour to signal Idle /
        # Running / Completed / Warning by toggling the ``state`` property
        # then re-polishing.
        self.status_dot = QLabel("●")
        self.status_dot.setObjectName("ScopeDrawerStatusDot")
        self.status_dot.setProperty("state", "idle")
        df = QFont()
        df.setPointSize(11)
        self.status_dot.setFont(df)
        layout.addWidget(self.status_dot)

        # Summary text. Capabilities replace this string as they go.
        self.summary = QLabel("Idle — no data captured yet.")
        self.summary.setObjectName("ScopeDrawerSummary")
        f = QFont()
        f.setPointSize(10)
        self.summary.setFont(f)
        layout.addWidget(self.summary)

        layout.addStretch(1)

        self.expand_btn = QPushButton("Expand")
        self.expand_btn.setObjectName("ScopeDrawerExpandBtn")
        self.expand_btn.setFlat(True)
        self.expand_btn.setFixedHeight(22)
        layout.addWidget(self.expand_btn)

        # Capability host — hidden while collapsed.
        self.extra_host = QWidget(self)
        self.extra_layout = QVBoxLayout(self.extra_host)
        self.extra_layout.setContentsMargins(14, 0, 14, 6)
        self.extra_layout.setSpacing(4)
        self.extra_host.setVisible(False)
        outer.addWidget(self.extra_host, 1)


# ── Timeline + actions ─────────────────────────────────────────────────────


class _ScopeTimelineBar(QFrame):
    """Bottom-most row — timeline scrubber + Fit / Range / Measure buttons."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeTimelineBar")
        self.setFixedHeight(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # Zoom out / Pan left / scrubber / Pan right / Zoom in.
        self.btn_zoom_out = QToolButton()
        self.btn_zoom_out.setObjectName("ScopeTimelineStepBtn")
        self.btn_zoom_out.setText("−")
        self.btn_zoom_out.setFixedSize(26, 24)
        self.btn_zoom_out.setToolTip("Zoom out (2× wider window)")
        zf = QFont()
        zf.setPointSize(14)
        zf.setWeight(QFont.Weight.DemiBold)
        self.btn_zoom_out.setFont(zf)
        layout.addWidget(self.btn_zoom_out)

        self.btn_pan_left = QToolButton()
        self.btn_pan_left.setObjectName("ScopeTimelineStepBtn")
        self.btn_pan_left.setIcon(
            IconService.get_icon("chevron-left", _DARK_FALLBACK["muted"], 14),
        )
        self.btn_pan_left.setIconSize(QSize(14, 14))
        self.btn_pan_left.setFixedSize(26, 24)
        self.btn_pan_left.setToolTip("Pan left")
        layout.addWidget(self.btn_pan_left)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("ScopeTimelineSlider")
        self.slider.setRange(0, 1000)
        self.slider.setValue(1000)
        layout.addWidget(self.slider, stretch=4)

        self.btn_pan_right = QToolButton()
        self.btn_pan_right.setObjectName("ScopeTimelineStepBtn")
        self.btn_pan_right.setIcon(
            IconService.get_icon("chevron-right", _DARK_FALLBACK["muted"], 14),
        )
        self.btn_pan_right.setIconSize(QSize(14, 14))
        self.btn_pan_right.setFixedSize(26, 24)
        self.btn_pan_right.setToolTip("Pan right")
        layout.addWidget(self.btn_pan_right)

        self.btn_zoom_in = QToolButton()
        self.btn_zoom_in.setObjectName("ScopeTimelineStepBtn")
        self.btn_zoom_in.setText("+")
        self.btn_zoom_in.setFixedSize(26, 24)
        self.btn_zoom_in.setToolTip("Zoom in (½ window)")
        self.btn_zoom_in.setFont(zf)
        layout.addWidget(self.btn_zoom_in)

        # Range readout.
        self.range_label = QLabel("— to —")
        self.range_label.setObjectName("ScopeTimelineRange")
        rf = QFont()
        rf.setPointSize(10)
        self.range_label.setFont(rf)
        self.range_label.setMinimumWidth(110)
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.range_label)

        # Fit / Range combo / Measure.
        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setObjectName("ScopeTimelineActionBtn")
        self.fit_btn.setFixedHeight(24)
        layout.addWidget(self.fit_btn)

        self.range_combo = QComboBox()
        self.range_combo.setObjectName("ScopeTimelineRangeCombo")
        self.range_combo.addItem("Full Range", "full")
        self.range_combo.addItem("Visible Window", "window")
        self.range_combo.addItem("Between Cursors", "a_to_b")
        layout.addWidget(self.range_combo)

        self.measure_btn = QPushButton("+ Measure")
        self.measure_btn.setObjectName("ScopeTimelineActionBtn")
        self.measure_btn.setFixedHeight(24)
        layout.addWidget(self.measure_btn)


# ── The shell itself ───────────────────────────────────────────────────────


class BaseScopeWindow(QWidget):
    """PLECS-style scope window — shell that hosts capabilities.

    Parameters
    ----------
    variant
        Describes which scope flavour this window is (electrical /
        thermal / …). Drives the header glyph + badge + accent.
    capabilities
        Modules attached during construction. The shell calls
        ``capability.attach(self)`` once after the chrome is built.
    version
        Optional ``"0.12.0a9"`` style string shown in the header.
    parent
        Standard Qt parent.
    """

    closed = Signal()

    def __init__(
        self,
        *,
        variant: ScopeVariant,
        capabilities: list[ScopeCapability] | None = None,
        version: str = "",
        theme_service=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BaseScopeWindow")
        self.setWindowTitle(variant.name)
        self.setMinimumSize(960, 600)
        self.resize(1280, 800)

        self._variant = variant
        self._capabilities: list[ScopeCapability] = []

        # ── Theme wiring ────────────────────────────────────────────────
        # When the host (MainWindow) passes its ``theme_service``, the
        # scope inherits the app's current theme AND subscribes to the
        # ``theme_changed`` signal so it re-renders dark / light in
        # lock-step with the rest of the app. Without a theme service
        # (tests, headless renders, ad-hoc embedding) we fall back to
        # the legacy hard-coded dark palette.
        self._theme_service = theme_service
        if theme_service is not None and hasattr(theme_service, "current_theme"):
            self._palette = _palette_from_theme(theme_service.current_theme)
        else:
            self._palette = dict(_DARK_FALLBACK)
        # ``_re_theme`` is called both on ``__init__`` and whenever the
        # service fires ``theme_changed``. Keep it bound now so the
        # later connect just hooks the existing callable.
        if (
            theme_service is not None
            and hasattr(theme_service, "theme_changed")
        ):
            theme_service.theme_changed.connect(self._on_theme_changed)

        # ── Build chrome ────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.header = _ScopeHeader(variant=variant, version=version)
        root.addWidget(self.header)

        self.menubar = _ScopeMenuBar(self)
        root.addWidget(self.menubar)

        self.toolbar = _ScopeToolbar(accent_color=variant.accent_color, parent=self)
        root.addWidget(self.toolbar)

        # ── Body: sidebar | plot | inspector ────────────────────────────
        body = QSplitter(Qt.Orientation.Horizontal, self)
        body.setObjectName("ScopeBodySplitter")
        body.setChildrenCollapsible(False)
        body.setHandleWidth(1)
        # NoFrame: QSplitter inherits from QFrame and otherwise reserves
        # ~1 px of frame border on each side — that gap let the macOS
        # aqua style draw native scrollbar / chevron shadows past the
        # inspector's right edge, which the user saw as ghost-text frags.
        body.setFrameShape(QFrame.Shape.NoFrame)
        body.setContentsMargins(0, 0, 0, 0)

        self.sidebar = _ScopeSidebar(self)
        body.addWidget(self.sidebar)

        self.plot_canvas = PlotCanvas(accent_color=variant.accent_color, parent=self)
        body.addWidget(self.plot_canvas)

        self.inspector = _ScopeInspector(self)
        # Make the inspector swallow any child overflow with a styled
        # background that paints to its full rect — ensures children
        # (combos / spinboxes with native shadows) can't bleed past.
        self.inspector.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        body.addWidget(self.inspector)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        root.addWidget(body, stretch=1)
        # Pin the splitter's initial sizes to the SAME fixed widths the
        # sidebar / inspector use. Without this, QSplitter computes
        # sizeHint-based slots that can be larger than the children's
        # setFixedWidth — leaving a few px of dead space on the right
        # of the inspector (the user's "espaco vazio depois do
        # inspetor" report). The plot gets a sentinel large size so it
        # absorbs the remainder.
        body.setSizes([
            self.sidebar.expanded_width,
            10_000,
            self.inspector.expanded_width,
        ])

        # ── Drawer + timeline ───────────────────────────────────────────
        self.drawer = _ScopeDrawer(self)
        root.addWidget(self.drawer)
        self.timeline = _ScopeTimelineBar(self)
        root.addWidget(self.timeline)

        # ── Wire toolbar toggles to the panel collapse buttons ──────────
        self.toolbar.sidebar_toggled.connect(self._on_sidebar_toggle)
        self.toolbar.inspector_toggled.connect(self._on_inspector_toggle)
        # Fit: rescale every panel's X + Y to fit all data with the
        # standard pyqtgraph 5% padding. Wired both on the main
        # toolbar ⬜ button AND the bottom timeline "Fit" button.
        self.toolbar.fit_clicked.connect(self._on_fit_to_data)
        self.timeline.fit_btn.clicked.connect(self._on_fit_to_data)
        # Timeline navigation: zoom / pan / scrub / range-mode / measure.
        self.timeline.btn_zoom_out.clicked.connect(
            lambda: self._timeline_zoom(2.0),
        )
        self.timeline.btn_zoom_in.clicked.connect(
            lambda: self._timeline_zoom(0.5),
        )
        self.timeline.btn_pan_left.clicked.connect(
            lambda: self._timeline_pan(-0.10),
        )
        self.timeline.btn_pan_right.clicked.connect(
            lambda: self._timeline_pan(+0.10),
        )
        self.timeline.slider.valueChanged.connect(self._timeline_slider_moved)
        self.timeline.range_combo.currentIndexChanged.connect(
            self._timeline_range_mode_changed,
        )
        self.timeline.measure_btn.clicked.connect(self._timeline_add_measure)
        # Toolbar grid + pause that nobody was listening to.
        self.toolbar.grid_toggled.connect(self._on_grid_toggled)
        self.toolbar.pause_clicked.connect(self._on_pause_clicked)
        # Drawer Expand toggles the drawer height between collapsed and
        # an extended row for the long status / matched-keys text.
        self.drawer.expand_btn.clicked.connect(self._on_drawer_expand_toggled)
        self._drawer_expanded = False
        # Subscribe to the plot's first panel's range changes so the
        # bottom timeline label + slider stay in sync when the user
        # zooms / pans via the mouse.
        self._timeline_syncing = False
        self._wire_plot_range_sync()
        # Saved views: + Save button in the sidebar captures the
        # current X/Y range per panel. In-memory only for now —
        # project-level persistence is a follow-up.
        self.sidebar.btn_save_view.clicked.connect(self._save_current_view)
        self._saved_views: list[dict] = []

        # ── Theme ───────────────────────────────────────────────────────
        # Two layers of theming, both required:
        #   1. QPalette — catches every "default" Qt widget so even
        #      QSpinBox / QLineEdit / QToolTip inside capabilities have
        #      dark colours without explicit QSS.
        #   2. QSS — adds the polish (rounded borders, chevrons, accent
        #      hovers) on top of the palette.
        # Fusion style is applied per-widget in ``_normalize_form_widgets``
        # below; setStyle on the window itself segfaults in test runs.
        self._apply_palette()
        self._apply_stylesheet()
        for cap in capabilities or []:
            self.attach_capability(cap)
        # After capabilities have created their widgets, normalize
        # every form widget to use the Fusion style + a QListView
        # popup. macOS's native QStyle ignores QSS ``color:`` on
        # QComboBox text — Fusion respects QSS fully on every
        # platform, which is the only way to get a consistent dark
        # look without painting widgets by hand.
        self._normalize_form_widgets()
        # Re-tint chrome icons (toolbar + sidebar/inspector chevrons +
        # timeline pan arrows) with the current palette so they read
        # correctly on BOTH light and dark themes. The IconService
        # bakes colour into the QIcon at creation time, so the icons
        # would otherwise stay forever-grey from their dark-fallback
        # construction seeds — invisible on light bg.
        self._retint_chrome_icons()

    # ── Capability lifecycle ────────────────────────────────────────────

    def attach_capability(self, capability: ScopeCapability) -> None:
        """Register a capability with the shell. Idempotent per instance."""
        if capability in self._capabilities:
            return
        capability.attach(self)
        self._capabilities.append(capability)

    # ── Fit-to-data helper ──────────────────────────────────────────────

    def _on_fit_to_data(self) -> None:
        """Auto-range every panel's X *and* Y axis to fit the data.

        Without this the user had no one-click way to recover a useful
        view after zooming/panning — pyqtgraph's default mouse menu is
        disabled in the shell. The Y-side is the important bit: when
        Vsw shows a 12 V envelope but Vout sits at 7 V on the same
        panel, the initial Y range can clip Vout entirely.

        ``autoRange()`` computes the new range from current data once
        and SETS it (without keeping auto-range latched on), so the
        user's next manual zoom/pan sticks.
        """
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        for plot in panels.values():
            try:
                plot.getViewBox().autoRange(padding=0.05)
            except Exception:  # noqa: BLE001 — defensive
                try:
                    plot.autoRange()
                except Exception:  # noqa: BLE001
                    pass

    # ── Timeline navigation ─────────────────────────────────────────────

    def _first_panel(self):
        """Return the first plot panel, or None when nothing's wired."""
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        return next(iter(panels.values()), None) if panels else None

    def _data_x_extent(self) -> tuple[float, float] | None:
        """Return ``(t_min, t_max)`` across every signal cached on the canvas.

        Used by the slider + Full Range / range readout — gives us a
        deterministic global range regardless of current zoom level.
        """
        signals = getattr(self.plot_canvas, "_signals", {})  # noqa: SLF001
        if not signals:
            return None
        t_lo, t_hi = float("inf"), float("-inf")
        for state in signals.values():
            try:
                t_arr, _ = state.merged()
            except Exception:  # noqa: BLE001
                continue
            if t_arr.size == 0:
                continue
            t_lo = min(t_lo, float(t_arr[0]))
            t_hi = max(t_hi, float(t_arr[-1]))
        if t_lo == float("inf") or t_hi == float("-inf") or t_hi <= t_lo:
            return None
        return (t_lo, t_hi)

    def _timeline_zoom(self, factor: float) -> None:
        """Zoom X around the current view's centre.

        ``factor < 1`` zooms in (window shrinks), ``factor > 1`` zooms
        out. We anchor on the current centre so the user's focus point
        stays put across zoom steps.
        """
        panel = self._first_panel()
        if panel is None:
            return
        x_range, _ = panel.viewRange()
        lo, hi = float(x_range[0]), float(x_range[1])
        span = hi - lo
        if span <= 0:
            return
        centre = (lo + hi) / 2.0
        new_half = (span * factor) / 2.0
        new_lo, new_hi = centre - new_half, centre + new_half
        # Clamp to data extent on zoom out so we don't show empty space.
        ext = self._data_x_extent()
        if ext is not None and factor > 1.0:
            t_min, t_max = ext
            if new_lo < t_min:
                new_lo = t_min
            if new_hi > t_max:
                new_hi = t_max
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        for plot in panels.values():
            plot.setXRange(new_lo, new_hi, padding=0)

    def _timeline_pan(self, delta_frac: float) -> None:
        """Shift the X view window left (negative) or right (positive)
        by ``delta_frac`` of the current visible span.
        """
        panel = self._first_panel()
        if panel is None:
            return
        x_range, _ = panel.viewRange()
        span = float(x_range[1]) - float(x_range[0])
        if span <= 0:
            return
        shift = span * delta_frac
        new_lo = float(x_range[0]) + shift
        new_hi = float(x_range[1]) + shift
        # Clamp to data extent if known so we don't pan off into empty.
        ext = self._data_x_extent()
        if ext is not None:
            t_min, t_max = ext
            if new_lo < t_min:
                new_lo, new_hi = t_min, t_min + span
            if new_hi > t_max:
                new_hi, new_lo = t_max, t_max - span
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        for plot in panels.values():
            plot.setXRange(new_lo, new_hi, padding=0)

    def _timeline_slider_moved(self, value: int) -> None:
        """Slider scrubs the visible window across the data extent.

        ``value`` is 0..1000 (set in ``_ScopeTimelineBar.__init__``).
        Position 0 = window starts at data t_min; position 1000 =
        window ends at data t_max. We keep the current visible
        span and just slide it. Skips work when the change came
        from our own range-sync handler (avoids feedback loops).
        """
        if self._timeline_syncing:
            return
        panel = self._first_panel()
        ext = self._data_x_extent()
        if panel is None or ext is None:
            return
        t_min, t_max = ext
        x_range, _ = panel.viewRange()
        span = float(x_range[1]) - float(x_range[0])
        if span <= 0 or span >= (t_max - t_min):
            return
        # ``value`` 0..1000 → fraction 0..1 of the slack space
        # ``(t_max - t_min - span)``.
        slack = (t_max - t_min) - span
        frac = max(0.0, min(1.0, value / 1000.0))
        new_lo = t_min + slack * frac
        new_hi = new_lo + span
        self._timeline_syncing = True
        try:
            panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
            for plot in panels.values():
                plot.setXRange(new_lo, new_hi, padding=0)
        finally:
            self._timeline_syncing = False

    def _timeline_range_mode_changed(self, index: int) -> None:
        """Range combo: Full Range / Visible Window / Between Cursors.

        - Full Range  : zoom out to the entire data extent.
        - Visible Window : keep current view (no-op).
        - Between Cursors: zoom to A/B cursor positions when CursorsCapability
          has them active.
        """
        if index < 0:
            return
        mode = self.timeline.range_combo.itemData(index)
        if mode == "full":
            ext = self._data_x_extent()
            if ext is not None:
                panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
                for plot in panels.values():
                    plot.setXRange(ext[0], ext[1], padding=0.02)
        elif mode == "a_to_b":
            for cap in self._capabilities:
                if cap.__class__.__name__ != "CursorsCapability":
                    continue
                a = getattr(cap, "_a", None)  # noqa: SLF001
                b = getattr(cap, "_b", None)  # noqa: SLF001
                if a is None or b is None:
                    return
                lo, hi = sorted([float(a.position), float(b.position)])
                if hi <= lo:
                    return
                panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
                for plot in panels.values():
                    plot.setXRange(lo, hi, padding=0.05)
                return

    def _timeline_add_measure(self) -> None:
        """``+ Measure`` — delegate to the measurements capability when one
        registered itself (``self.measure_handler``); otherwise keep the old
        drawer hint so the click reads as acknowledged."""
        handler = getattr(self, "measure_handler", None)
        if callable(handler):
            handler()
            return
        self.set_drawer_status(
            "idle",
            "Measure: use SMPS panel (Tsw + Fsw / Duty / Ripple) — "
            "general-purpose measurements coming soon.",
        )

    def _wire_plot_range_sync(self) -> None:
        """Hook the first panel's range-changed signal so the slider +
        range label follow the user's mouse-pan / mouse-zoom.
        """
        panel = self._first_panel()
        if panel is None:
            return
        try:
            panel.sigRangeChanged.connect(self._on_plot_range_changed)
        except Exception:  # noqa: BLE001 — pyqtgraph signal absent in some test paths
            pass

    @staticmethod
    def _fmt_time_eng(value: float) -> str:
        """Format a time value with the smallest engineering prefix.

        Used by the timeline range readout so ``"0.0023 to 0.0037"``
        becomes ``"2.3 ms to 3.7 ms"``.
        """
        av = abs(value)
        if av == 0.0:
            return "0 s"
        if av >= 1.0:
            return f"{value:.4g} s"
        if av >= 1e-3:
            return f"{value * 1e3:.4g} ms"
        if av >= 1e-6:
            return f"{value * 1e6:.4g} µs"
        return f"{value * 1e9:.4g} ns"

    def _on_plot_range_changed(self, *_args) -> None:
        """Refresh the slider position + range readout from the active view."""
        if self._timeline_syncing:
            return
        panel = self._first_panel()
        ext = self._data_x_extent()
        if panel is None:
            return
        x_range, _ = panel.viewRange()
        lo, hi = float(x_range[0]), float(x_range[1])
        self.timeline.range_label.setText(
            f"{self._fmt_time_eng(lo)} to {self._fmt_time_eng(hi)}"
        )
        # Slide the scrubber to match — but only when we know the
        # full data extent.
        if ext is not None:
            t_min, t_max = ext
            span = hi - lo
            slack = (t_max - t_min) - span
            if slack > 0:
                frac = max(0.0, min(1.0, (lo - t_min) / slack))
                self._timeline_syncing = True
                try:
                    self.timeline.slider.setValue(int(round(frac * 1000)))
                finally:
                    self._timeline_syncing = False

    # ── Toolbar handlers that were unwired ─────────────────────────────

    def _on_grid_toggled(self, show: bool) -> None:
        """Show / hide the pyqtgraph grid on every panel."""
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        for plot in panels.values():
            try:
                plot.showGrid(x=show, y=show, alpha=0.18 if show else 0.0)
            except Exception:  # noqa: BLE001
                pass

    def _on_pause_clicked(self) -> None:
        """Pause the simulation if the host service supports it."""
        # Pause behaviour is service-driven; LiveStreamCapability holds
        # the service ref. Reach for it through the capability list.
        for cap in self._capabilities:
            svc = getattr(cap, "_simulation_service", None)
            if svc is None:
                continue
            pause = getattr(svc, "pause", None) or getattr(svc, "toggle_pause", None)
            if callable(pause):
                pause()
                return

    def _on_drawer_expand_toggled(self) -> None:
        """Toggle the drawer between collapsed (32 px) and expanded (140 px).

        When expanded, the same single-line summary stays at top but
        the user has room for capabilities to drop additional text /
        legends in the future. For now the height bump alone gives
        the long backend-keys message room to wrap.
        """
        self._drawer_expanded = not self._drawer_expanded
        # A bit more room when a capability dropped widgets into the host
        # (e.g. the measurement table).
        has_extra = self.drawer.extra_layout.count() > 0
        new_h = (220 if has_extra else 140) if self._drawer_expanded else 32
        self.drawer.setFixedHeight(new_h)
        self.drawer.extra_host.setVisible(self._drawer_expanded)
        self.drawer.expand_btn.setText(
            "Collapse" if self._drawer_expanded else "Expand"
        )

    # ── Saved views ─────────────────────────────────────────────────────

    def _save_current_view(self) -> None:
        """Snapshot every panel's X/Y range and add it to the sidebar.

        Naming auto-increments (``View 1``, ``View 2``, …). Could grow
        a prompt dialog later; the auto-name keeps the click cheap.
        """
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        if not panels:
            return
        snapshot = {
            "ranges": {},
            "cursors": None,
        }
        for panel_name, plot in panels.items():
            try:
                x_range, y_range = plot.viewRange()
                snapshot["ranges"][panel_name] = (
                    [float(x_range[0]), float(x_range[1])],
                    [float(y_range[0]), float(y_range[1])],
                )
            except Exception:  # noqa: BLE001 — defensive
                continue
        if not snapshot["ranges"]:
            return

        # If a CursorsCapability is attached, capture its A/B positions
        # so restore puts the cursors back where the user had them.
        for cap in self._capabilities:
            if cap.__class__.__name__ == "CursorsCapability":
                a = getattr(cap, "_a", None)  # noqa: SLF001
                b = getattr(cap, "_b", None)  # noqa: SLF001
                if a is not None and b is not None:
                    snapshot["cursors"] = (
                        float(a.position), float(b.position),
                    )
                break

        name = f"View {len(self._saved_views) + 1}"
        idx = len(self._saved_views)
        self._saved_views.append(snapshot)
        self.sidebar.add_view_row(
            name,
            on_restore=lambda i=idx: self._restore_view(i),
            on_delete=lambda i=idx: self._delete_view(i),
        )

    def _restore_view(self, index: int) -> None:
        if not (0 <= index < len(self._saved_views)):
            return
        snapshot = self._saved_views[index]
        panels = getattr(self.plot_canvas, "_panels", {})  # noqa: SLF001
        for panel_name, (x_range, y_range) in snapshot["ranges"].items():
            plot = panels.get(panel_name)
            if plot is None:
                continue
            try:
                plot.setXRange(*x_range, padding=0)
                plot.setYRange(*y_range, padding=0)
            except Exception:  # noqa: BLE001
                pass
        # Restore cursor positions if we captured them.
        cursors = snapshot.get("cursors")
        if cursors is not None:
            for cap in self._capabilities:
                if cap.__class__.__name__ == "CursorsCapability":
                    a, b = cursors
                    a_state = getattr(cap, "_a", None)  # noqa: SLF001
                    b_state = getattr(cap, "_b", None)  # noqa: SLF001
                    if a_state is not None:
                        a_state.position = a
                        for ln in a_state.lines:
                            ln.setValue(a)
                    if b_state is not None:
                        b_state.position = b
                        for ln in b_state.lines:
                            ln.setValue(b)
                    update = getattr(cap, "_update_readouts", None)  # noqa: SLF001
                    if callable(update):
                        update()
                    break

    def _delete_view(self, index: int) -> None:
        if not (0 <= index < len(self._saved_views)):
            return
        self._saved_views.pop(index)
        # Full rebuild of sidebar rows — indices into the captured
        # closures shifted so we wire fresh callbacks. If the list is
        # now empty, ``remove_view_row(0)`` is responsible for restoring
        # the empty-state hint (it no-ops when the row doesn't exist).
        for row in list(self.sidebar._view_rows):  # noqa: SLF001
            row.setParent(None)
            row.deleteLater()
        self.sidebar._view_rows.clear()  # noqa: SLF001
        if not self._saved_views:
            # Reinstate the empty-state hint manually since
            # ``remove_view_row`` only restores it when called from
            # within itself.
            if getattr(self.sidebar, "_views_hint", None) is None:
                hint = QLabel(
                    "Capture the current zoom + cursors\nwith + Save.",
                )
                hint.setObjectName("ScopeSidebarHint")
                hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
                hint.setWordWrap(True)
                hf = QFont()
                hf.setPointSize(9)
                hint.setFont(hf)
                self.sidebar._views_layout.addWidget(hint)  # noqa: SLF001
                self.sidebar._views_hint = hint  # noqa: SLF001
            return
        for i, _snap in enumerate(self._saved_views):
            self.sidebar.add_view_row(
                f"View {i + 1}",
                on_restore=lambda i=i: self._restore_view(i),
                on_delete=lambda i=i: self._delete_view(i),
            )

    # ── Drawer status helper ────────────────────────────────────────────

    def set_drawer_status(self, state: str, summary: str) -> None:
        """Update the drawer's coloured status dot + summary text.

        ``state`` is one of ``idle`` / ``running`` / ``success`` /
        ``warning`` / ``error``; the stylesheet picks the dot colour
        from that property. Capabilities call this instead of poking
        ``drawer.summary`` directly so the colour stays in sync.
        """
        dot = getattr(self.drawer, "status_dot", None)
        if dot is not None:
            dot.setProperty("state", state)
            # Property changes don't auto-restyle — repolish to pick up
            # the new ``QLabel[state="…"]`` selector.
            dot.style().unpolish(dot)
            dot.style().polish(dot)
        if hasattr(self.drawer, "summary"):
            self.drawer.summary.setText(summary)

    # ── Panel toggles ───────────────────────────────────────────────────

    def _on_sidebar_toggle(self, visible: bool) -> None:
        # The toolbar button is the source of truth for "should sidebar
        # be visible". The sidebar's own collapse button can also fire
        # the sidebar's own ``collapsed`` signal but it stays in sync
        # because both routes call ``setFixedWidth``.
        if visible and self.sidebar._collapsed:
            self.sidebar.toggle_collapsed()
        elif not visible and not self.sidebar._collapsed:
            self.sidebar.toggle_collapsed()

    def _on_inspector_toggle(self, visible: bool) -> None:
        if visible and self.inspector._collapsed:
            self.inspector.toggle_collapsed()
        elif not visible and not self.inspector._collapsed:
            self.inspector.toggle_collapsed()

    # ── Lifecycle ────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:  # noqa: D401 - Qt override
        self.closed.emit()
        super().closeEvent(event)

    # ── Theme (host-driven, follows MainWindow's ThemeService) ──────────

    def _on_theme_changed(self, theme) -> None:
        """Re-derive the palette + restyle on host theme switch.

        Triggered by ``ThemeService.theme_changed``. Re-renders palette,
        stylesheet, re-normalises form widgets, and re-tints icons so
        the toolbar / sidebar / inspector / timeline chevrons flip
        dark↔light in lock-step with the rest of the app.
        """
        try:
            self._palette = _palette_from_theme(theme)
        except Exception:  # noqa: BLE001 — bad theme schema → keep current
            return
        self._apply_palette()
        self._apply_stylesheet()
        self._normalize_form_widgets()
        self._retint_chrome_icons()

    def _retint_chrome_icons(self) -> None:
        """Refresh every icon on the scope chrome with current palette colours.

        Icons are baked at construction with the dark-fallback tones
        (fine on dark, white-on-white in light mode). Here they pick up
        ``palette["text_dim"]`` / ``muted`` / accent so contrast is
        correct on both themes.
        """
        p = self._palette
        neutral = p["text_dim"]
        muted = p["muted"]
        accent = self._variant.accent_color or p["accent"]
        # Toolbar buttons.
        self.toolbar.retint_icons(
            neutral=neutral,
            success=p["success"],
            error=p["error"],
        )
        # Sidebar collapse chevron.
        sb = self.sidebar
        if hasattr(sb, "_collapse_btn"):
            icon = "chevron-left" if not sb._collapsed else "chevron-right"  # noqa: SLF001
            sb._collapse_btn.setIcon(IconService.get_icon(icon, muted, 14))  # noqa: SLF001
        # Inspector collapse chevron.
        ins = self.inspector
        if hasattr(ins, "_collapse_btn"):
            icon = "chevron-right" if not ins._collapsed else "chevron-left"  # noqa: SLF001
            ins._collapse_btn.setIcon(IconService.get_icon(icon, muted, 14))  # noqa: SLF001
        # Timeline pan buttons (zoom buttons are text-based — pick up
        # palette automatically via QSS).
        self.timeline.btn_pan_left.setIcon(
            IconService.get_icon("chevron-left", muted, 14),
        )
        self.timeline.btn_pan_right.setIcon(
            IconService.get_icon("chevron-right", muted, 14),
        )
        # Header glyph uses accent colour — palette change re-derives.
        # The version label uses QSS muted via stylesheet, so no extra
        # work needed there.
        _ = accent  # silence unused — accent is reserved for future re-tint paths
        # Cursors capability has its own InfiniteLine pens cached at
        # spawn time — re-spawning isn't worth the complexity here;
        # users get the new colour pair next time they re-arm cursors.

    def _apply_palette(self) -> None:
        """Force every default-Qt role to the scope's dark palette.

        QSS only styles widgets whose property selectors match — a
        QSpinBox in a deeply-nested capability widget that we haven't
        explicitly named falls back to the platform palette (white bg +
        black text on macOS). Setting the QPalette here catches all
        those defaults so even un-themed widgets read correctly. The
        QSS rules layered on top fine-tune the polish.
        """
        p = self._palette
        accent = self._variant.accent_color or p["accent"]
        palette = QPalette()
        # Window-level
        palette.setColor(QPalette.ColorRole.Window, QColor(p["bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(p["text"]))
        # Surfaces
        palette.setColor(QPalette.ColorRole.Base, QColor(p["surface"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(p["surface_alt"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(p["text"]))
        # Buttons (covers QPushButton + QToolButton + QSpinBox arrows
        # AND, critically, the QComboBox drop-down sub-control bg that
        # Fusion paints from palette.Button. Matching it to ``bg`` so
        # the chevron region looks UNIFIED with the combo's interior —
        # otherwise a lighter rectangle appears on the right side of
        # every combo, the chief "Frankenstein" complaint).
        palette.setColor(QPalette.ColorRole.Button, QColor(p["bg"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(p["text"]))
        # Tooltips
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(p["surface_hi"]))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(p["text"]))
        # Selection highlight (combo popups, list selections)
        palette.setColor(QPalette.ColorRole.Highlight, QColor(accent))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(p["bg"]))
        # Placeholder ghost text + links
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(p["muted"]))
        palette.setColor(QPalette.ColorRole.Link, QColor(accent))
        # Disabled state — dimmer but still readable
        for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                     QPalette.ColorRole.ButtonText):
            palette.setColor(QPalette.ColorGroup.Disabled, role,
                             QColor(p["muted"]))
        self.setPalette(palette)

    def _normalize_form_widgets(self) -> None:
        """Apply the legacy-scope theming pattern to every combo.

        The deleted ``scope_window.py`` (which had no theme issues)
        did exactly this: it walked ``findChildren(QComboBox)`` and
        called ``view.setStyleSheet(popup_qss)`` on the *existing*
        combo view — without replacing it. The whole-app Fusion style
        (set in ``__main__.py``) makes the field colours stick;
        styling the existing view directly takes care of the popup
        which would otherwise default to macOS's white NSMenu look.

        Replacing the view (what an earlier pass tried) had no effect
        on the popup because QComboBox wraps the view in a private
        container whose own background bleeds through unless THAT is
        styled too — easier to keep the default view and just style
        it, which is what the legacy did successfully.
        """
        p = self._palette
        accent = self._variant.accent_color or p["accent"]
        # Popup QSS — applied to BOTH the view and the popup
        # container (``view.parent()`` is a ``QComboBoxPrivateContainer``,
        # the QFrame that wraps the view and shows up as a white halo
        # around the dropdown unless explicitly styled).
        popup_qss = f"""
            QAbstractItemView,
            QListView {{
                background-color: {p["surface_hi"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
                outline: none;
                padding: 4px;
                selection-background-color: {accent};
                selection-color: {p["bg"]};
            }}
            QAbstractItemView::item,
            QListView::item {{
                padding: 5px 10px;
                border-radius: 4px;
                color: {p["text"]};
                background-color: transparent;
                min-height: 22px;
            }}
            QAbstractItemView::item:hover,
            QListView::item:hover {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
            }}
            QAbstractItemView::item:selected,
            QListView::item:selected {{
                background-color: {accent};
                color: {p["bg"]};
            }}
            QFrame {{
                background-color: {p["surface_hi"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
            }}
        """
        # Popups are TOP-LEVEL widgets when shown — they don't
        # inherit the BaseScopeWindow's palette. So we set our dark
        # palette explicitly on each view + its container, matching
        # the QSS so text colour AND background match in the popup.
        popup_palette = self.palette()
        # Per-combo stylesheet — set DIRECTLY on the widget so it
        # always wins over the app-level QSS. The app-level
        # ``QComboBox::down-arrow { width:12; height:12 }`` (without an
        # image) was letting QMacStyle draw its "=" native chevron;
        # widget-level QSS overrides that for the combo we control.
        combo_field_qss = f"""
            QComboBox {{
                background-color: {p["bg"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 5px;
                padding: 4px 26px 4px 10px;
                min-height: 24px;
                selection-background-color: {accent};
                selection-color: {p["bg"]};
            }}
            QComboBox:hover {{ border-color: {accent}; }}
            QComboBox:focus {{ border-color: {accent}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                background-color: {p["bg"]};
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {p["text_dim"]};
                width: 0;
                height: 0;
                margin-right: 8px;
            }}
            QComboBox::down-arrow:on {{
                border-top-color: {accent};
            }}
        """
        # QProxyStyle that paints a clean triangle chevron over the
        # macOS native "=" arrow. QSS can't override the sub-control
        # rendering of ``PE_IndicatorComboBoxArrow`` on macOS — only
        # the QStyle layer can.
        arrow_proxy = _ComboArrowProxy(self.style(), p["text_dim"])
        for combo in self.findChildren(QComboBox):
            # Widget-level QSS overrides app-level — covers background,
            # border, and item padding cleanly. The QStyle proxy
            # handles the chevron because QSS can't.
            combo.setStyleSheet(combo_field_qss)
            combo.setStyle(arrow_proxy)
            view = combo.view()
            if view is None:
                continue
            view.setStyleSheet(popup_qss)
            view.setPalette(popup_palette)
            # ALSO style the popup container (the QFrame that wraps
            # the view) — that's where the macOS white halo comes
            # from. The container is the top-level when popup shows.
            container = view.parent()
            if container is not None and isinstance(container, QWidget):
                container.setStyleSheet(popup_qss)
                container.setPalette(popup_palette)

    def _apply_stylesheet(self) -> None:
        """Apply the dark scope theme to the entire window subtree."""
        p = self._palette
        # Variant accent overrides the generic blue.
        accent = self._variant.accent_color or p["accent"]
        self.setStyleSheet(f"""
            QWidget#BaseScopeWindow {{
                background-color: {p["bg"]};
                color: {p["text"]};
            }}
            /* ─── Header ──────────────────────────────────────────── */
            QFrame#ScopeHeader {{
                background-color: {p["surface"]};
                border-bottom: 1px solid {p["border"]};
            }}
            QLabel#ScopeHeaderGlyph {{ color: {accent}; }}
            QLabel#ScopeHeaderTitle {{ color: {p["text"]}; }}
            QLabel#ScopeHeaderBadge {{
                color: {accent};
                background-color: {p["accent_soft"]};
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 2px 8px;
            }}
            QLabel#ScopeHeaderVersion {{ color: {p["muted"]}; }}
            /* ─── Menubar ─────────────────────────────────────────── */
            QMenuBar#ScopeMenuBar {{
                background-color: {p["surface"]};
                border-bottom: 1px solid {p["border_soft"]};
                padding: 3px 8px;
                color: {p["text"]};
            }}
            QMenuBar#ScopeMenuBar::item {{
                padding: 5px 10px;
                border-radius: 4px;
            }}
            QMenuBar#ScopeMenuBar::item:selected {{
                background-color: {p["surface_alt"]};
            }}
            /* ─── Toolbar ─────────────────────────────────────────── */
            QFrame#ScopeToolbar {{
                background-color: {p["surface"]};
                border-bottom: 1px solid {p["border"]};
            }}
            QToolButton#ScopeToolbarBtn {{
                background-color: transparent;
                color: {p["text_dim"]};
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }}
            QToolButton#ScopeToolbarBtn:hover {{
                background-color: {p["surface_hi"]};
                color: {p["text"]};
                border-color: {p["border"]};
            }}
            QToolButton#ScopeToolbarBtn:checked {{
                background-color: {p["accent_soft"]};
                color: {accent};
                border-color: {accent};
            }}
            /* Transport buttons (Run / Stop) get tinted backgrounds so
               they read as primary actions even when not hovered. */
            QToolButton#ScopeToolbarBtn[accent="success"] {{
                color: {p["success"]};
                background-color: {p["success_soft"]};
                border-color: {p["success"]};
            }}
            QToolButton#ScopeToolbarBtn[accent="success"]:hover {{
                background-color: {p["success"]};
                color: {p["bg"]};
            }}
            QToolButton#ScopeToolbarBtn[accent="error"] {{
                color: {p["error"]};
                background-color: {p["error_soft"]};
                border-color: {p["error"]};
            }}
            QToolButton#ScopeToolbarBtn[accent="error"]:hover {{
                background-color: {p["error"]};
                color: {p["bg"]};
            }}
            QFrame#ScopeToolbarSep {{
                background-color: {p["border"]};
                max-width: 1px;
                margin: 6px 8px;
            }}
            QLabel#ScopeToolbarPill {{
                color: {accent};
                background-color: {p["accent_soft"]};
                border: 1px solid {accent};
                border-radius: 11px;
                padding: 3px 14px;
                font-family: {font_service.MONO_STACK};
                font-size: 11px;
                font-weight: 600;
            }}
            /* ─── Sidebar + Inspector ─────────────────────────────── */
            QFrame#ScopeSidebar,
            QFrame#ScopeInspector {{
                background-color: {p["surface"]};
                border-right: 1px solid {p["border"]};
            }}
            QFrame#ScopeInspector {{
                border-right: none;
                border-left: 1px solid {p["border"]};
            }}
            QLabel#ScopeSidebarTitle,
            QLabel#ScopeInspectorTitle {{ color: {p["text"]}; }}
            QLabel#ScopeSidebarSubTitle {{ color: {p["muted"]}; }}
            QFrame#ScopeSidebarSectionSep {{
                background-color: {p["border_soft"]};
                margin: 6px 0 2px 0;
            }}
            QToolButton#ScopeSidebarCollapseBtn,
            QToolButton#ScopeInspectorCollapseBtn {{
                background-color: {p["surface_alt"]};
                color: {p["muted"]};
                border: 1px solid {p["border"]};
                border-radius: 4px;
                padding: 0;
            }}
            QToolButton#ScopeSidebarCollapseBtn:hover,
            QToolButton#ScopeInspectorCollapseBtn:hover {{
                color: {p["text"]};
                border-color: {accent};
            }}
            QFrame#ScopeSidebarListHost,
            QFrame#ScopeSidebarViewsHost {{
                background-color: {p["surface_alt"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 8px;
            }}
            QLabel#ScopeSidebarSignalUnit {{
                color: {p["muted"]};
                background-color: {p["surface_hi"]};
                border: 1px solid {p["border"]};
                border-radius: 4px;
                padding: 1px 6px;
            }}
            QToolButton#ScopeSidebarSaveBtn {{
                background-color: {p["accent_soft"]};
                color: {accent};
                border: 1px solid {accent};
                border-radius: 4px;
                padding: 2px 8px;
            }}
            QToolButton#ScopeSidebarSaveBtn:hover {{
                background-color: {accent};
                color: {p["bg"]};
            }}
            QFrame#ScopeSidebarViewRow {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            QFrame#ScopeSidebarViewRow:hover {{
                background-color: {p["surface_hi"]};
                border-color: {p["border"]};
            }}
            QPushButton#ScopeSidebarViewName {{
                background: transparent;
                border: none;
                color: {p["text"]};
                text-align: left;
                padding: 2px 4px;
            }}
            QPushButton#ScopeSidebarViewName:hover {{
                color: {accent};
            }}
            QToolButton#ScopeSidebarViewDelBtn {{
                background: transparent;
                color: {p["muted"]};
                border: 1px solid transparent;
                border-radius: 3px;
                font-size: 14px;
                padding: 0;
            }}
            QToolButton#ScopeSidebarViewDelBtn:hover {{
                color: {p["error"]};
                border-color: {p["error"]};
            }}
            QFrame#ScopeInspectorGroup {{
                background-color: {p["surface_alt"]};
                border: 1px solid {p["border_soft"]};
                border-top: 1px solid {p["border"]};
                border-radius: 8px;
            }}
            QLabel#ScopeInspectorGroupTitle {{
                color: {accent};
            }}
            QLabel#ScopeInspectorGroupHint,
            QLabel#ScopeSidebarHint {{
                color: {p["muted"]};
            }}
            /* Inspector form-row label ("Mode", "Source", "Edge",
               "Level") — text_dim so the label reads as the field
               descriptor without competing with the value. */
            QLabel#ScopeFormFieldLabel {{
                color: {p["text_dim"]};
            }}
            /* Trigger / SMPS status hint text — readable but secondary. */
            QLabel#ScopeInspectorStatusHint {{
                color: {p["text_dim"]};
            }}
            QFrame#ScopeSidebarSignalRow {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            QFrame#ScopeSidebarSignalRow:hover {{
                background-color: {p["surface_hi"]};
                border-color: {p["border"]};
            }}
            QLabel#ScopeSidebarSignalName {{
                color: {p["text"]};
            }}
            /* ─── Plot canvas ─────────────────────────────────────── */
            QFrame#ScopePlotCanvas {{
                background-color: {p["plot_bg"]};
                border: none;
            }}
            QLabel#ScopeEmptyTitle {{ color: {p["text"]}; }}
            QLabel#ScopeEmptyHint  {{ color: {p["muted"]}; }}
            /* ─── Drawer + timeline ───────────────────────────────── */
            QFrame#ScopeDrawer,
            QFrame#ScopeTimelineBar {{
                background-color: {p["surface"]};
                border-top: 1px solid {p["border"]};
            }}
            QLabel#ScopeDrawerSummary {{ color: {p["text_dim"]}; }}
            QLabel#ScopeTimelineRange {{
                color: {p["text_dim"]};
                font-family: {font_service.MONO_STACK};
            }}
            QLabel#ScopeDrawerStatusDot[state="idle"]     {{ color: {p["muted"]};   }}
            QLabel#ScopeDrawerStatusDot[state="running"]  {{ color: {p["accent"]};  }}
            QLabel#ScopeDrawerStatusDot[state="success"]  {{ color: {p["success"]}; }}
            QLabel#ScopeDrawerStatusDot[state="warning"]  {{ color: {p["warning"]}; }}
            QLabel#ScopeDrawerStatusDot[state="error"]    {{ color: {p["error"]};   }}
            QPushButton#ScopeDrawerExpandBtn,
            QPushButton#ScopeTimelineActionBtn {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
                padding: 0 12px;
            }}
            QPushButton#ScopeDrawerExpandBtn:hover,
            QPushButton#ScopeTimelineActionBtn:hover {{
                background-color: {p["surface_hi"]};
                border-color: {accent};
                color: {accent};
            }}
            QToolButton#ScopeTimelineStepBtn {{
                background-color: {p["surface_alt"]};
                color: {p["text_dim"]};
                border: 1px solid {p["border"]};
                border-radius: 4px;
                font-size: 11px;
                padding: 0;
            }}
            QToolButton#ScopeTimelineStepBtn:hover {{
                border-color: {accent};
                color: {accent};
            }}
            /* Timeline range combo — slightly wider min-width than
               the generic combo so "Between Cursors" fits. The look
               itself comes from the global QComboBox rules above. */
            QComboBox#ScopeTimelineRangeCombo {{
                min-width: 130px;
            }}
            QSlider#ScopeTimelineSlider::groove:horizontal {{
                background: {p["surface_alt"]};
                height: 4px;
                border-radius: 2px;
                border: 1px solid {p["border_soft"]};
            }}
            QSlider#ScopeTimelineSlider::sub-page:horizontal {{
                background: {accent};
                border-radius: 2px;
            }}
            QSlider#ScopeTimelineSlider::handle:horizontal {{
                background: {accent};
                width: 14px;
                height: 14px;
                margin: -6px 0;
                border-radius: 7px;
                border: 2px solid {p["surface"]};
            }}
            QSlider#ScopeTimelineSlider::handle:horizontal:hover {{
                background: {p["accent_strong"]};
            }}
            QSplitter#ScopeBodySplitter::handle {{
                background-color: {p["border_soft"]};
            }}
            /* ─── ALL form controls (combos, spins, line edits) ─────
               Scope-wide so timeline combos, capability widgets, etc.
               all get the same dark treatment. macOS's aqua style is
               bypassed via per-widget Fusion in ``_normalize_form_widgets``;
               this QSS adds the colour + chrome polish on top. */
            QComboBox,
            QDoubleSpinBox,
            QSpinBox,
            QLineEdit {{
                background-color: {p["bg"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 5px;
                /* 26 px right padding leaves room for the chevron. */
                padding: 4px 26px 4px 10px;
                min-height: 24px;
                selection-background-color: {accent};
                selection-color: {p["bg"]};
            }}
            QComboBox:focus,
            QDoubleSpinBox:focus,
            QSpinBox:focus,
            QLineEdit:focus {{
                border-color: {accent};
                background-color: {p["surface"]};
            }}
            QComboBox:hover,
            QDoubleSpinBox:hover,
            QSpinBox:hover,
            QLineEdit:hover {{
                border-color: {accent};
            }}
            QComboBox:disabled,
            QDoubleSpinBox:disabled,
            QSpinBox:disabled,
            QLineEdit:disabled {{
                color: {p["muted"]};
                background-color: {p["surface"]};
                border-color: {p["border_soft"]};
            }}
            /* Drop-down sub-control: draw a clean CSS down-triangle
               instead of the macOS "=" chevron the user complained
               about. We target combos that carry the
               ``scopeManaged="true"`` property — that's tagged by
               ``_normalize_form_widgets`` so the selector beats the
               app-level QSS in specificity. */
            QComboBox[scopeManaged="true"]::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 22px;
                border: none;
                background-color: {p["bg"]};
            }}
            QComboBox[scopeManaged="true"]::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {p["text_dim"]};
                width: 0;
                height: 0;
                margin-right: 8px;
            }}
            QComboBox[scopeManaged="true"]::down-arrow:hover,
            QComboBox[scopeManaged="true"]::down-arrow:on {{
                border-top-color: {accent};
            }}
            /* The dropdown popup — uses QListView (forced via
               ``_normalize_combo_popups``), so this DOES apply on
               macOS now. */
            QComboBox QAbstractItemView,
            QListView#ScopeComboPopup {{
                background-color: {p["surface_hi"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
                padding: 4px;
                outline: 0;
                selection-background-color: {accent};
                selection-color: {p["bg"]};
            }}
            QComboBox QAbstractItemView::item,
            QListView#ScopeComboPopup::item {{
                padding: 5px 10px;
                border-radius: 4px;
                color: {p["text"]};
                min-height: 22px;
            }}
            QComboBox QAbstractItemView::item:selected,
            QComboBox QAbstractItemView::item:hover,
            QListView#ScopeComboPopup::item:selected,
            QListView#ScopeComboPopup::item:hover {{
                background-color: {accent};
                color: {p["bg"]};
            }}
            /* Spin button arrows — kept neutral so they don't fight
               the value text. */
            QDoubleSpinBox::up-button,
            QDoubleSpinBox::down-button,
            QSpinBox::up-button,
            QSpinBox::down-button {{
                width: 14px;
                border: none;
                background: transparent;
            }}
            QDoubleSpinBox::up-arrow,
            QSpinBox::up-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-bottom: 4px solid {p["muted"]};
                width: 0;
                height: 0;
            }}
            QDoubleSpinBox::down-arrow,
            QSpinBox::down-arrow {{
                image: none;
                border-left: 3px solid transparent;
                border-right: 3px solid transparent;
                border-top: 4px solid {p["muted"]};
                width: 0;
                height: 0;
            }}
            /* Inspector-only buttons — the Re-arm / Tsw+Fsw / Duty /
               Ripple buttons inside group cards. */
            QFrame#ScopeInspectorGroup QPushButton {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 5px;
                padding: 5px 10px;
                min-height: 22px;
            }}
            QFrame#ScopeInspectorGroup QPushButton:hover {{
                border-color: {accent};
                color: {accent};
            }}
            QFrame#ScopeInspectorGroup QPushButton:disabled {{
                color: {p["muted"]};
                background-color: {p["surface"]};
            }}
            /* ─── Menu popups (menubar dropdowns + context menus) ── */
            QMenu {{
                background-color: {p["surface_hi"]};
                color: {p["text"]};
                border: 1px solid {p["border"]};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                background: transparent;
            }}
            QMenu::item:selected {{
                background-color: {accent};
                color: {p["bg"]};
            }}
            QMenu::item:disabled {{
                color: {p["muted"]};
            }}
            QMenu::separator {{
                height: 1px;
                background-color: {p["border_soft"]};
                margin: 4px 8px;
            }}
        """)


__all__ = ["BaseScopeWindow", "ScopeVariant", "ScopeCapability"]
