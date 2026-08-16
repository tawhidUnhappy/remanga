#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\033[1;34m=== Initializing remanga Environment ===\033[0m"

mkdir -p .tools

# Setup virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv
    else
        python -m venv .venv
    fi
fi

if [ -f ".venv/bin/pip" ]; then
    PIP_BIN=".venv/bin/pip"
else
    PIP_BIN=".venv/Scripts/pip.exe"
fi

echo "Installing project dependencies..."
"$PIP_BIN" install --upgrade pip
"$PIP_BIN" install -e .

# Initialize config.json from config.example.json if not present
if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    cp config.example.json config.json
    echo "Created config.json from config.example.json"
fi

chmod +x run.sh pipeline.sh bootstrap.sh 2>/dev/null || true

echo -e "\033[1;32m=== remanga Environment Ready! ===\033[0m"