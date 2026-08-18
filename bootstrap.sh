#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Initializing 100% Self-Contained remanga Environment ==="

BIN_DIR="$SCRIPT_DIR/bin"
CACHE_DIR="$SCRIPT_DIR/.cache"
VENV_DIR="$SCRIPT_DIR/.venv"

mkdir -p "$BIN_DIR" "$CACHE_DIR/uv" "$CACHE_DIR/huggingface" "$CACHE_DIR/torch" assets/voices assets/bgm projects

# Force all caches strictly inside remanga directory
export PATH="$BIN_DIR:$PATH"
export UV_CACHE_DIR="$CACHE_DIR/uv"
export HF_HOME="$CACHE_DIR/huggingface"
export TRANSFORMERS_CACHE="$CACHE_DIR/huggingface"
export TORCH_HOME="$CACHE_DIR/torch"
unset HF_HUB_ENABLE_HF_TRANSFER

# 1. Install standalone uv locally inside remanga/bin
if [ ! -f "$BIN_DIR/uv" ]; then
    echo "[+] Installing standalone uv binary into $BIN_DIR/uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env CARGO_HOME="$SCRIPT_DIR" UV_INSTALL_DIR="$BIN_DIR" sh
fi

echo "[+] Using local uv: $("$BIN_DIR/uv" --version)"

# 2. Download standalone static FFmpeg and FFprobe from BtbN GitHub into remanga/bin
if [ ! -f "$BIN_DIR/ffmpeg" ] || [ ! -f "$BIN_DIR/ffprobe" ]; then
    echo "[+] Downloading isolated static FFmpeg into $BIN_DIR..."
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

    if [ ! -f "$BIN_DIR/ffmpeg" ]; then
        if command -v ffmpeg >/dev/null 2>&1; then
            cp "$(command -v ffmpeg)" "$BIN_DIR/ffmpeg"
            cp "$(command -v ffprobe 2>/dev/null || command -v ffmpeg)" "$BIN_DIR/ffprobe"
            chmod +x "$BIN_DIR/ffmpeg" "$BIN_DIR/ffprobe"
        else
            echo "[-] Error: Failed to setup FFmpeg binaries."
            exit 1
        fi
    fi
fi

# 3. Provision standalone Python 3.11 & create virtual environment
echo "[+] Provisioning standalone Python 3.11 runtime..."
"$BIN_DIR/uv" python install 3.11
"$BIN_DIR/uv" venv "$VENV_DIR" --python 3.11 --allow-existing

# 4. Install dependencies inside isolated venv
echo "[+] Installing remanga and machine learning dependencies..."
"$BIN_DIR/uv" pip install --python "$VENV_DIR" -e .

# 5. Initialize config.json from config.example.json if missing
if [ ! -f "config.json" ]; then
    cp config.example.json config.json
fi

# 6. Let Hugging Face verify/download model weights natively
"$VENV_DIR/bin/python3" -m remanga.cli setup-models

echo "=========================================================="
echo "✓ remanga hermetic environment initialized successfully!"
echo "  To start the guided production wizard, run: ./pipeline.sh"
echo "  To use the step-by-step CLI, run: ./run.sh --help"
echo "=========================================================="