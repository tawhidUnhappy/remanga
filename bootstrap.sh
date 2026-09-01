#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Initializing 100% Self-Contained remanga Environment ==="

BIN_DIR="$SCRIPT_DIR/bin"
CACHE_DIR="$SCRIPT_DIR/.cache"
TOOLS_DIR="$SCRIPT_DIR/.tools"
VENV_DIR="$SCRIPT_DIR/.venv"
INDEXTTS_VENV_DIR="$TOOLS_DIR/venv-indextts"
AUDIO8_VENV_DIR="$TOOLS_DIR/venv-audio8"
MAGI_VENV_DIR="$TOOLS_DIR/venv-magi"

mkdir -p "$BIN_DIR" "$CACHE_DIR/uv" "$CACHE_DIR/huggingface" "$CACHE_DIR/torch" "$TOOLS_DIR" assets/voices assets/bgm projects

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
#
# Deliberately pinned to a specific dated build, NOT the "latest" rolling tag.
# BtbN only ever publishes master-branch snapshots (there's no separate stable
# channel), each compiled against whatever NVIDIA NVENC SDK/driver-API version
# was current on build day - and NVENC's minimum required driver only ever
# goes UP over time. "latest" therefore silently raises the minimum driver
# GPU rendering needs every single day it's rebuilt, with no warning: a user
# whose driver was perfectly current a few months ago can suddenly get a
# bundled ffmpeg whose NVENC refuses to open ("Driver does not support the
# required nvenc API version") on a perfectly real, working GPU. NVENC is
# backward-compatible in the other direction though - a build pinned to an
# OLDER, known-good snapshot keeps working fine on NEWER drivers too - so
# pinning trades a few months of ffmpeg changelog (nothing this project's
# actual usage - concat demux, h264_nvenc/libx264, aac - needs) for GPU
# encoding that just works out of the box for a much wider range of driver
# versions. remanga/video/render.py additionally falls back to a system
# ffmpeg for GPU encoding specifically if even this pinned build's NVENC
# doesn't work - see its _resolve_gpu_ffmpeg() - as a last-resort safety net,
# not the primary way GPU rendering is meant to work.
#
# To bump this pin (e.g. to pick up newer codec/bugfix work), pick a recent
# tag from https://github.com/BtbN/FFmpeg-Builds/releases, find its actual
# linux64-gpl asset filename (NOT "master-latest" - that name only exists on
# the "latest" alias) via:
#   curl -s https://github.com/BtbN/FFmpeg-Builds/releases/expanded_assets/<tag> \
#     | grep -oE 'ffmpeg-[^"]*linux64-gpl\.tar\.xz' | grep -v shared
# and test its h264_nvenc against your own driver before trusting it further.
if [ ! -f "$BIN_DIR/ffmpeg" ] || [ ! -f "$BIN_DIR/ffprobe" ]; then
    echo "[+] Downloading isolated static FFmpeg into $BIN_DIR..."
    FFMPEG_TAG="autobuild-2026-03-31-13-11"
    FFMPEG_ASSET="ffmpeg-N-123777-g53537f6cf5-linux64-gpl.tar.xz"
    FFMPEG_URL="https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFMPEG_TAG/$FFMPEG_ASSET"
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

# 3. Provision standalone Python 3.11 & create the four isolated virtual
# environments: the main env (remanga's own lightweight core) at the repo
# root, plus one per heavy ML dependency, tucked under .tools/ for easy
# management, so their conflicting requirements never have to share a
# resolution - IndexTTS-2.5, Audio8 TTS, and MAGI v3 each pin their own
# torch/transformers stack, sometimes incompatibly (MAGI v3 needs
# transformers<4.52; Audio8 needs transformers>=4.57; nothing guarantees any
# two of them would ever agree on one shared resolution). The storage
# trade-off (four venvs instead of one) buys permanent isolation
# instead of a pin that has to be re-asserted and re-verified by hand every
# time one tool's install could clobber another's. Nothing "activates" these -
# the main env only ever invokes `.tools/venv-<tool>/bin/python` directly as a
# subprocess (see remanga/venvs.py), which needs no shell activation step at all.
echo "[+] Provisioning standalone Python 3.11 runtime..."
"$BIN_DIR/uv" python install 3.11

echo "[+] Creating main environment ($VENV_DIR)..."
"$BIN_DIR/uv" venv "$VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$VENV_DIR" -e .

echo "[+] Creating isolated IndexTTS-2.5 environment ($INDEXTTS_VENV_DIR)..."
"$BIN_DIR/uv" venv "$INDEXTTS_VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$INDEXTTS_VENV_DIR" torch torchaudio transformers accelerate huggingface-hub modelscope
"$BIN_DIR/uv" pip install --python "$INDEXTTS_VENV_DIR" git+https://github.com/index-tts/index-tts.git

# Second, alternative TTS engine - Audio8/Audio8-TTS-Preview-0.1b on Hugging
# Face (config.json's tts.engine picks which one actually runs; see
# remanga/config.py's TTS_ENGINES and remanga/audio/synth.py). Its own
# isolated venv, same reasoning as IndexTTS-2.5's: a `transformers>=4.57,<5`
# pin (for its trust_remote_code=True custom modeling files) that has no
# business sharing a resolution with IndexTTS's own pin, let alone MAGI v3's
# `transformers<4.52`. Provisioned unconditionally alongside the other two
# so switching engines later (config.json, or `setup-config`) never requires
# re-running bootstrap.sh - only the weights themselves (checkpoints/
# audio8_tts_0.1b/, ~1.7GB) are fetched lazily, the first time this engine
# is actually selected and used (ModelManager.ensure_model(), same lazy
# pattern IndexTTS-2.5's own weights already follow).
echo "[+] Creating isolated Audio8 TTS environment ($AUDIO8_VENV_DIR)..."
"$BIN_DIR/uv" venv "$AUDIO8_VENV_DIR" --python 3.11 --allow-existing
"$BIN_DIR/uv" pip install --python "$AUDIO8_VENV_DIR" "torch>=2.5.0" "torchaudio>=2.5.0" "transformers>=4.57.0,<5" "soundfile>=0.12" "safetensors>=0.4" accelerate huggingface-hub

# Audio8 is Falcon-H1-based (a Mamba/state-space hybrid, not a plain
# transformer) - its speed depends on the fused `mamba-ssm`/`causal-conv1d`
# CUDA kernels for the state-space recurrence. Without them,
# audio8_worker.py's `transformers` call silently falls back to a naive,
# unfused, token-by-token recurrence loop that's dramatically slower
# (measured ~2-3x slower per panel on an RTX 3060) - small parameter count
# barely matters on that path. Best-effort only: these are genuine CUDA
# extension builds (need nvcc matching torch's CUDA major version, ~10-20
# min combined) and the worker already degrades gracefully to the naive
# path if they're missing/fail to build, so a failure here must never abort
# the rest of bootstrap.sh.
echo "[+] Building Audio8's fused Mamba CUDA kernels (mamba-ssm, causal-conv1d) - this speeds up synthesis significantly and takes ~10-20 min; safe to skip on failure, Audio8 still works without it..."
(
    set -e
    # torch's cpp_extension build only requires nvcc's MAJOR version to match
    # torch.version.cuda (a minor mismatch is just a warning) - installing
    # `nvidia-cuda-nvcc` into this same venv guarantees that match without
    # touching the system CUDA toolkit (which may be a different, older
    # major version - see this script's comment above the FFmpeg/NVENC pin
    # for the same kind of driver/toolkit-version trap).
    "$BIN_DIR/uv" pip install --python "$AUDIO8_VENV_DIR" nvidia-cuda-nvcc
    NVCC_CUDA_HOME="$("$AUDIO8_VENV_DIR/bin/python" -c "import nvidia.cuda_nvcc as m, pathlib; print(pathlib.Path(m.__file__).parent)" 2>/dev/null || true)"
    if [ -z "$NVCC_CUDA_HOME" ]; then
        # Fallback: locate it by the actual nvcc binary pip just installed,
        # since the importable package name has moved between releases.
        NVCC_BIN="$(find "$AUDIO8_VENV_DIR/lib" -maxdepth 5 -type f -path "*/nvidia/*/bin/nvcc" 2>/dev/null | head -n 1)"
        [ -n "$NVCC_BIN" ] && NVCC_CUDA_HOME="$(dirname "$(dirname "$NVCC_BIN")")"
    fi
    [ -n "$NVCC_CUDA_HOME" ] && [ -x "$NVCC_CUDA_HOME/bin/nvcc" ] || { echo "[-] Could not locate a usable nvcc after installing nvidia-cuda-nvcc - skipping fused kernels."; exit 1; }

    export CUDA_HOME="$NVCC_CUDA_HOME"
    export PATH="$CUDA_HOME/bin:$PATH"
    # Target this machine's actual GPU compute capability (falls back to a
    # broad common-GPU list if nvidia-smi isn't available) so nvcc doesn't
    # waste the ~10-20 min build compiling kernels for architectures that
    # will never run here.
    export TORCH_CUDA_ARCH_LIST="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n 1 | tr -d ' ' || true)"
    [ -z "$TORCH_CUDA_ARCH_LIST" ] && TORCH_CUDA_ARCH_LIST="7.5;8.0;8.6;8.9;9.0"
    export MAX_JOBS=4

    "$BIN_DIR/uv" pip install --python "$AUDIO8_VENV_DIR" causal-conv1d --no-build-isolation
    "$BIN_DIR/uv" pip install --python "$AUDIO8_VENV_DIR" mamba-ssm --no-build-isolation
) && echo "[+] Fused Mamba CUDA kernels installed - Audio8 will use the fast path." \
  || echo "[-] Skipping fused Mamba CUDA kernels (build failed) - Audio8 will still work, just on its slower fallback path."

echo "[+] Creating isolated MAGI v3 environment ($MAGI_VENV_DIR)..."
"$BIN_DIR/uv" venv "$MAGI_VENV_DIR" --python 3.11 --allow-existing
# einops/matplotlib: undeclared imports MAGI v3's remote modeling code needs
# beyond what its own requirements list - remanga/webui/magi_assist.py will
# auto-install anything still missing on first load, but listing the ones
# already known here saves that extra round-trip.
"$BIN_DIR/uv" pip install --python "$MAGI_VENV_DIR" torch "transformers<4.52.0" timm shapely pytorch-metric-learning huggingface-hub pillow numpy einops matplotlib

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