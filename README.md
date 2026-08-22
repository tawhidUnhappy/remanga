# remanga

**remanga** is a 100% self-contained, modular manga recap video production engine. Powered by **IndexTTS-2.5**, it automates manga downloading, MAGI v3-assisted panel marking via a local web UI, LLM-guided narration writing, vision packaging, consistent monotone vocal synthesis, audio mastering with EBU R128 normalization, and GPU-accelerated video rendering.

Built with strict environment isolation, `remanga` provisions its own tools, manages its own runtimes, and leaves zero files or modifications outside its root workspace directory.

---

## Table of Contents
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Fresh PC Installation & Setup](#fresh-pc-installation--setup)
- [Quick Start: Master Interactive Wizard](#quick-start-master-interactive-wizard)
- [Configuration & Settings Wizard](#configuration--settings-wizard)
- [Step-by-Step CLI Production Workflow](#step-by-step-cli-production-workflow)
- [LLM Prompting & Vision Asset Guide](#llm-prompting--vision-asset-guide)
  - [Vision Upload Formats: sheets.zip vs panels.zip](#vision-upload-formats-sheetszip-vs-panelszip)
  - [Panel Marker Web UI](#panel-marker-web-ui)
  - [Temporal Horizon Prompting (Zero Spoilers)](#temporal-horizon-prompting-zero-spoilers)
- [Zero-Emotion & Consistent Audio Mastering](#zero-emotion--consistent-audio-mastering)
- [CLI Command Reference](#cli-command-reference)
- [Workspace Directory Structure](#workspace-directory-structure)
- [Troubleshooting & FAQ](#troubleshooting--faq)
- [License](#license)

---

## Key Features

- **100% Isolated & Cleanly Removable:**
  - Provisions its own standalone `uv` binary in `bin/uv`.
  - Downloads and runs isolated static `ffmpeg` and `ffprobe` binaries in `bin/`.
  - Runs inside an isolated Python 3.11 interpreter inside `.cache/`.
  - PyTorch, Hugging Face, and ModelScope caches are locked to `.cache/`.
  - **Deleting the `remanga/` folder leaves ZERO leftover files or tool modifications on your system.**
- **Dual Vision Asset Packaging (`sheets.zip` vs `panels.zip`):**
  - **Vision Contact Sheets (`sheets.zip`):** Consolidates cropped panels into 2x2 labeled grid sheets to drastically reduce LLM vision token consumption.
  - **Individual Panel Crops (`panels.zip`):** Packages individual high-resolution panel crops for maximum visual fidelity.
  - Configurable interactively and persistent in `config.json`.
- **Zero-Emotion Consistent Vocal Synthesis (IndexTTS-2.5):**
  - Autoregressive temperature (`0.2`) and nucleus sampling (`top_p: 0.7`) stabilization.
  - Locked flat 8-dimensional emotion vector (`[0.0]*8`) for uniform, objective, documentary-style narration across all panels.
  - Zero-shot speaker cloning from any clean 3–10s reference voice WAV.
- **Strict Temporal Horizon Prompting (Anti-Spoiler & Anti-Hallucination):**
  - Forbids unintroduced character names, future plot reveals, motives, or hallucinated actions.
  - Strict 0–1000 normalized integer bounding box coordinate system (`[ymin, xmin, ymax, xmax]`).
- **Broadcast Audio Mastering:**
  - Per-panel 35ms micro edge-fading to eliminate digital clicks.
  - Optional background music (BGM) looping with gain ducking.
  - Broadcast EBU R128 loudness normalization (`-16 LUFS`).
- **Multi-Resolution Video Compositor & GPU Renderer:**
  - Presets for **1080p Full HD**, **1440p 2K QHD**, **2160p 4K UHD**, and **720p HD**.
  - Fast Bokeh Canvas Blur (<1.5ms per frame) or Solid Black canvas.
  - Automatic NVIDIA NVENC GPU hardware encoding (`h264_nvenc`) with automatic CPU fallback (`libx264`).

---

## System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| **Operating System** | Linux (Ubuntu 20.04+, Debian 11+, Arch, WSL2 on Windows) | Ubuntu 22.04 LTS or WSL2 |
| **GPU** | 6 GB VRAM (NVIDIA Pascal or newer) | 8 GB+ VRAM (RTX 3060/4060 or better) |
| **CUDA Driver** | NVIDIA Driver >= 525.60.13 | NVIDIA Driver >= 535+ (CUDA 12.x) |
| **CPU** | 4 Cores x86_64 | 8+ Cores x86_64 |
| **RAM** | 8 GB RAM | 16 GB+ RAM |
| **Disk Space** | 20 GB free disk space (three isolated venvs + models + workspace) | 35 GB+ SSD |

---

## Fresh PC Installation & Setup

Follow these steps to set up `remanga` from scratch on a new machine.

### Step 1: Install System Prerequisites
On Ubuntu / Debian / WSL2:
```bash
sudo apt update && sudo apt install -y git curl wget tar bzip2 libgl1 libglib2.0-0
```

*Note on Windows:* Run inside **WSL2 (Windows Subsystem for Linux)** with NVIDIA CUDA drivers installed on the Windows host.

### Step 2: Clone the Repository
```bash
git clone https://github.com/your-username/remanga.git
cd remanga
```

### Step 3: Run the Bootstrap Script
Run the automated sandbox bootstrapper:
```bash
bash bootstrap.sh
```

**What `bootstrap.sh` does automatically:**
1. Downloads and provisions static `bin/uv`, `bin/ffmpeg`, and `bin/ffprobe`.
2. Provisions **three** isolated Python 3.11 virtual environments instead of one:
   - `.venv/` — remanga's own lightweight core (Pillow, Pydantic, requests, rich, pydub, Flask). No ML libraries at all.
   - `.venv-indextts/` — PyTorch + IndexTTS-2.5's own pinned dependencies.
   - `.venv-magi/` — PyTorch + MAGI v3's own pinned dependencies (including a `transformers` capped below its DaViT-breaking `4.52`).

   IndexTTS and MAGI each pin their own, sometimes mutually incompatible, versions of shared libraries like `transformers` — separate environments mean neither can ever silently break the other. The main env only ever talks to them as subprocesses (see `remanga/venvs.py`); the storage trade-off buys permanent isolation instead of a pin that has to be babysat.
3. Turbo-downloads official `IndexTeam/IndexTTS-2.5` weights into `checkpoints/indextts_2.5` and `ragavsachdeva/magiv3` weights into `checkpoints/magiv3` (skipped automatically if no GPU is present).
4. Initializes default `config.json`.

---

## Quick Start: Master Interactive Wizard

The easiest way to produce a recap video is through the interactive terminal wizard:

```bash
./pipeline.sh
```
*(or run `./run.sh interactive`)*

### Wizard Step-by-Step Flow:
```
┌─────────────────────────────────────────────────────────────┐
│ 1. Select or Create Project & Chapter                       │
│ 2. Verify Reference Voice WAV & BGM                         │
│ 3. Choose Vision Upload Format (sheets.zip vs panels.zip)   │
│ 4. Download Chapter Pages from MangaDex                     │
│ 5. Mark Panels (Panel Marker web UI, MAGI v3-assisted)      │
│ 6. Crop panels & compile ZIP                                │
│ 7. Prompt for narration.json -> Synthesize Voice            │
│ 8. Mix Master Audio with EBU R128 Normalization             │
│ 9. Render Final 1080p / 2K / 4K MP4 Video                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration & Settings Wizard

Run the interactive settings wizard anytime to configure vocal reference files, background music, video resolution, canvas blur, and vision packaging:

```bash
./run.sh setup-config
```

### Key Configurable Parameters (`config.json`):

```json
{
  "system": {
    "prefer_gpu": true,
    "gpu_codec": "h264_nvenc",
    "fallback_codec": "libx264",
    "threads": 4
  },
  "cropper": {
    "margin_padding_pixels": 8,
    "auto_contrast_clean": false,
    "save_format": "PNG",
    "vision_asset_type": "sheets",
    "create_sheets": true,
    "panels_per_sheet": 4,
    "create_zip": true
  },
  "tts": {
    "engine": "indextts-2.5",
    "spk_audio_prompt": "path/to/reference_voice.wav",
    "lang": "EN",
    "use_bf16": true,
    "speed": 1.0,
    "temperature": 0.2,
    "top_p": 0.7,
    "sample_rate": 22050
  },
  "audio": {
    "sample_rate": 44100,
    "edge_fade_ms": 35,
    "pause_between_panels_ms": 300,
    "bgm_enabled": false,
    "bgm_path": "",
    "bgm_volume_db": -22.0,
    "enable_loudnorm": true
  },
  "video": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "background_style": "blur",
    "blur_brightness": 0.42,
    "panel_border_width": 2,
    "panel_border_color": "#222222"
  }
}
```

---

## Step-by-Step CLI Production Workflow

If you prefer scripting individual pipeline stages without the interactive wizard, use the CLI commands below:

### 1. Download Chapter Pages from MangaDex
Pass a title query, title URL, chapter URL, or UUID:
```bash
./run.sh download --project "yandere_sister" --chapter "1" --url "https://mangadex.org/title/..."
```
*Creates:* `projects/yandere_sister/chapters/chapter_1/pages.zip`

### 2. Mark Panels
Launches the **Panel Marker** web UI: MAGI v3 pre-fills every page's panel boxes on a GPU, you drag/adjust/delete to correct them, then Save & Continue writes `crops.json`.
```bash
./run.sh mark --project "yandere_sister" --chapter "1"
```
*Creates:* `projects/yandere_sister/chapters/chapter_1/crops.json` — see [Panel Marker Web UI](#panel-marker-web-ui) below.

### 3. Crop Panels & Build Vision Archive
```bash
./run.sh crop --project "yandere_sister" --chapter "1"
```
*Creates:* `panels/`, `sheets/`, `panels_manifest.json`, and either `sheets.zip` or `panels.zip` (depending on `config.json`).

### 4. Generate and Place `narration.json`
Upload your generated vision archive (`sheets.zip` or `panels.zip`) and `prompts/narration.md` to your LLM. Save the resulting script to:
```text
projects/yandere_sister/chapters/chapter_1/narration.json
```
*(`memory.json` is auto-created as an empty placeholder at `projects/yandere_sister/memory.json` the first time the project is touched — feed its current contents to the LLM alongside the panels so it can update it in place to maintain continuity across chapters).*

### 5. Synthesize Vocal Audio (IndexTTS-2.5)
```bash
./run.sh tts --project "yandere_sister" --chapter "1"
```
*(Optional: override reference speaker voice with `--voice path/to/voice.wav` or force re-synthesis with `--force`)*

### 6. Mix Master Audio Track
Applies micro edge-fading, mixes optional background music (BGM), and normalizes via EBU R128:
```bash
./run.sh mix --project "yandere_sister" --chapter "1"
```
*(Optional: override BGM path with `--bgm path/to/music.mp3`)*

### 7. Render Final Recap Video
Composites frames onto the chosen background canvas and renders hardware-accelerated MP4:
```bash
./run.sh render --project "yandere_sister" --chapter "1"
```
*Output File:* `projects/yandere_sister/chapters/chapter_1/yandere_sister_ch1_recap.mp4`

### Check Workspace Status Anytime
```bash
./run.sh status --project "yandere_sister" --chapter "1"
```

---

## LLM Prompting & Vision Asset Guide

### Vision Upload Formats: `sheets.zip` vs `panels.zip`

| Asset Type | Archive File | Structure | Best For |
|---|---|---|---|
| **Contact Sheets** | `sheets.zip` | 2x2 labeled grid images (`sheet_001.png`, etc.) | **Low vision token cost & fast LLM inference** (75% fewer images uploaded) |
| **Individual Panels** | `panels.zip` | Standalone cropped images (`panel_001.png`, etc.) | **Maximum resolution & fine detail examination** |

To switch formats:
1. Run `./run.sh setup-config` and choose option 2, **OR**
2. Set `"vision_asset_type": "sheets"` (or `"panels"`) in `config.json`.

---

## Panel Marker Web UI

Panel cropping is done by hand in a local browser tool instead of an LLM round-trip — `./run.sh mark -p <PROJECT> -c <CHAPTER>` (or step 5 of the interactive wizard) opens it automatically:

- **[MAGI v3](https://github.com/ragavsachdeva/magi)** (a manga-understanding vision model, GPU required) pre-fills every page's panel boxes the moment the tool launches, running in the background while you start adjusting already-detected pages.
- **Draw:** left-click and drag on a page to mark a panel (drag can start outside the page edge, Canva-style).
- **Adjust:** click a mark to select it, drag its body to move it or a corner/edge handle to resize it. Dashed guide lines appear when an edge lines up with another panel's — a visual aid, not a hard snap.
- **Delete:** right-click a mark.
- **Reorder:** drag a panel's `⠿` grip in the right-hand panel list — that order becomes narration order.
- **Finish:** `Ctrl+S` (`⌘S` on macOS) or the **Save & Continue** button writes `crops.json` and signals the CLI/wizard to move on to cropping.

Every mark — MAGI's or your own — still goes through the same gutter-snap, seam-reconciliation, duplicate-detection, and whitespace-trim passes described below, so pixel-perfect precision was never the point of drawing carefully by hand.

MAGI v3's weights download automatically the first time you run `bootstrap.sh` / `remanga setup-models` (skipped automatically if no GPU is present). Its model license permits personal, research, and non-commercial use only. To mark every panel manually without it, set `"magi_enabled": false` under `"marker"` in `config.json`.

---

### Temporal Horizon Prompting (Zero Spoilers)

The included prompt system in `prompts/` enforces strict narrative rules:
1. **Zero Future Spoilers:** The LLM is forbidden from revealing plot twists, motives, or unrevealed identities.
2. **Name Introduction Protocol:** Characters are referred to strictly by visible physical traits (*"a dark-haired student"*) until formally introduced by name in dialogue or captions.
3. **Show-and-Synthesize:** Narrative commentary blends speech bubbles and actions into active present-tense storytelling.
4. **Pacing Ceiling:** 10 to 20 words per panel (hard ceiling: 26 words) to ensure optimal retention and natural IndexTTS-2.5 speech pacing.

---

## Zero-Emotion & Consistent Audio Mastering

To maintain a consistent, flat, documentary-style recap narration without screaming, emotional pitch breaks, or cadence shifts:

1. **Flat 8-D Emotion Conditioning:** All 8 emotion vectors in `config.json` are mapped to `[0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]`.
2. **Autoregressive Sampling Stabilization:**
   - `"temperature": 0.2` (eliminates random pitch excursions).
   - `"top_p": 0.7` (constrains token sampling to uniform cadence).
3. **Punctuation Cleanliness:** The prompt forbids exclamation marks (`!`), question marks (`?`), ellipses (`...`), and ALL CAPS, preventing neural prosody spikes.
4. **Reference Voice Sample Criteria:**
   - **Length:** 4–7 seconds.
   - **Quality:** Studio clean (zero background noise, room reverb, or vocal fry).
   - **Delivery:** Calm, steady, monotone reading.

---

## CLI Command Reference

```bash
# Interactive Production Wizard
./pipeline.sh
./run.sh interactive

# Configuration & Hardware Setup
./run.sh setup-config
./run.sh setup-models

# Step-by-Step Production Commands
./run.sh download -p <PROJECT> -c <CHAPTER> [-u <URL_OR_ID>]
./run.sh mark      -p <PROJECT> -c <CHAPTER>
./run.sh crop     -p <PROJECT> -c <CHAPTER> [-f]
./run.sh tts      -p <PROJECT> -c <CHAPTER> [-v <VOICE_WAV>] [-f]
./run.sh mix      -p <PROJECT> -c <CHAPTER> [-b <BGM_FILE>]
./run.sh render   -p <PROJECT> -c <CHAPTER> [-f]
./run.sh status   -p <PROJECT> -c <CHAPTER>
```

---

## Workspace Directory Structure

```text
remanga/
├── bin/                        # Isolated standalone binaries (uv, ffmpeg, ffprobe)
├── .venv/                      # Main env - remanga's own lightweight core, no ML libs
├── .venv-indextts/             # Isolated env - PyTorch + IndexTTS-2.5's own pins
├── .venv-magi/                 # Isolated env - PyTorch + MAGI v3's own pins
├── checkpoints/
│   ├── indextts_2.5/           # IndexTTS-2.5 neural model weights
│   └── magiv3/                 # MAGI v3 panel-detection weights (Panel Marker assist)
├── prompts/
│   └── narration.md  # Master objective scriptwriter prompt
├── projects/
│   └── <project_name>/
│       ├── project.json        # Saved MangaDex URL and chapter index
│       ├── memory.json         # Story continuity state across chapters
│       └── chapters/
│           └── chapter_<num>/
│               ├── pages/              # Raw downloaded chapter pages
│               ├── pages.zip           # Upload archive for narration generation
│               ├── crops.json          # Panel crop coordinates from the Panel Marker web UI
│               ├── panels/             # Cropped individual panel images
│               ├── sheets/             # 2x2 vision contact sheets
│               ├── sheets.zip          # Contact sheets upload archive
│               ├── panels.zip          # (Alternative) individual panels archive
│               ├── narration.json      # Synchronized narration script
│               ├── audio/              # Synthesized vocal WAV files per panel
│               ├── audio_timing.json   # Panel timeline synchronization map
│               ├── master_audio.wav    # Master audio track (Loudnorm + BGM)
│               ├── video/frames/       # Composited 1080p/2K/4K canvas frames
│               └── <project>_ch<num>_recap.mp4  # FINAL RECAP VIDEO
├── remanga/                    # Python core pipeline package
│   ├── audio/                  # synth.py (talks to the .venv-indextts worker) & mix.py (master audio mixer)
│   │   └── scripts/             # indextts_worker.py - runs inside .venv-indextts, not the main env
│   ├── cropper/                # crop.py (coordinate cropper) & sheets.py (contact sheet generator)
│   ├── downloader/             # mangadex.py (MangaDex client)
│   ├── models/                 # weights.py (talks to .venv-indextts to fetch/verify weights)
│   │   └── scripts/             # download_indextts.py - runs inside .venv-indextts
│   ├── webui/                  # Panel Marker: server.py (Flask backend) & magi_assist.py (talks to .venv-magi)
│   │   └── scripts/             # magi_worker.py, download_magi.py - run inside .venv-magi
│   ├── video/                  # compose.py (frame compositor) & render.py (GPU/CPU renderer)
│   ├── venvs.py                 # Locates the .venv-indextts / .venv-magi isolated environments
│   ├── config.py                # Pydantic configuration schemas (load/save only)
│   ├── paths.py                 # Project/chapter directory layout & metadata persistence
│   ├── status.py                # Chapter production-status computation & display
│   ├── setup.py                 # Interactive Rich setup-wizard prompts
│   ├── json_io.py               # Shared JSON read/write helpers
│   ├── ffmpeg_io.py             # Shared ffmpeg subprocess helper
│   ├── wizard.py                # Interactive step-by-step production wizard
│   └── cli.py                   # CLI command dispatcher
├── config.json                 # Active user production settings
├── bootstrap.sh                # Zero-dependency sandbox environment installer
├── pipeline.sh                 # Master interactive pipeline launcher
└── run.sh                      # Isolated CLI wrapper
```

---

## Troubleshooting & FAQ

### 1. `CUDA out of memory` during TTS synthesis
- In `config.json`, verify `"use_bf16": true`.
- IndexTTS-2.5 runs comfortably on GPUs with 6GB+ VRAM in BF16 mode.

### 2. Narration tone has emotional spikes or voice breaks
- Verify that `config.json` has `"temperature": 0.2` and `"top_p": 0.7`.
- Ensure your `narration.json` does not contain exclamation marks (`!`), question marks (`?`), or dramatic punctuation.
- Inspect your reference speaker WAV (`spk_audio_prompt`). Ensure the speaker speaks in a calm, flat tone without laughter or excitement.

### 3. NVENC GPU encoder error during video rendering
- If your GPU does not support NVENC or if drivers are missing, `remanga` automatically falls back to CPU encoding (`libx264`).
- You can manually force CPU encoding by setting `"prefer_gpu": false` in `config.json`.

### 4. How do I switch between `sheets.zip` and `panels.zip`?
- Run `./run.sh setup-config` and select your preference in **Option 2 (Vision Asset Upload Format)**.
- Or change `"vision_asset_type": "sheets"` to `"panels"` directly in `config.json`.

### 5. Do I need a GPU to mark panels?
Only for the MAGI v3 auto-detect assist. Marking itself is manual clicking/dragging in the browser and needs no GPU at all — set `"magi_enabled": false` under `"marker"` in `config.json` to skip it and mark every panel by hand.

---

## License

Distributed under the **MIT License**. See `LICENSE` for details.