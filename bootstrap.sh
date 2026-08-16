#!/usr/bin/env bash
set -euo pipefail

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${SCRIPT_DIR}/.tools"
BIN_DIR="${TOOLS_DIR}/bin"
mkdir -p "${BIN_DIR}"

echo -e "${BLUE}==> [remanga] Initializing Standalone Isolated Environment...${NC}"

# 1. Install isolated portable 'uv' if not present
if [ ! -f "${BIN_DIR}/uv" ]; then
    echo -e "${YELLOW}--> Downloading standalone uv binary into .tools/...${NC}"
    export CARGO_DIST_FORCE_INSTALLERS=1
    curl -LsSf https://astral.sh/uv/install.sh | INSTALLER_NO_MODIFY_PATH=1 UV_INSTALL_DIR="${BIN_DIR}" sh
fi

export PATH="${BIN_DIR}:${PATH}"

# 2. Check or download portable static ffmpeg if missing
if ! command -v ffmpeg >/dev/null 2>&1 && [ ! -f "${BIN_DIR}/ffmpeg" ]; then
    echo -e "${YELLOW}--> ffmpeg not found on host. Downloading isolated static build...${NC}"
    OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
    ARCH="$(uname -m)"

    if [ "${OS}" = "linux" ] && [ "${ARCH}" = "x86_64" ]; then
        curl -LsSf "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -o "${TOOLS_DIR}/ffmpeg.tar.xz"
        tar -xf "${TOOLS_DIR}/ffmpeg.tar.xz" -C "${TOOLS_DIR}" --strip-components=1
        mv "${TOOLS_DIR}/ffmpeg" "${TOOLS_DIR}/ffprobe" "${BIN_DIR}/"
        rm -rf "${TOOLS_DIR}/ffmpeg.tar.xz" "${TOOLS_DIR}/manpages" "${TOOLS_DIR}/model" "${TOOLS_DIR}/readme.txt"
    elif [ "${OS}" = "darwin" ]; then
        echo -e "${YELLOW}Please ensure ffmpeg is installed via brew or present in system PATH.${NC}"
    fi
fi

# 3. Create isolated virtual environment using Python 3.12
echo -e "${BLUE}--> Provisioning isolated Python 3.12 virtual environment...${NC}"
"${BIN_DIR}/uv" venv --python 3.12 "${SCRIPT_DIR}/.venv"

# 4. Synchronize dependencies
echo -e "${BLUE}--> Installing dependencies...${NC}"
"${BIN_DIR}/uv" pip install --python "${SCRIPT_DIR}/.venv/bin/python" -e .

# 5. Initialize config if absent
if [ ! -f "${SCRIPT_DIR}/config.json" ]; then
    cp "${SCRIPT_DIR}/config.example.json" "${SCRIPT_DIR}/config.json"
    echo -e "${GREEN}--> Created default config.json from template.${NC}"
fi

echo -e "${GREEN}==> [remanga] Setup Complete! Run ./run.sh or ./pipeline.sh to begin.${NC}"