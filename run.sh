#!/bin/bash
# PulsimGui launcher — fixes Qt cocoa plugin path on macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if not already active
if [ -z "$VIRTUAL_ENV" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Resolve paths from installed PySide6
PYSIDE6_DIR="$(python3 -c "import PySide6, os; print(os.path.dirname(PySide6.__file__))")"
QT_BASE="$PYSIDE6_DIR/Qt"

export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_BASE/plugins/platforms"
export QT_PLUGIN_PATH="$QT_BASE/plugins"
export DYLD_LIBRARY_PATH="$QT_BASE/lib:${DYLD_LIBRARY_PATH:-}"
export DYLD_FRAMEWORK_PATH="$QT_BASE/lib:${DYLD_FRAMEWORK_PATH:-}"

exec python3 -m pulsimgui "$@"
