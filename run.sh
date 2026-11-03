#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "[-] Virtual environment not found. Running bootstrap.sh first..."
    bash "$SCRIPT_DIR/bootstrap.sh"
fi

# Lock all environment variables and PATH strictly to remanga root
export PATH="$SCRIPT_DIR/bin:$PATH"
export UV_CACHE_DIR="$SCRIPT_DIR/.cache/uv"
export HF_HOME="$SCRIPT_DIR/.cache/huggingface"
export TRANSFORMERS_CACHE="$SCRIPT_DIR/.cache/huggingface"
export TORCH_HOME="$SCRIPT_DIR/.cache/torch"
export HF_HUB_ENABLE_HF_TRANSFER=1
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

exec "$VENV_PYTHON" -m remanga.cli "$@"