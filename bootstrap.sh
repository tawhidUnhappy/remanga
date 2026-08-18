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
unset HF_HUB_ENABLE_HF_TRANSFER

# 2. Install standalone uv locally inside remanga/bin
if [ ! -f "$BIN_DIR/uv" ]; then
    echo "[+] Downloading standalone uv binary into $BIN_DIR/uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env CARGO_HOME="$SCRIPT_DIR" UV_INSTALL_DIR="$BIN_DIR" sh
fi

echo "[+] Using local uv: $("$BIN_DIR/uv" --version)"

# 3. Download standalone static FFmpeg and FFprobe from BtbN GitHub into remanga/bin
if [ ! -f "$BIN_DIR/ffmpeg" ] || [ ! -f "$BIN_DIR/ffprobe" ]; then
    echo "[+] Downloading isolated static FFmpeg (GPL/NVENC) into $BIN_DIR..."
    FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"
    FFMPEG_TMP="$CACHE_DIR/ffmpeg.tar.xz"

    if curl -fL -A "Mozilla/5.0" "$FFMPEG_URL" -o "$FFMPEG_TMP" 2>/dev/null; then
        tar -xf "$FFMPEG_TMP" -C "$CACHE_DIR"
        EXTRACTED_DIR="$(find "$CACHE_DIR" -maxdepth 1 -type d -name "ffmpeg-*-linux64-gpl" | head -n 1)"
        if [ -n "$EXTRACTED_DIR" ] && [ -d "$EXTRACTED_DIR" ]; then
            cp "$EXTRACTED_DIR/bin/ffmpeg" "$BIN_DIR/ffmpeg"
            cp "$EXTRACTED_DIR/bin/ffprobe" "$BIN_DIR/ffprobe"
            chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
            rm -rf "$FFMPEG_TMP" "$EXTRACTED_DIR"
            echo "[+] Static FFmpeg and FFprobe installed locally in $BIN_DIR"
        fi
    fi

    # Fallback to system ffmpeg copy if download was blocked
    if [ ! -f "$BIN_DIR/ffmpeg" ]; then
        if command -v ffmpeg >/dev/null 2>&1; then
            echo "[!] Using copy of system ffmpeg as local binary fallback..."
            cp "$(command -v ffmpeg)" "$BIN_DIR/ffmpeg"
            cp "$(command -v ffprobe 2>/dev/null || command -v ffmpeg)" "$BIN_DIR/ffprobe"
            chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
        else
            echo "[-] Error: Failed to download static FFmpeg and no system FFmpeg found."
            exit 1
        fi
    fi
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
"$BIN_DIR/uv" pip install --python "$VENV_DIR" modelscope "huggingface-hub[cli]"

# 7. Initialize config.json from config.example.json if missing
if [ ! -f "config.json" ]; then
    echo "[+] Creating default config.json from config.example.json..."
    cp config.example.json config.json
fi

# 8. High-Speed Download for IndexTTS-2.5 weights
if [ ! -f "$CHECKPOINTS_DIR/config.yaml" ]; then
    echo "[+] Downloading IndexTTS-2.5 model weights into $CHECKPOINTS_DIR..."
    
    # Try high-speed ModelScope first (fastest in Asia/international), fallback to Hugging Face CLI with resume
    "$VENV_DIR/bin/python3" -c "
import sys
from pathlib import Path

target_dir = Path('$CHECKPOINTS_DIR')
target_dir.mkdir(parents=True, exist_ok=True)

success = False
try:
    print('[+] Connecting to high-speed mirror (ModelScope)...')
    from modelscope import snapshot_download as ms_download
    ms_download('IndexTeam/IndexTTS-2.5', local_dir=str(target_dir.resolve()))
    success = True
    print('✓ IndexTTS-2.5 weights downloaded via ModelScope mirror!')
except Exception as e:
    print(f'[!] ModelScope mirror notice: {e}. Switching to standard Hugging Face CLI...')

if not success or not (target_dir / 'config.yaml').exists():
    from huggingface_hub import snapshot_download as hf_download
    print('[+] Downloading directly from Hugging Face with clean progress bar...')
    hf_download(
        repo_id='IndexTeam/IndexTTS-2.5',
        local_dir=str(target_dir.resolve()),
        local_dir_use_symlinks=False,
        resume_download=True
    )
    print('✓ IndexTTS-2.5 weights downloaded via Hugging Face!')
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