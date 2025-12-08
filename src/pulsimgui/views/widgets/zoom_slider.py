"""Zoom slider widget for status bar and corner overlay."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QSlider,
    QPushButton,
    QLabel,
)

from pulsimgui.resources.icons import IconService


class ZoomSlider(QWidget):
    """Compact zoom slider with + / - buttons."""

    zoom_changed = Signal(float)  # Emits zoom percentage (e.g., 100.0 for 100%)

    # Zoom range
    ZOOM_MIN = 10    # 10%
    ZOOM_MAX = 500   # 500%
    ZOOM_DEFAULT = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._apply_styles()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Zoom out button
        self._zoom_out_btn = QPushButton()
        self._zoom_out_btn.setFixedSize(20, 20)
        self._zoom_out_btn.setIcon(IconService.get_icon("minus", "#6b7280"))
        self._zoom_out_btn.setToolTip("Zoom Out")
        self._zoom_out_btn.clicked.connect(self._on_zoom_out)
        layout.addWidget(self._zoom_out_btn)

        # Slider
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setRange(self.ZOOM_MIN, self.ZOOM_MAX)
        self._slider.setValue(self.ZOOM_DEFAULT)
        self._slider.setFixedWidth(80)
        self._slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self._slider)

        # Zoom in button
        self._zoom_in_btn = QPushButton()
        self._zoom_in_btn.setFixedSize(20, 20)
        self._zoom_in_btn.setIcon(IconService.get_icon("plus", "#6b7280"))
        self._zoom_in_btn.setToolTip("Zoom In")
        self._zoom_in_btn.clicked.connect(self._on_zoom_in)
        layout.addWidget(self._zoom_in_btn)

        # Zoom percentage label
        self._label = QLabel("100%")
        self._label.setFixedWidth(40)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setToolTip("Click to reset to 100%")
        self._label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._label.mousePressEvent = self._on_label_clicked
        layout.addWidget(self._label)

    def _apply_styles(self) -> None:
        """Apply modern styling."""
        self.setStyleSheet("""
            ZoomSlider {
                background: transparent;
            }
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #e5e7eb;
            }
            QPushButton:pressed {
                background-color: #d1d5db;
            }
            QSlider::groove:horizontal {
                height: 4px;
                background: #e5e7eb;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                width: 12px;
                height: 12px;
                margin: -4px 0;
                background: #3b82f6;
                border-radius: 6px;
            }
            QSlider::handle:horizontal:hover {
                background: #2563eb;
            }
            QSlider::sub-page:horizontal {
                background: #93c5fd;
                border-radius: 2px;
            }
            QLabel {
                color: #6b7280;
                font-size: 10px;
                font-weight: 500;
            }
        """)

    def _on_slider_changed(self, value: int) -> None:
        """Handle slider value change."""
        self._update_label(value)
        self.zoom_changed.emit(float(value))

    def _on_zoom_in(self) -> None:
        """Handle zoom in button click."""
        current = self._slider.value()
        step = self._get_zoom_step(current)
        new_value = min(current + step, self.ZOOM_MAX)
        self._slider.setValue(new_value)

    def _on_zoom_out(self) -> None:
        """Handle zoom out button click."""
        current = self._slider.value()
        step = self._get_zoom_step(current)
        new_value = max(current - step, self.ZOOM_MIN)
        self._slider.setValue(new_value)

    def _on_label_clicked(self, event) -> None:
        """Handle label click - reset to 100%."""
        self._slider.setValue(self.ZOOM_DEFAULT)

    def _get_zoom_step(self, current_value: int) -> int:
        """Get appropriate zoom step based on current value."""
        if current_value < 50:
            return 5
        elif current_value < 100:
            return 10
        elif current_value < 200:
            return 25
        else:
            return 50

    def _update_label(self, value: int) -> None:
        """Update the zoom percentage label."""
        self._label.setText(f"{value}%")

    def set_zoom(self, percent: float) -> None:
        """Set the zoom level (external update)."""
        # Block signals to prevent feedback loop
        self._slider.blockSignals(True)
        value = int(max(self.ZOOM_MIN, min(self.ZOOM_MAX, percent)))
        self._slider.setValue(value)
        self._update_label(value)
        self._slider.blockSignals(False)

    def zoom_percent(self) -> float:
        """Get current zoom percentage."""
        return float(self._slider.value())


class ZoomOverlay(QWidget):
    """Floating zoom control overlay for corner of view."""

    zoom_changed = Signal(float)
    fit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the overlay UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Container with background
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: rgba(255, 255, 255, 0.95);
                border: 1px solid #e5e7eb;
                border-radius: 6px;
            }
        """)
        container_layout = QHBoxLayout(container)
        container_layout.setContentsMargins(6, 4, 6, 4)
        container_layout.setSpacing(6)

        # Fit button
        self._fit_btn = QPushButton()
        self._fit_btn.setFixedSize(24, 24)
        self._fit_btn.setIcon(IconService.get_icon("maximize", "#6b7280"))
        self._fit_btn.setToolTip("Fit to View (Ctrl+0)")
        self._fit_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #f3f4f6;
            }
        """)
        self._fit_btn.clicked.connect(self.fit_clicked)
        container_layout.addWidget(self._fit_btn)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet("color: #e5e7eb;")
        container_layout.addWidget(sep)

        # Zoom slider
        self._zoom_slider = ZoomSlider()
        self._zoom_slider.zoom_changed.connect(self.zoom_changed)
        container_layout.addWidget(self._zoom_slider)

        layout.addWidget(container)

    def set_zoom(self, percent: float) -> None:
        """Set the zoom level."""
        self._zoom_slider.set_zoom(percent)
