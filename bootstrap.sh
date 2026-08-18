#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Initializing 100% Self-Contained remanga Environment ==="

# 1. Ensure local directory structure
BIN_DIR="$SCRIPT_DIR/bin"
CACHE_DIR="$SCRIPT_DIR/.cache"
VENV_DIR="$SCRIPT_DIR/.venv"
CHECKPOINTS_DIR="$SCRIPT_DIR/checkpoints/indextts_2.5"

mkdir -p "$BIN_DIR" "$CACHE_DIR/uv" "$CACHE_DIR/huggingface" "$CACHE_DIR/torch" "$CHECKPOINTS_DIR" assets/voices assets/bgm projects

# Force all caches strictly inside remanga directory
export PATH="$BIN_DIR:$PATH"
export UV_CACHE_DIR="$CACHE_DIR/uv"
export HF_HOME="$CACHE_DIR/huggingface"
export TRANSFORMERS_CACHE="$CACHE_DIR/huggingface"
export TORCH_HOME="$CACHE_DIR/torch"
export HF_HUB_ENABLE_HF_TRANSFER=1

# 2. Install standalone uv locally inside remanga/bin
if [ ! -f "$BIN_DIR/uv" ]; then
    echo "[+] Downloading standalone uv binary into $BIN_DIR/uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env CARGO_HOME="$SCRIPT_DIR" UV_INSTALL_DIR="$BIN_DIR" sh
fi

echo "[+] Using local uv: $("$BIN_DIR/uv" --version)"

# 3. Download standalone static FFmpeg and FFprobe into remanga/bin
if [ ! -f "$BIN_DIR/ffmpeg" ] || [ ! -f "$BIN_DIR/ffprobe" ]; then
    echo "[+] Downloading isolated static FFmpeg binaries into $BIN_DIR..."
    FFMPEG_TMP="$CACHE_DIR/ffmpeg_static.tar.xz"
    curl -L "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" -o "$FFMPEG_TMP"
    tar -xf "$FFMPEG_TMP" -C "$CACHE_DIR"
    FFMPEG_EXTRACTED="$(find "$CACHE_DIR" -maxdepth 1 -type d -name "ffmpeg-*-amd64-static" | head -n 1)"
    cp "$FFMPEG_EXTRACTED/ffmpeg" "$BIN_DIR/ffmpeg"
    cp "$FFMPEG_EXTRACTED/ffprobe" "$BIN_DIR/ffprobe"
    chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
    rm -rf "$FFMPEG_TMP" "$FFMPEG_EXTRACTED"
    echo "[+] Static FFmpeg and FFprobe installed locally in $BIN_DIR"
fi

# 4. Provision standalone Python 3.11 inside remanga/.cache
echo "[+] Provisioning standalone Python 3.11 runtime..."
"$BIN_DIR/uv" python install 3.11

# 5. Create local virtual environment
echo "[+] Creating isolated virtual environment in $VENV_DIR..."
"$BIN_DIR/uv" venv "$VENV_DIR" --python 3.11

# 6. Install project dependencies into isolated venv
echo "[+] Installing remanga and machine learning dependencies..."
"$BIN_DIR/uv" pip install --python "$VENV_DIR" -e .

# 7. Initialize config.json from config.example.json if missing
if [ ! -f "config.json" ]; then
    echo "[+] Creating default config.json from config.example.json..."
    cp config.example.json config.json
fi

# 8. High-Speed Parallel Download for IndexTTS-2.5 weights via hf-transfer
if [ ! -f "$CHECKPOINTS_DIR/config.yaml" ]; then
    echo "[+] Turbo-downloading IndexTeam/IndexTTS-2.5 from Hugging Face via hf-transfer..."
    "$VENV_DIR/bin/python3" -c "
import os
from huggingface_hub import snapshot_download

target_dir = '$CHECKPOINTS_DIR'
os.makedirs(target_dir, exist_ok=True)
os.environ['HF_HUB_ENABLE_HF_TRANSFER'] = '1'

print('Connecting to Hugging Face with parallel multi-connection streams...')
snapshot_download(
    repo_id='IndexTeam/IndexTTS-2.5',
    local_dir=target_dir,
    local_dir_use_symlinks=False,
    max_workers=8
)
print('✓ IndexTTS-2.5 weights downloaded successfully!')
"
else
    echo "[+] Found existing IndexTTS-2.5 model weights in $CHECKPOINTS_DIR."
fi

echo "=========================================================="
echo "✓ remanga hermetic environment initialized successfully!"
echo "  All binaries, Python runtimes, and caches are local to this folder."
echo "  To start the guided production wizard, run: ./pipeline.sh"
echo "  To use the step-by-step CLI, run: ./run.sh --help"
echo "=========================================================="