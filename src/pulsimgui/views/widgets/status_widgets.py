"""Status bar widgets with icons and visual feedback.

Every colour in this module is a :class:`~pulsimgui.services.theme_service.ThemeColors`
token — no raw hex. Widgets accept an optional ``theme_service`` (the design
package `_Themed` convention): when given, they restyle themselves on
``theme_changed``; when omitted they style once from ``LIGHT_THEME`` and the
owner may drive re-theming through the long-standing ``apply_theme(theme)``
hooks (as ``MainWindow`` does for its status-bar segments).
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from pulsimgui.resources.icons import IconService
from pulsimgui.services.theme_service import LIGHT_THEME, Theme
from pulsimgui.views.design.components import _tint
from pulsimgui.views.design.tokens import FontSize, FontWeight, Radius


def _resolve_theme(theme_service: object | None) -> Theme:
    """The service's current theme, or the light fallback when standalone."""
    if theme_service is not None:
        return getattr(theme_service, "current_theme", LIGHT_THEME)
    return LIGHT_THEME


class IconLabel(QWidget):
    """A label with an icon prefix."""

    def __init__(
        self,
        icon_name: str,
        text: str = "",
        icon_color: str | None = None,
        parent=None,
        theme_service: object | None = None,
    ):
        super().__init__(parent)
        theme = _resolve_theme(theme_service)
        self._icon_name = icon_name
        self._icon_color = icon_color or theme.colors.foreground_muted
        self._dark_mode = theme.is_dark

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 0, 6, 0)
        layout.setSpacing(5)

        # Icon label
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 16)
        self._icon_label.setStyleSheet("padding: 0px; margin: 0px;")
        self._update_icon()
        layout.addWidget(self._icon_label)

        # Text label - single line, no wrap, with elision
        self._text_label = QLabel(text)
        self._text_label.setWordWrap(False)
        # v0.8.4 — bumped from 250 to 360 so the GUI + backend version pair
        # (e.g. ``PulsimGui 0.8.4  ·  Backend Pulsim 0.9.0``) renders
        # without truncating "0.9.0" mid-segment.
        self._text_label.setMaximumWidth(360)
        layout.addWidget(self._text_label)

        self._subscribe_theme(theme_service)

    def _subscribe_theme(self, theme_service: object | None) -> None:
        """Adopt a ThemeService: style now and restyle on every theme change.

        Subclasses call this at the END of their own ``__init__`` (and pass
        ``theme_service=None`` to ``super().__init__``) so the overridden
        ``apply_theme`` only ever runs once their colour attributes exist.
        """
        self._theme_service = theme_service
        if theme_service is None:
            return
        changed = getattr(theme_service, "theme_changed", None)
        if changed is not None:
            changed.connect(self.apply_theme)
        self.apply_theme(_resolve_theme(theme_service))

    def _update_icon(self) -> None:
        """Update the icon with current color."""
        icon = IconService.get_icon(self._icon_name, self._icon_color)
        if not icon.isNull():
            pixmap = icon.pixmap(16, 16)
            self._icon_label.setPixmap(pixmap)

    def _set_icon_state(self, icon_name: str | None = None, color: str | None = None) -> None:
        """Apply icon name/color and repaint only when they changed."""
        changed = False
        if icon_name is not None and icon_name != self._icon_name:
            self._icon_name = icon_name
            changed = True
        if color is not None and color != self._icon_color:
            self._icon_color = color
            changed = True
        if changed:
            self._update_icon()

    def setText(self, text: str) -> None:
        """Set the text."""
        self._text_label.setText(text)

    def text(self) -> str:
        """Get the text."""
        return self._text_label.text()

    def setIconColor(self, color: str) -> None:
        """Set icon color."""
        self._set_icon_state(color=color)

    def setIcon(self, icon_name: str) -> None:
        """Change the icon."""
        self._set_icon_state(icon_name=icon_name)

    def setDarkMode(self, dark: bool) -> None:
        """Set dark mode."""
        self._dark_mode = dark
        self._update_icon()

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme-aware colors for generic icon/text labels."""
        self._text_label.setStyleSheet(f"color: {theme.colors.statusbar_foreground};")
        self.setDarkMode(theme.is_dark)

    def setMinimumWidth(self, width: int) -> None:
        """Set minimum width for text label."""
        self._text_label.setMinimumWidth(width - 28)  # Account for icon container and spacing


class CoordinateWidget(QWidget):
    """Widget showing current cursor coordinates with click-to-edit."""

    coordinate_entered = Signal(float, float)  # Emitted when user enters coordinates

    def __init__(self, parent=None, theme_service: object | None = None):
        super().__init__(parent)
        self._x = 0.0
        self._y = 0.0
        self._editing = False
        theme = _resolve_theme(theme_service)
        self._icon_color = theme.colors.primary
        self._focus_border_color = theme.colors.input_focus_border

        self._setup_ui()
        # Initial styling runs through the SAME path as re-theming so the
        # editor can never render with stale, init-only colours.
        self.apply_theme(theme)
        self._theme_service = theme_service
        if theme_service is not None:
            changed = getattr(theme_service, "theme_changed", None)
            if changed is not None:
                changed.connect(self.apply_theme)

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        from PySide6.QtWidgets import QLineEdit, QStackedWidget

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        # Icon (pixmap painted by apply_theme with the themed accent)
        self._icon_label = QLabel()
        self._icon_label.setFixedSize(18, 16)
        self._icon_label.setStyleSheet("padding: 0px; margin: 0px;")
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

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors to coordinate editor visuals."""
        self._icon_color = theme.colors.primary
        self._focus_border_color = theme.colors.input_focus_border
        icon = IconService.get_icon("crosshairs", self._icon_color)
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(16, 16))
        self._display_label.setStyleSheet(f"color: {theme.colors.statusbar_foreground};")
        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1px solid {self._focus_border_color};
                border-radius: 3px;
                padding: 1px 4px;
                font-size: {FontSize.CAPTION}px;
                color: {theme.colors.foreground};
                background-color: {theme.colors.input_background};
            }}
        """)


class ZoomWidget(IconLabel):
    """Widget showing current zoom level."""

    def __init__(self, parent=None, theme_service: object | None = None):
        theme = _resolve_theme(theme_service)
        super().__init__("zoom", "100%", theme.colors.primary, parent)
        self._zoom_color = theme.colors.primary
        self.setToolTip("Current zoom level")
        self._subscribe_theme(theme_service)

    def setZoom(self, percent: float) -> None:
        """Set zoom percentage."""
        self.setText(f"{percent:.0f}%")

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors to zoom widget."""
        self._zoom_color = theme.colors.primary
        self.setIconColor(self._zoom_color)
        super().apply_theme(theme)


class SelectionWidget(IconLabel):
    """Widget showing selection count."""

    def __init__(self, parent=None, theme_service: object | None = None):
        theme = _resolve_theme(theme_service)
        super().__init__("cursor", "", theme.colors.foreground_muted, parent)
        self._selection_color = theme.colors.primary
        self.setToolTip("Number of selected items")
        self._subscribe_theme(theme_service)

    def setCount(self, count: int) -> None:
        """Set selection count."""
        if count > 0:
            self.setText(f"{count} selected")
            self.setIconColor(self._selection_color)
            self.show()
        else:
            self.setText("")
            self.hide()

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors to selection widget."""
        self._selection_color = theme.colors.primary
        super().apply_theme(theme)


class ModifiedWidget(IconLabel):
    """Widget showing document modified state."""

    def __init__(self, parent=None, theme_service: object | None = None):
        theme = _resolve_theme(theme_service)
        super().__init__("saved", "", theme.colors.success, parent)
        self._is_modified = False
        self._saved_color = theme.colors.success
        self._modified_color = theme.colors.warning
        self.setToolTip("Document status")
        self._subscribe_theme(theme_service)

    def setModified(self, modified: bool) -> None:
        """Set modified state."""
        self._is_modified = modified
        if modified:
            self.setIcon("modified")
            self.setIconColor(self._modified_color)
            self.setText("Modified")
            self.setToolTip("Document has unsaved changes")
        else:
            self.setIcon("saved")
            self.setIconColor(self._saved_color)
            self.setText("")
            self.setToolTip("Document saved")
        self.setVisible(modified)

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors to modified widget."""
        self._saved_color = theme.colors.success
        self._modified_color = theme.colors.warning
        super().apply_theme(theme)
        self.setModified(self._is_modified)


class SolverPill(QWidget):
    """Glanceable status-bar pill showing the active integrator, dt, and
    linear solver, color-coded by last-run convergence health.

    Visual states:
        idle      — gray, no badge        (no simulation has run yet)
        success   — green tint            (last run converged cleanly)
        recovered — amber tint            (last run needed retries / fallback)
        failed    — red tint              (last run did not converge)
    """

    clicked = Signal()

    STATE_IDLE = "idle"
    STATE_SUCCESS = "success"
    STATE_RECOVERED = "recovered"
    STATE_FAILED = "failed"

    _STATES = (STATE_IDLE, STATE_SUCCESS, STATE_RECOVERED, STATE_FAILED)

    def __init__(self, parent=None, theme_service: object | None = None):
        super().__init__(parent)
        self.setObjectName("SolverPill")
        self._integrator = "—"
        self._dt = ""
        self._linear_solver = ""
        self._adaptive = False
        self._state = self.STATE_IDLE
        self._theme = _resolve_theme(theme_service)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(0)
        self._label = QLabel("—")
        self._label.setObjectName("SolverPillLabel")
        font = self._label.font()
        font.setPointSize(max(8, font.pointSize() - 1))
        font.setBold(True)
        self._label.setFont(font)
        layout.addWidget(self._label)

        self._apply_state_style()
        self.setToolTip("Click to open Simulation Settings")

        self._theme_service = theme_service
        if theme_service is not None:
            changed = getattr(theme_service, "theme_changed", None)
            if changed is not None:
                changed.connect(self.apply_theme)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_solver(self, integrator: str, dt: str = "", linear_solver: str = "",
                   adaptive: bool = False) -> None:
        """Update the displayed solver triple."""
        self._integrator = integrator or "—"
        self._dt = dt or ""
        self._linear_solver = linear_solver or ""
        self._adaptive = bool(adaptive)
        self._render_label()

    def set_state(self, state: str) -> None:
        """Set the visual health state of the pill."""
        if state not in self._STATES:
            state = self.STATE_IDLE
        if state != self._state:
            self._state = state
            self._apply_state_style()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _render_label(self) -> None:
        parts: list[str] = [self._integrator]
        if self._dt:
            parts.append(f"dt={self._dt}")
        if self._linear_solver:
            parts.append(self._linear_solver)
        if self._adaptive:
            parts.append("adaptive")
        self._label.setText(" · ".join(parts))

    def _state_palette(self) -> tuple[str, str]:
        """``(background, text)`` for the current state, from theme tokens.

        The background is the strong status colour at low alpha (the design
        system's ``_tint`` convention) so the pill reads correctly on both
        light and dark status bars.
        """
        c = self._theme.colors
        if self._state == self.STATE_SUCCESS:
            return _tint(c.success, 46), c.success
        if self._state == self.STATE_RECOVERED:
            return _tint(c.warning, 51), c.warning
        if self._state == self.STATE_FAILED:
            return _tint(c.error, 56), c.error
        return _tint(c.foreground_muted, 36), c.foreground_muted

    def _apply_state_style(self) -> None:
        bg, fg = self._state_palette()
        self.setStyleSheet(
            f"#SolverPill {{ background: {bg}; border-radius: {Radius.MD}px; }} "
            f"#SolverPillLabel {{ color: {fg}; padding: 0 2px; }}"
        )

    def mousePressEvent(self, event) -> None:  # pragma: no cover - Qt event
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def apply_theme(self, theme: Theme) -> None:
        """Rebuild the state palette from the new theme's tokens."""
        self._theme = theme
        self._apply_state_style()


class SimulationStatusWidget(IconLabel):
    """Widget showing simulation status."""

    def __init__(self, parent=None, theme_service: object | None = None):
        theme = _resolve_theme(theme_service)
        super().__init__("sim-ready", "Ready", theme.colors.foreground_muted, parent)
        self._error_color = theme.colors.error
        self._running_color = theme.colors.primary
        self._complete_color = theme.colors.success
        self._idle_color = theme.colors.foreground_muted
        self.setToolTip("Simulation status")
        self._subscribe_theme(theme_service)

    def setStatus(self, status: str, is_running: bool = False, is_error: bool = False) -> None:
        """Set simulation status."""
        if is_error:
            icon_name = "sim-error"
            color = self._error_color
        elif is_running:
            icon_name = "play"
            color = self._running_color
        elif status.lower() in ("complete", "done", "finished"):
            icon_name = "sim-done"
            color = self._complete_color
        else:
            icon_name = "sim-ready"
            color = self._idle_color

        self._set_icon_state(icon_name=icon_name, color=color)
        if status != self.text():
            self.setText(status)

    def setDarkMode(self, dark: bool) -> None:
        """Override to keep status colors."""
        self._dark_mode = dark
        # Don't update icon - keep status-specific colors

    def apply_theme(self, theme: Theme) -> None:
        """Apply theme colors while preserving status semantics."""
        self._error_color = theme.colors.error
        self._running_color = theme.colors.primary
        self._complete_color = theme.colors.success
        self._idle_color = theme.colors.foreground_muted
        self._text_label.setStyleSheet(f"color: {theme.colors.statusbar_foreground};")


class StatusBanner(QWidget):
    """A styled banner for displaying status messages in dialogs."""

    # Status types (semantic palette resolved from the active theme)
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

    def __init__(
        self,
        text: str,
        status_type: str = "info",
        parent=None,
        theme_service: object | None = None,
    ):
        super().__init__(parent)
        self._status_type = status_type
        self._text = text
        self._theme: Theme | None = None
        self._theme_service = theme_service
        if theme_service is not None:
            self._theme = _resolve_theme(theme_service)
            changed = getattr(theme_service, "theme_changed", None)
            if changed is not None:
                changed.connect(self.apply_theme)

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
        """Apply the style based on status type, from theme tokens."""
        theme = self._theme if self._theme is not None else LIGHT_THEME
        c = theme.colors
        styles = {
            "success": {"bg": c.success_background, "accent": c.success, "icon": "check"},
            "error": {"bg": c.error_background, "accent": c.error, "icon": "error"},
            "warning": {"bg": c.warning_background, "accent": c.warning, "icon": "warning"},
            "info": {"bg": c.info_background, "accent": c.info, "icon": "info"},
        }
        style = styles.get(self._status_type, styles["info"])

        # Set icon
        icon = IconService.get_icon(style["icon"], style["accent"])
        if not icon.isNull():
            self._icon_label.setPixmap(icon.pixmap(20, 20))

        # Set text color
        self._text_label.setStyleSheet(
            f"color: {style['accent']};"
            f" font-weight: {FontWeight.MEDIUM};"
            f" font-size: {FontSize.SMALL}px;"
        )

        # Set banner style
        self.setStyleSheet(f"""
            StatusBanner {{
                background-color: {style['bg']};
                border: 1px solid {style['accent']};
                border-radius: {Radius.SM}px;
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

    def apply_theme(self, theme: Theme) -> None:
        """Apply one theme-aware semantic palette to the banner."""
        self._theme = theme
        self._apply_style()

    @classmethod
    def success(cls, text: str, parent=None, theme_service: object | None = None) -> "StatusBanner":
        """Create a success banner."""
        return cls(text, cls.SUCCESS, parent, theme_service=theme_service)

    @classmethod
    def error(cls, text: str, parent=None, theme_service: object | None = None) -> "StatusBanner":
        """Create an error banner."""
        return cls(text, cls.ERROR, parent, theme_service=theme_service)

    @classmethod
    def warning(cls, text: str, parent=None, theme_service: object | None = None) -> "StatusBanner":
        """Create a warning banner."""
        return cls(text, cls.WARNING, parent, theme_service=theme_service)

    @classmethod
    def info(cls, text: str, parent=None, theme_service: object | None = None) -> "StatusBanner":
        """Create an info banner."""
        return cls(text, cls.INFO, parent, theme_service=theme_service)
