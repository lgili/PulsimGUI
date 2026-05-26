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

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenuBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from pulsimgui.resources.icons import IconService

from .plot_canvas import PlotCanvas


# ── Palette tokens ──────────────────────────────────────────────────────────
# Centralised so capabilities + variants reference the same colour names.
# Dark-first; light overrides live in ``_LIGHT`` for the theme switch.
_DARK = {
    "bg":            "#1a1d23",
    "surface":       "#22262e",
    "surface_alt":   "#2a2f38",
    "border":        "#3a4150",
    "border_soft":   "#2e333d",
    "text":          "#e4e7ec",
    "muted":         "#8a92a3",
    "accent":        "#5b8def",
    "accent_soft":   "rgba(91, 141, 239, 0.18)",
    "success":       "#4ade80",
    "warning":       "#fbbf24",
    "error":         "#f87171",
    "plot_bg":       "#16181d",
    "plot_grid":     "#2c313a",
    "plot_axis":     "#5a6273",
}

_LIGHT = {
    "bg":            "#f5f7fb",
    "surface":       "#ffffff",
    "surface_alt":   "#edf2fa",
    "border":        "#cdd9e8",
    "border_soft":   "#dfe7f2",
    "text":          "#0b1220",
    "muted":         "#4f627a",
    "accent":        "#1d4ed8",
    "accent_soft":   "rgba(29, 78, 216, 0.12)",
    "success":       "#059669",
    "warning":       "#d97706",
    "error":         "#dc2626",
    "plot_bg":       "#ffffff",
    "plot_grid":     "#e5e7eb",
    "plot_axis":     "#374151",
}


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
        self.setFixedHeight(38)
        self._variant = variant

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(10)

        # Type glyph — replaces the old "● Scope" circle.
        self._glyph = QLabel(variant.type_glyph)
        self._glyph.setObjectName("ScopeHeaderGlyph")
        f = QFont()
        f.setPointSize(14)
        self._glyph.setFont(f)
        layout.addWidget(self._glyph)

        # Scope title.
        self._title = QLabel(variant.name)
        self._title.setObjectName("ScopeHeaderTitle")
        tf = QFont()
        tf.setPointSize(13)
        tf.setWeight(QFont.Weight.DemiBold)
        self._title.setFont(tf)
        layout.addWidget(self._title)

        # Type badge.
        self._badge = QLabel(variant.type_label)
        self._badge.setObjectName("ScopeHeaderBadge")
        bf = QFont()
        bf.setPointSize(9)
        bf.setWeight(QFont.Weight.Medium)
        self._badge.setFont(bf)
        layout.addWidget(self._badge)

        layout.addStretch(1)

        self._version = QLabel(f"v{version}" if version else "")
        self._version.setObjectName("ScopeHeaderVersion")
        vf = QFont()
        vf.setPointSize(10)
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

    def __init__(self, *, accent_color: str = "#5b8def", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeToolbar")
        self.setFixedHeight(44)
        self._accent_color = accent_color
        self._icon_color = "#cdd6e3"  # default icon tone on dark surface

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
            # use the neutral icon tone derived from the theme.
            tone = {
                "success": "#4ade80",
                "error":   "#f87171",
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
        self._collapse_btn.setIcon(IconService.get_icon("chevron-left", "#8a92a3", 14))
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

        # Saved-views section header.
        sv_title = QLabel("Saved Views")
        sv_title.setObjectName("ScopeSidebarSubTitle")
        sf = QFont()
        sf.setPointSize(10)
        sf.setWeight(QFont.Weight.DemiBold)
        sv_title.setFont(sf)
        layout.addWidget(sv_title)

        # Saved views placeholder hint.
        self.views_list_host = QFrame()
        self.views_list_host.setObjectName("ScopeSidebarViewsHost")
        self.views_list_host.setMinimumHeight(80)
        views_layout = QVBoxLayout(self.views_list_host)
        views_layout.setContentsMargins(12, 12, 12, 12)
        sv_hint = QLabel("Capture the current zoom + cursors\nwith View → Save view.")
        sv_hint.setObjectName("ScopeSidebarHint")
        sv_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv_hint.setWordWrap(True)
        sv_hint.setFont(hf)
        views_layout.addWidget(sv_hint)
        layout.addWidget(self.views_list_host, stretch=1)

        self._collapsed = False

    def toggle_collapsed(self) -> None:
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.setFixedWidth(self.rail_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-right", "#8a92a3", 14))
            self._collapse_btn.setToolTip("Expand sidebar (Ctrl+B)")
        else:
            self.setFixedWidth(self.expanded_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-left", "#8a92a3", 14))
            self._collapse_btn.setToolTip("Collapse sidebar (Ctrl+B)")
        self.collapsed.emit(self._collapsed)

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
        chip = QLabel()
        chip.setFixedSize(10, 10)
        chip.setStyleSheet(
            f"background-color: {color}; border-radius: 5px; border: 1px solid rgba(0,0,0,0.25);"
        )
        rl.addWidget(chip)
        label = QLabel(name + (f"   [{unit}]" if unit else ""))
        label.setObjectName("ScopeSidebarSignalName")
        lf = QFont()
        lf.setPointSize(10)
        label.setFont(lf)
        rl.addWidget(label, stretch=1)
        self._signal_list_layout.addWidget(row)
        self._signal_rows.append(row)

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

    expanded_width = 240
    rail_width = 44

    collapsed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeInspector")
        self.setFixedWidth(self.expanded_width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._collapse_btn = QToolButton()
        self._collapse_btn.setObjectName("ScopeInspectorCollapseBtn")
        self._collapse_btn.setIcon(IconService.get_icon("chevron-right", "#8a92a3", 14))
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
        v.setSpacing(6)
        lbl = QLabel(title)
        lbl.setObjectName("ScopeInspectorGroupTitle")
        f = QFont()
        f.setPointSize(10)
        f.setWeight(QFont.Weight.DemiBold)
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
        if self._collapsed:
            self.setFixedWidth(self.rail_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-left", "#8a92a3", 14))
        else:
            self.setFixedWidth(self.expanded_width)
            self._collapse_btn.setIcon(IconService.get_icon("chevron-right", "#8a92a3", 14))
        self.collapsed.emit(self._collapsed)


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

    def paintEvent(self, event):  # noqa: D401 - Qt override
        super().paintEvent(event)
        # Subtle grid hint behind the empty-state label so the surface
        # reads as a plot area, not just a blank rectangle.
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        pen = QPen(QColor(_DARK["plot_grid"]))
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
    """Bottom drawer — collapses to a single-line summary by default."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ScopeDrawer")
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

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

        # Pan left / scrubber / pan right.
        self.btn_pan_left = QToolButton()
        self.btn_pan_left.setObjectName("ScopeTimelineStepBtn")
        self.btn_pan_left.setIcon(IconService.get_icon("chevron-left", "#8a92a3", 14))
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
        self.btn_pan_right.setIcon(IconService.get_icon("chevron-right", "#8a92a3", 14))
        self.btn_pan_right.setIconSize(QSize(14, 14))
        self.btn_pan_right.setFixedSize(26, 24)
        self.btn_pan_right.setToolTip("Pan right")
        layout.addWidget(self.btn_pan_right)

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
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("BaseScopeWindow")
        self.setWindowTitle(variant.name)
        self.setMinimumSize(960, 600)
        self.resize(1280, 800)

        self._variant = variant
        self._capabilities: list[ScopeCapability] = []

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

        self.sidebar = _ScopeSidebar(self)
        body.addWidget(self.sidebar)

        self.plot_canvas = PlotCanvas(accent_color=variant.accent_color, parent=self)
        body.addWidget(self.plot_canvas)

        self.inspector = _ScopeInspector(self)
        body.addWidget(self.inspector)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        root.addWidget(body, stretch=1)

        # ── Drawer + timeline ───────────────────────────────────────────
        self.drawer = _ScopeDrawer(self)
        root.addWidget(self.drawer)
        self.timeline = _ScopeTimelineBar(self)
        root.addWidget(self.timeline)

        # ── Wire toolbar toggles to the panel collapse buttons ──────────
        self.toolbar.sidebar_toggled.connect(self._on_sidebar_toggle)
        self.toolbar.inspector_toggled.connect(self._on_inspector_toggle)

        # ── Attach capabilities ─────────────────────────────────────────
        self._apply_stylesheet()
        for cap in capabilities or []:
            self.attach_capability(cap)

    # ── Capability lifecycle ────────────────────────────────────────────

    def attach_capability(self, capability: ScopeCapability) -> None:
        """Register a capability with the shell. Idempotent per instance."""
        if capability in self._capabilities:
            return
        capability.attach(self)
        self._capabilities.append(capability)

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

    # ── Theme (dark-first, PLECS-clean) ─────────────────────────────────

    def _apply_stylesheet(self) -> None:
        """Apply the dark scope theme to the entire window subtree."""
        p = _DARK
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
                border-bottom: 1px solid {p["border_soft"]};
            }}
            QLabel#ScopeHeaderGlyph {{ color: {accent}; }}
            QLabel#ScopeHeaderTitle {{ color: {p["text"]}; }}
            QLabel#ScopeHeaderBadge {{
                color: {p["muted"]};
                background-color: {p["surface_alt"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 7px;
                padding: 1px 8px;
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
                border-bottom: 1px solid {p["border_soft"]};
            }}
            QToolButton#ScopeToolbarBtn {{
                background-color: transparent;
                color: {p["text"]};
                border: 1px solid transparent;
                border-radius: 6px;
                font-size: 14px;
                padding: 0;
            }}
            QToolButton#ScopeToolbarBtn:hover {{
                background-color: {p["surface_alt"]};
                border-color: {p["border_soft"]};
            }}
            QToolButton#ScopeToolbarBtn:checked {{
                background-color: {p["accent_soft"]};
                color: {accent};
                border-color: {accent};
            }}
            QToolButton#ScopeToolbarBtn[accent="success"] {{ color: {p["success"]}; }}
            QToolButton#ScopeToolbarBtn[accent="error"]   {{ color: {p["error"]}; }}
            QFrame#ScopeToolbarSep {{
                background-color: {p["border_soft"]};
                max-width: 1px;
                margin: 5px 8px;
            }}
            QLabel#ScopeToolbarPill {{
                color: {p["muted"]};
                background-color: {p["surface_alt"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 11px;
                padding: 3px 12px;
                font-size: 11px;
            }}
            /* ─── Sidebar + Inspector ─────────────────────────────── */
            QFrame#ScopeSidebar,
            QFrame#ScopeInspector {{
                background-color: {p["surface"]};
                border-right: 1px solid {p["border_soft"]};
            }}
            QFrame#ScopeInspector {{
                border-right: none;
                border-left: 1px solid {p["border_soft"]};
            }}
            QLabel#ScopeSidebarTitle,
            QLabel#ScopeInspectorTitle {{ color: {p["text"]}; }}
            QLabel#ScopeSidebarSubTitle {{ color: {p["muted"]}; }}
            QToolButton#ScopeSidebarCollapseBtn,
            QToolButton#ScopeInspectorCollapseBtn {{
                background-color: {p["surface_alt"]};
                color: {p["muted"]};
                border: 1px solid {p["border_soft"]};
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
            QFrame#ScopeInspectorGroup {{
                background-color: {p["surface_alt"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 8px;
            }}
            QLabel#ScopeInspectorGroupTitle {{
                color: {p["muted"]};
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            QLabel#ScopeInspectorGroupHint,
            QLabel#ScopeSidebarHint {{
                color: {p["muted"]};
            }}
            QFrame#ScopeSidebarSignalRow {{
                background-color: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
            }}
            QFrame#ScopeSidebarSignalRow:hover {{
                background-color: {p["surface_alt"]};
                border-color: {p["border_soft"]};
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
                border-top: 1px solid {p["border_soft"]};
            }}
            QLabel#ScopeDrawerSummary,
            QLabel#ScopeTimelineRange {{ color: {p["muted"]}; }}
            QPushButton#ScopeDrawerExpandBtn,
            QPushButton#ScopeTimelineActionBtn {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 6px;
                padding: 0 12px;
            }}
            QPushButton#ScopeDrawerExpandBtn:hover,
            QPushButton#ScopeTimelineActionBtn:hover {{
                border-color: {accent};
                color: {accent};
            }}
            QToolButton#ScopeTimelineStepBtn {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 4px;
                font-size: 11px;
                padding: 0;
            }}
            QToolButton#ScopeTimelineStepBtn:hover {{
                border-color: {accent};
                color: {accent};
            }}
            QComboBox#ScopeTimelineRangeCombo {{
                background-color: {p["surface_alt"]};
                color: {p["text"]};
                border: 1px solid {p["border_soft"]};
                border-radius: 6px;
                padding: 2px 10px;
                min-width: 130px;
            }}
            QComboBox#ScopeTimelineRangeCombo:hover {{
                border-color: {accent};
            }}
            QSlider#ScopeTimelineSlider::groove:horizontal {{
                background: {p["surface_alt"]};
                height: 4px;
                border-radius: 2px;
            }}
            QSlider#ScopeTimelineSlider::handle:horizontal {{
                background: {accent};
                width: 12px;
                height: 12px;
                margin: -5px 0;
                border-radius: 6px;
            }}
            QSplitter#ScopeBodySplitter::handle {{
                background-color: {p["border_soft"]};
            }}
        """)


__all__ = ["BaseScopeWindow", "ScopeVariant", "ScopeCapability"]
