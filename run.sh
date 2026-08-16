#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${SCRIPT_DIR}/.tools/bin"
VENV_BIN="${SCRIPT_DIR}/.venv/bin"

if [ ! -d "${VENV_BIN}" ]; then
    echo "[!] Environment not found. Running bootstrap.sh first..."
    bash "${SCRIPT_DIR}/bootstrap.sh"
fi

export PATH="${VENV_BIN}:${BIN_DIR}:${PATH}"
export PYTHONPATH="${SCRIPT_DIR}:${PYTHONPATH:-}"

exec "${VENV_BIN}/python" -m remanga.cli "$@"