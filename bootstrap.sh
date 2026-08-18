#!/usr/bin/env bash
set -e

echo "=== Initializing remanga Environment with uv ==="

# 1. Install or locate uv (ultra-fast standalone Python & venv manager)
if ! command -v uv >/dev/null 2>&1; then
    if [ -f "$HOME/.local/bin/uv" ]; then
        export PATH="$HOME/.local/bin:$PATH"
    elif [ -f "$HOME/.cargo/bin/uv" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
    else
        echo "[+] Installing standalone uv tool..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    fi
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[-] Failed to locate uv. Please ensure curl is installed and try again."
    exit 1
fi

echo "[+] Using uv version: $(uv --version)"

# 2. Provision hermetic Python 3.11 runtime (avoids Python 3.14 build/header issues)
echo "[+] Ensuring standalone Python 3.11 is provisioned..."
uv python install 3.11

# 3. Create isolated virtual environment
VENV_DIR=".venv"
echo "[+] Creating isolated virtual environment at $VENV_DIR with Python 3.11..."
uv venv "$VENV_DIR" --python 3.11

# 4. Install dependencies inside isolated venv using pre-compiled wheels
echo "[+] Installing PyTorch, torchaudio, and remanga dependencies..."
uv pip install --python "$VENV_DIR" -e .

# 5. Initialize config.json from config.example.json if missing
if [ ! -f "config.json" ]; then
    echo "[+] Initializing config.json from config.example.json..."
    cp config.example.json config.json
fi

# 6. Verify ffmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "[!] Warning: ffmpeg was not found on your system PATH."
    echo "    On Ubuntu/Debian, install it via: sudo apt install ffmpeg"
fi

# 7. Check & Download IndexTTS-2.5 weights from Hugging Face
CHECKPOINTS_DIR="checkpoints/indextts_2.5"
if [ ! -f "$CHECKPOINTS_DIR/config.yaml" ]; then
    echo "[+] IndexTTS-2.5 model weights not detected locally."
    echo "[+] Automatically downloading IndexTeam/IndexTTS-2.5 from Hugging Face into $CHECKPOINTS_DIR..."
    "$VENV_DIR/bin/python3" -c "
from huggingface_hub import snapshot_download
import os

target_dir = '$CHECKPOINTS_DIR'
os.makedirs(target_dir, exist_ok=True)
print('Downloading snapshot from IndexTeam/IndexTTS-2.5...')
snapshot_download(
    repo_id='IndexTeam/IndexTTS-2.5',
    local_dir=target_dir,
    local_dir_use_symlinks=False
)
print('✓ IndexTTS-2.5 weights downloaded successfully!')
"
else
    echo "[+] Found existing IndexTTS-2.5 model weights in $CHECKPOINTS_DIR."
fi

# 8. Create workspace directories
mkdir -p assets/voices assets/bgm projects

echo "=========================================================="
echo "✓ remanga environment initialized successfully!"
echo "  To use the CLI, run: ./run.sh --help"
echo "  To start the guided workflow, run: ./pipeline.sh"
echo "  Set your reference voice path in config.json ('spk_audio_prompt')"
echo "=========================================================="