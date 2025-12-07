"""Entry point for PulsimGui application."""

import sys

from PySide6.QtWidgets import QApplication

from pulsimgui.views.main_window import MainWindow


def main() -> int:
    """Run the PulsimGui application."""
    app = QApplication(sys.argv)
    app.setApplicationName("PulsimGui")
    app.setOrganizationName("Pulsim")
    app.setOrganizationDomain("pulsim.org")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
