"""Entry point for PulsimGui application."""

import os
import stat
import sys


def _clear_hidden_flag(path: str) -> None:
    """Remove macOS hidden flag if present.

    Some PySide6 wheels end up with Qt plugin dylibs flagged as hidden, and Qt
    ignores hidden plugin files during discovery.
    """
    if not hasattr(os, "chflags") or not hasattr(stat, "UF_HIDDEN"):
        return
    try:
        current = os.stat(path, follow_symlinks=False).st_flags
    except OSError:
        return
    if current & stat.UF_HIDDEN:
        try:
            os.chflags(path, current & ~stat.UF_HIDDEN, follow_symlinks=False)
        except OSError:
            pass


def _ensure_qt_plugins_visible(plugin_path: str) -> None:
    """Ensure Qt plugin files are visible to Qt on macOS."""
    for root, dirs, files in os.walk(plugin_path):
        for name in dirs:
            _clear_hidden_flag(os.path.join(root, name))
        for name in files:
            _clear_hidden_flag(os.path.join(root, name))


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
                    _ensure_qt_plugins_visible(plugin_path)
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

from PySide6.QtWidgets import QApplication  # noqa: E402

from pulsimgui.views.main_window import MainWindow  # noqa: E402


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
