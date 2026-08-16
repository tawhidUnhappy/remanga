#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "\033[1;34m=== Initializing remanga Environment ===\033[0m"

mkdir -p .tools

# 1. Clean up broken or incomplete virtual environments if present
if [ -d ".venv" ]; then
    if [ ! -f ".venv/bin/python" ] && [ ! -f ".venv/bin/python3" ] && [ ! -f ".venv/Scripts/python.exe" ]; then
        echo "Found broken or empty .venv directory, cleaning up..."
        rm -rf .venv
    fi
fi

# 2. Setup virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv .venv || python3 -m venv --without-pip .venv
    elif command -v python >/dev/null 2>&1; then
        python -m venv .venv || python -m venv --without-pip .venv
    else
        echo "Error: Python 3 is not installed or not in PATH."
        exit 1
    fi
fi

# 3. Locate Python executable in .venv
if [ -f ".venv/bin/python3" ]; then
    VENV_PYTHON=".venv/bin/python3"
elif [ -f ".venv/bin/python" ]; then
    VENV_PYTHON=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    VENV_PYTHON=".venv/Scripts/python.exe"
else
    echo "Error: Could not locate Python binary inside .venv."
    exit 1
fi

# 4. Ensure pip is available inside the virtual environment
if ! "$VENV_PYTHON" -m pip --version >/dev/null 2>&1; then
    echo "Bootstrapping pip inside virtual environment..."
    "$VENV_PYTHON" -m ensurepip --default-pip 2>/dev/null || {
        echo "Downloading pip bootstrap utility..."
        curl -sSL https://bootstrap.pypa.io/get-pip.py -o .tools/get-pip.py
        "$VENV_PYTHON" .tools/get-pip.py
        rm -f .tools/get-pip.py
    }
fi

echo "Installing project dependencies..."
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -e .

# 5. Initialize config.json from config.example.json if not present
if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    cp config.example.json config.json
    echo "Created config.json from config.example.json"
fi

# 6. Set executable permissions
chmod +x run.sh pipeline.sh bootstrap.sh 2>/dev/null || true

echo -e "\033[1;32m=== remanga Environment Ready! ===\033[0m"