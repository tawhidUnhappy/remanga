#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[-] Virtual environment not found. Running bootstrap.sh first..."
    bash "$SCRIPT_DIR/bootstrap.sh"
fi

export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
exec "$VENV_PYTHON" -m remanga.cli "$@"