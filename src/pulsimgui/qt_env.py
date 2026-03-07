"""Qt runtime environment preparation helpers.

These helpers must run before importing PySide6.Qt* modules.
"""

from __future__ import annotations

import os
import stat
import sys


def _clear_hidden_flag(path: str) -> None:
    """Remove macOS hidden flag when present.

    Some PySide6 wheels can ship plugin files flagged as hidden and Qt then
    skips those files during plugin discovery.
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
            return


def _ensure_qt_plugins_visible(plugin_path: str) -> None:
    """Ensure plugin files are visible to Qt on macOS."""
    for root, dirs, files in os.walk(plugin_path):
        for name in dirs:
            _clear_hidden_flag(os.path.join(root, name))
        for name in files:
            _clear_hidden_flag(os.path.join(root, name))


def setup_qt_plugin_path() -> None:
    """Configure Qt plugin environment before importing Qt modules."""
    if sys.platform != "darwin":
        return

    try:
        import importlib.util

        spec = importlib.util.find_spec("PySide6")
        if spec is None or spec.origin is None:
            return

        pyside_dir = os.path.dirname(spec.origin)
        plugin_path = os.path.join(pyside_dir, "Qt", "plugins")
        platforms_path = os.path.join(plugin_path, "platforms")
        if not os.path.isdir(platforms_path):
            return

        _ensure_qt_plugins_visible(plugin_path)
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_path
        os.environ["QT_PLUGIN_PATH"] = plugin_path

        lib_path = os.path.join(pyside_dir, "Qt", "lib")
        if not os.path.isdir(lib_path):
            return

        existing = os.environ.get("DYLD_LIBRARY_PATH", "")
        if lib_path not in existing:
            os.environ["DYLD_LIBRARY_PATH"] = (
                f"{lib_path}:{existing}" if existing else lib_path
            )
    except Exception:
        # Keep startup resilient even when discovery fails.
        return
