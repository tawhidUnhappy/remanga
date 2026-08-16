#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Add portable tools to PATH if present
if [ -d "$SCRIPT_DIR/.tools" ]; then
    export PATH="$SCRIPT_DIR/.tools:$PATH"
fi

# Select Python binary
if [ -f "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
elif [ -f "$SCRIPT_DIR/.venv/Scripts/python.exe" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/Scripts/python.exe"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    PYTHON_BIN="python"
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

exec "$PYTHON_BIN" -m remanga.cli "$@"