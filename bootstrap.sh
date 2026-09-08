#!/usr/bin/env bash
#
# Provisions a complete, self-contained remanga environment on whatever
# machine it is run on: Linux, macOS or Windows (Git Bash / MSYS), x86_64 or
# arm64, with an NVIDIA GPU, an AMD ROCm GPU, Apple Silicon, or no GPU at
# all. Nothing here is specific to the machine it was written on.
#
# Everything hardware-shaped is decided in ONE place - remanga/hardware.py -
# and read back here as shell variables. That module runs on a bare
# interpreter with no dependencies, so it can answer "what is this machine"
# before a single package has been installed, and the application imports the
# same module later so the installer and the app can never disagree.
#
# Failure policy: this script does NOT use `set -e`. Provisioning is a long
# sequence of steps of very different importance - failing to build an
# optional CUDA kernel must not abort a run that has already downloaded
# several GB of working environment. Critical steps call `die`, optional ones
# go through `try_step` and only warn. The summary at the end says what
# actually happened.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

BIN_DIR="$SCRIPT_DIR/bin"
CACHE_DIR="$SCRIPT_DIR/.cache"
TOOLS_DIR="$SCRIPT_DIR/.tools"
VENV_DIR="$SCRIPT_DIR/.venv"
INDEXTTS_VENV_DIR="$TOOLS_DIR/venv-indextts"
AUDIO8_VENV_DIR="$TOOLS_DIR/venv-audio8"
MAGI_VENV_DIR="$TOOLS_DIR/venv-magi"
DEEPSEEK_OCR_VENV_DIR="$TOOLS_DIR/venv-deepseek-ocr"

WARNINGS=()

say()  { printf '[+] %s\n' "$*"; }
warn() { printf '[-] %s\n' "$*" >&2; WARNINGS+=("$*"); }
die()  { printf '\n[!] FATAL: %s\n' "$*" >&2; exit 1; }

# Runs an optional step. Its failure is recorded and reported at the end,
# but never stops provisioning - see the failure policy above.
try_step() {
    local label="$1"; shift
    if "$@"; then
        return 0
    fi
    warn "$label failed - continuing without it."
    return 1
}

echo "=== Initializing self-contained remanga environment ==="

mkdir -p "$BIN_DIR" "$CACHE_DIR/uv" "$CACHE_DIR/huggingface" "$CACHE_DIR/torch" \
         "$TOOLS_DIR" assets/voices assets/bgm projects || die "could not create working directories"

# Every cache stays inside the repo, so provisioning never writes to (or is
# poisoned by) a shared machine-wide cache.
export PATH="$BIN_DIR:$PATH"
export UV_CACHE_DIR="$CACHE_DIR/uv"
export HF_HOME="$CACHE_DIR/huggingface"
export TORCH_HOME="$CACHE_DIR/torch"
unset HF_HUB_ENABLE_HF_TRANSFER

# ---------------------------------------------------------------------------
# 1. Local uv
# ---------------------------------------------------------------------------
UV_EXE="uv"
case "$(uname -s 2>/dev/null || echo unknown)" in
    MINGW*|MSYS*|CYGWIN*) UV_EXE="uv.exe" ;;
esac

if [ ! -x "$BIN_DIR/$UV_EXE" ]; then
    say "Installing standalone uv into $BIN_DIR..."
    if command -v curl >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | env CARGO_HOME="$SCRIPT_DIR" UV_INSTALL_DIR="$BIN_DIR" sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- https://astral.sh/uv/install.sh | env CARGO_HOME="$SCRIPT_DIR" UV_INSTALL_DIR="$BIN_DIR" sh
    else
        die "neither curl nor wget is available - install one, or install uv yourself and put it in $BIN_DIR"
    fi
fi
[ -x "$BIN_DIR/$UV_EXE" ] || die "uv did not install into $BIN_DIR - see https://docs.astral.sh/uv/getting-started/installation/"
UV="$BIN_DIR/$UV_EXE"
say "Using local uv: $("$UV" --version)"

say "Provisioning standalone Python 3.11 runtime..."
"$UV" python install 3.11 || die "could not provision Python 3.11 via uv"

# ---------------------------------------------------------------------------
# 2. Detect the machine
# ---------------------------------------------------------------------------
# Run through uv's own managed interpreter with --no-project, so this works
# before .venv exists and regardless of what (if any) system python is
# installed. remanga/hardware.py is stdlib-only precisely so this is possible.
say "Detecting hardware..."
DETECTED="$("$UV" run --no-project --python 3.11 "$SCRIPT_DIR/remanga/hardware.py" --shell 2>/dev/null)"
if [ -z "$DETECTED" ]; then
    warn "hardware detection failed - falling back to CPU-only builds."
    REMANGA_OS="linux"; REMANGA_ARCH="x86_64"; REMANGA_ACCEL="cpu"
    REMANGA_TORCH_BACKEND="cpu"; REMANGA_VIDEO_ENCODER="libx264"
    REMANGA_FFMPEG_KIND="btbn"; REMANGA_FFMPEG_ASSET="linux64"; REMANGA_FFMPEG_ARCHIVE="tar.xz"
    REMANGA_SUMMARY="detection failed; assuming linux/x86_64 CPU"; REMANGA_NOTES=""
else
    eval "$DETECTED"
fi

say "This machine: $REMANGA_SUMMARY"
[ -n "${REMANGA_NOTES:-}" ] && warn "$REMANGA_NOTES"

# Passed to every install that pulls a torch-ecosystem package, so uv fetches
# from the wheel index that matches this machine instead of whatever plain
# PyPI happens to serve. Deliberately an explicit backend rather than uv's own
# `--torch-backend=auto`: auto maps the driver to the newest CUDA it supports,
# and the newest indexes do not all carry the torch 2.8 that IndexTTS-2.5
# pins (cu118 stops at 2.7, cu130 starts at 2.9). hardware.py only ever picks
# an index that actually has it - see its module docstring.
TORCH_ARGS=()
if [ -n "${REMANGA_TORCH_BACKEND:-}" ] && [ "$REMANGA_TORCH_BACKEND" != "default" ]; then
    TORCH_ARGS=(--torch-backend "$REMANGA_TORCH_BACKEND")
fi

# ---------------------------------------------------------------------------
# 3. FFmpeg
# ---------------------------------------------------------------------------
# The pinned BtbN build below is deliberately a specific dated snapshot, NOT
# the "latest" rolling tag. BtbN only publishes master snapshots, each built
# against whatever NVENC SDK was current that day, and NVENC's minimum
# required driver only ever goes UP. "latest" therefore silently raises the
# driver floor for GPU encoding every day it rebuilds. Pinning an older,
# known-good snapshot keeps working on newer drivers too (NVENC is backward
# compatible in that direction), so it trades changelog nobody here needs for
# GPU encoding that works across a far wider range of drivers.
#
# To bump: pick a tag from https://github.com/BtbN/FFmpeg-Builds/releases and
# find its real asset name (NOT "master-latest") via:
#   curl -s https://github.com/BtbN/FFmpeg-Builds/releases/expanded_assets/<tag> \
#     | grep -oE 'ffmpeg-[^"]*-gpl\.(tar\.xz|zip)' | grep -v shared
FFMPEG_TAG="autobuild-2026-03-31-13-11"
FFMPEG_BUILD="N-123777-g53537f6cf5"

FFMPEG_BIN="$BIN_DIR/ffmpeg"
FFPROBE_BIN="$BIN_DIR/ffprobe"
FF_EXT=""
if [ "$REMANGA_OS" = "windows" ]; then
    FF_EXT=".exe"; FFMPEG_BIN="$BIN_DIR/ffmpeg.exe"; FFPROBE_BIN="$BIN_DIR/ffprobe.exe"
fi

use_system_ffmpeg() {
    command -v ffmpeg >/dev/null 2>&1 || return 1
    cp "$(command -v ffmpeg)" "$FFMPEG_BIN" 2>/dev/null || return 1
    if command -v ffprobe >/dev/null 2>&1; then
        cp "$(command -v ffprobe)" "$FFPROBE_BIN" 2>/dev/null || return 1
    fi
    chmod +x "$FFMPEG_BIN" "$FFPROBE_BIN" 2>/dev/null
    say "Using the system ffmpeg already on PATH."
    return 0
}

download_static_ffmpeg() {
    local asset="ffmpeg-${FFMPEG_BUILD}-${REMANGA_FFMPEG_ASSET}-gpl.${REMANGA_FFMPEG_ARCHIVE}"
    local url="https://github.com/BtbN/FFmpeg-Builds/releases/download/$FFMPEG_TAG/$asset"
    local tmp="$CACHE_DIR/ffmpeg-download"

    rm -rf "$tmp" && mkdir -p "$tmp" || return 1
    say "Downloading static FFmpeg for ${REMANGA_OS}/${REMANGA_ARCH}..."
    curl -fL --retry 3 -A "Mozilla/5.0" "$url" -o "$tmp/archive" 2>/dev/null || return 1

    if [ "$REMANGA_FFMPEG_ARCHIVE" = "zip" ]; then
        command -v unzip >/dev/null 2>&1 || return 1
        unzip -q "$tmp/archive" -d "$tmp" || return 1
    else
        tar -xf "$tmp/archive" -C "$tmp" || return 1
    fi

    local src_ffmpeg src_ffprobe
    src_ffmpeg="$(find "$tmp" -type f -name "ffmpeg$FF_EXT" | head -n 1)"
    src_ffprobe="$(find "$tmp" -type f -name "ffprobe$FF_EXT" | head -n 1)"
    [ -n "$src_ffmpeg" ] && [ -n "$src_ffprobe" ] || return 1

    cp "$src_ffmpeg" "$FFMPEG_BIN" && cp "$src_ffprobe" "$FFPROBE_BIN" || return 1
    chmod +x "$FFMPEG_BIN" "$FFPROBE_BIN" 2>/dev/null
    rm -rf "$tmp"
    say "Static FFmpeg installed into $BIN_DIR"
    return 0
}

if [ ! -x "$FFMPEG_BIN" ] || [ ! -x "$FFPROBE_BIN" ]; then
    if [ "$REMANGA_FFMPEG_KIND" = "btbn" ]; then
        download_static_ffmpeg || use_system_ffmpeg || warn "could not obtain ffmpeg"
    else
        # macOS and any architecture BtbN doesn't publish: the system one is
        # the normal way to have ffmpeg there, not a fallback.
        use_system_ffmpeg || warn "no ffmpeg found - install one (macOS: 'brew install ffmpeg') and re-run"
    fi
fi
[ -x "$FFMPEG_BIN" ] || die "ffmpeg is required and could not be installed automatically"

# ---------------------------------------------------------------------------
# 4. Virtual environments
# ---------------------------------------------------------------------------
# One lightweight main env plus one per heavy ML dependency, tucked under
# .tools/. Their requirements genuinely conflict - MAGI v3 needs
# transformers<4.52, Audio8 needs >=4.57, and nothing guarantees any two of
# them would ever agree on one resolution - so five environments buys
# permanent isolation instead of a pin that has to be re-verified by hand
# every time one tool's install could clobber another's. Nothing "activates"
# them: the main env invokes `.tools/venv-<tool>/bin/python` as a subprocess
# (see remanga/paths/tools.py).
make_venv() {
    "$UV" venv "$1" --python 3.11 --allow-existing >/dev/null 2>&1 || return 1
    return 0
}

say "Creating main environment ($VENV_DIR)..."
make_venv "$VENV_DIR" || die "could not create the main virtual environment"
"$UV" pip install --python "$VENV_DIR" -e . || die "could not install remanga into the main environment"

say "Creating IndexTTS-2.5 environment [$REMANGA_TORCH_BACKEND wheels]..."
if make_venv "$INDEXTTS_VENV_DIR"; then
    # --torch-backend on BOTH installs: the second one re-resolves torch as a
    # dependency of index-tts, and without the flag it would happily pull the
    # plain-PyPI build straight over the machine-matched one just installed.
    try_step "IndexTTS torch install" \
        "$UV" pip install --python "$INDEXTTS_VENV_DIR" "${TORCH_ARGS[@]}" \
        torch torchaudio transformers accelerate huggingface-hub modelscope
    try_step "IndexTTS package install" \
        "$UV" pip install --python "$INDEXTTS_VENV_DIR" "${TORCH_ARGS[@]}" \
        "git+https://github.com/index-tts/index-tts.git"

    # index-tts's own pyproject declares a `pytorch-cuda` index pinned to
    # cu128 via [tool.uv.sources], and that pin WINS over --torch-backend:
    # installing it resolves torch to 2.8.0+cu128 even when we asked for
    # cpu or rocm. Verified by dry-run - `--torch-backend cpu` alone gives
    # 2.8.0+cpu, but the same flag alongside the git package gives
    # 2.8.0+cu128. Left alone that would put CUDA wheels on CPU-only and
    # AMD machines, which is exactly the portability bug this file exists
    # to fix, so the 2.8 line is re-pinned here from the index this machine
    # actually wants. Every supported backend carries 2.8 (see
    # hardware.py), so this resolves everywhere; it's a no-op when the
    # detected backend already is cu128.
    try_step "IndexTTS torch re-pin for this machine" \
        "$UV" pip install --python "$INDEXTTS_VENV_DIR" "${TORCH_ARGS[@]}" \
        "torch==2.8.*" "torchaudio==2.8.*"
else
    warn "could not create the IndexTTS environment"
fi

say "Creating Audio8 TTS environment [$REMANGA_TORCH_BACKEND wheels]..."
if make_venv "$AUDIO8_VENV_DIR"; then
    try_step "Audio8 install" \
        "$UV" pip install --python "$AUDIO8_VENV_DIR" "${TORCH_ARGS[@]}" \
        "torch>=2.5.0" "torchaudio>=2.5.0" "transformers>=4.57.0,<5" "soundfile>=0.12" \
        "safetensors>=0.4" accelerate huggingface-hub
else
    warn "could not create the Audio8 environment"
fi

# Audio8 is Falcon-H1-based (a Mamba/state-space hybrid), and its speed
# depends on the fused mamba-ssm/causal-conv1d CUDA kernels; without them
# transformers silently falls back to an unfused token-by-token recurrence
# that measured ~2-3x slower per panel. These are real CUDA extension builds
# (~10-20 min, need nvcc matching torch's CUDA major version), so this is
# strictly best-effort - and it is skipped entirely unless there is actually
# an NVIDIA GPU to build them for, which is the difference between a 20
# minute wasted build and none at all on a CPU or Apple machine.
if [ "$REMANGA_ACCEL" = "cuda" ] && [ -d "$AUDIO8_VENV_DIR" ]; then
    say "Building Audio8's fused Mamba CUDA kernels (~10-20 min; optional, safe to fail)..."
    (
        set -e
        # nvcc from pip rather than the system CUDA toolkit: torch's build only
        # needs nvcc's MAJOR version to match torch.version.cuda, and the
        # system toolkit is frequently a different major version.
        "$UV" pip install --python "$AUDIO8_VENV_DIR" nvidia-cuda-nvcc
        NVCC_BIN="$(find "$AUDIO8_VENV_DIR" -type f -path "*/nvidia/*/bin/nvcc" 2>/dev/null | head -n 1)"
        [ -n "$NVCC_BIN" ] || { echo "no nvcc found after install"; exit 1; }
        CUDA_HOME="$(dirname "$(dirname "$NVCC_BIN")")"
        export CUDA_HOME PATH="$CUDA_HOME/bin:$PATH" MAX_JOBS=4
        # Build only for the compute capability actually present, so nvcc
        # doesn't spend the whole 20 minutes on architectures this machine
        # will never run.
        arch_list="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -n 1 | tr -d ' ')"
        export TORCH_CUDA_ARCH_LIST="${arch_list:-7.5;8.0;8.6;8.9;9.0}"
        "$UV" pip install --python "$AUDIO8_VENV_DIR" causal-conv1d --no-build-isolation
        "$UV" pip install --python "$AUDIO8_VENV_DIR" mamba-ssm --no-build-isolation
    ) && say "Fused Mamba CUDA kernels installed - Audio8 will use the fast path." \
      || warn "fused Mamba kernels not built - Audio8 still works, just on its slower fallback path."
else
    say "Skipping Audio8's CUDA kernels (torch backend is '$REMANGA_TORCH_BACKEND', not CUDA) - Audio8 will use its portable fallback path."
fi

say "Creating MAGI v3 environment [$REMANGA_TORCH_BACKEND wheels]..."
if make_venv "$MAGI_VENV_DIR"; then
    # einops/matplotlib: undeclared imports MAGI v3's remote modeling code
    # needs beyond its own requirements. magi_assist.py auto-installs anything
    # still missing on first load; listing the known ones saves a round-trip.
    try_step "MAGI v3 install" \
        "$UV" pip install --python "$MAGI_VENV_DIR" "${TORCH_ARGS[@]}" \
        torch "transformers<4.52.0" timm shapely pytorch-metric-learning huggingface-hub \
        pillow numpy einops matplotlib
else
    warn "could not create the MAGI v3 environment"
fi

say "Creating DeepSeek-OCR-2 environment [$REMANGA_TORCH_BACKEND wheels]..."
if make_venv "$DEEPSEEK_OCR_VENV_DIR"; then
    try_step "DeepSeek-OCR-2 install" \
        "$UV" pip install --python "$DEEPSEEK_OCR_VENV_DIR" "${TORCH_ARGS[@]}" \
        torch transformers accelerate pillow huggingface-hub modelscope einops addict easydict
else
    warn "could not create the DeepSeek-OCR-2 environment"
fi

# ---------------------------------------------------------------------------
# 5. Config + weights
# ---------------------------------------------------------------------------
if [ ! -f "config.json" ]; then
    cp config.example.json config.json && say "Created config.json from config.example.json"
fi

# video.gpu_codec defaults to "auto" and is resolved per machine at render
# time (see remanga/config/system.py and video/render.py), so nothing about
# the encoder needs writing into config.json here.

say "Verifying and downloading model weights..."
try_step "model weight download" "$VENV_DIR/bin/python3" -m remanga.cli setup-models

# ---------------------------------------------------------------------------
echo
echo "=========================================================="
if [ ${#WARNINGS[@]} -eq 0 ]; then
    echo "✓ remanga environment initialized successfully."
else
    echo "✓ remanga environment initialized, with ${#WARNINGS[@]} warning(s):"
    for w in "${WARNINGS[@]}"; do echo "    - $w"; done
fi
echo
echo "  Machine:  $REMANGA_SUMMARY"
echo "  Encoder:  $REMANGA_VIDEO_ENCODER"
echo
echo "  Guided wizard : ./pipeline.sh"
echo "  Step-by-step  : ./run.sh --help"
echo "  Re-check hw   : ./run.sh hardware"
echo "=========================================================="
