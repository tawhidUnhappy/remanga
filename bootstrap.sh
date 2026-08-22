#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Initializing 100% Self-Contained remanga Environment ==="

BIN_DIR="$SCRIPT_DIR/bin"
CACHE_DIR="$SCRIPT_DIR/.cache"
VENV_DIR="$SCRIPT_DIR/.venv"
INDEXTTS_VENV_DIR="$SCRIPT_DIR/.venv-indextts"
MAGI_VENV_DIR="$SCRIPT_DIR/.venv-magi"

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

# 3. Provision standalone Python 3.11 & create the three isolated virtual
# environments: the main env (remanga's own lightweight core), plus one per
# heavy ML dependency so their conflicting requirements never have to share a
# resolution - IndexTTS-2.5 and MAGI v3 each pin their own torch/transformers
# stack, sometimes incompatibly (MAGI v3 needs transformers<4.52; nothing
# guarantees IndexTTS or some future tool won't need something newer). The
# storage trade-off (three venvs instead of one) buys permanent isolation
# instead of a pin that has to be re-asserted and re-verified by hand every
# time one tool's install could clobber another's. See remanga/venvs.py for
# how the main env locates and talks to these two as subprocesses.
echo "[+] Provisioning standalone Python 3.11 runtime..."
"$BIN_DIR/uv" python install 3.11

echo "[+] Creating main environment ($VENV_DIR)..."
"$BIN_DIR/uv" venv "$VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$VENV_DIR" -e .

echo "[+] Creating isolated IndexTTS-2.5 environment ($INDEXTTS_VENV_DIR)..."
"$BIN_DIR/uv" venv "$INDEXTTS_VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$INDEXTTS_VENV_DIR" torch torchaudio transformers accelerate huggingface-hub modelscope
"$BIN_DIR/uv" pip install --python "$INDEXTTS_VENV_DIR" git+https://github.com/index-tts/index-tts.git

echo "[+] Creating isolated MAGI v3 environment ($MAGI_VENV_DIR)..."
"$BIN_DIR/uv" venv "$MAGI_VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$MAGI_VENV_DIR" "torch" "transformers<4.52.0" timm shapely pytorch-metric-learning huggingface-hub pillow numpy

# 4. Initialize config.json from config.example.json if missing
if [ ! -f "config.json" ]; then
    cp config.example.json config.json
fi

# 5. Verify and download model weights (IndexTTS-2.5 via ModelScope/HF, MAGI v3
# via HF) - each downloaded and verified using its own isolated environment.
"$VENV_DIR/bin/python3" -m remanga.cli setup-models

echo "=========================================================="
echo "✓ remanga hermetic environment initialized successfully!"
echo "  To start the guided production wizard, run: ./pipeline.sh"
echo "  To use the step-by-step CLI, run: ./run.sh --help"
echo "=========================================================="