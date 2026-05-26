#!/bin/bash
# PulsimGui launcher — fixes Qt cocoa plugin path on macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve python executable from active venv, project .venv, or system python3.
if [ -n "$VIRTUAL_ENV" ]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python3"
elif [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
    # shellcheck disable=SC1091
    source "$SCRIPT_DIR/.venv/bin/activate"
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
else
    PYTHON_BIN="$(command -v python3 || true)"
fi

if [ -z "$PYTHON_BIN" ] || [ ! -x "$PYTHON_BIN" ]; then
    echo "Error: python3 not found. Install Python 3.10+ and try again."
    exit 1
fi

if ! "$PYTHON_BIN" -c "import PySide6, pulsimgui" >/dev/null 2>&1; then
    echo "Error: missing runtime dependencies in current Python environment."
    echo "Create the project virtual environment and install dev dependencies:"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  python3 -m pip install --upgrade pip"
    echo "  python3 -m pip install -e '.[dev]'"
    exit 1
fi

# Resolve paths from installed PySide6
PYSIDE6_DIR="$("$PYTHON_BIN" -c "import PySide6, os; print(os.path.dirname(PySide6.__file__))")"
QT_BASE="$PYSIDE6_DIR/Qt"

export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_BASE/plugins/platforms"
export QT_PLUGIN_PATH="$QT_BASE/plugins"
export DYLD_LIBRARY_PATH="$QT_BASE/lib:${DYLD_LIBRARY_PATH:-}"
export DYLD_FRAMEWORK_PATH="$QT_BASE/lib:${DYLD_FRAMEWORK_PATH:-}"

exec "$PYTHON_BIN" -m pulsimgui "$@"
