"""Entry point for PulsimGui application."""

import os
import sys


def _setup_qt_plugin_path() -> None:
    """Configure Qt plugin path before any Qt imports.

    This fixes the "Could not find the Qt platform plugin cocoa" error
    on macOS by setting the plugin path to the PySide6 installation.
    """
    if sys.platform == "darwin":
        try:
            import importlib.util
            spec = importlib.util.find_spec("PySide6")
            if spec and spec.origin:
                pyside_dir = os.path.dirname(spec.origin)
                plugin_path = os.path.join(pyside_dir, "Qt", "plugins")
                platforms_path = os.path.join(plugin_path, "platforms")
                if os.path.isdir(platforms_path):
                    # Set the specific platforms plugin path
                    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_path
                    # Also set QT_PLUGIN_PATH for other Qt plugins
                    os.environ["QT_PLUGIN_PATH"] = plugin_path
                    # Set library path for dylib loading
                    lib_path = os.path.join(pyside_dir, "Qt", "lib")
                    if os.path.isdir(lib_path):
                        existing = os.environ.get("DYLD_LIBRARY_PATH", "")
                        if lib_path not in existing:
                            os.environ["DYLD_LIBRARY_PATH"] = f"{lib_path}:{existing}" if existing else lib_path
        except Exception:
            pass  # If this fails, Qt might still find plugins via other means


# MUST be called before any PySide6/Qt imports
_setup_qt_plugin_path()

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
