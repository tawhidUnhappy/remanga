# remanga

**remanga** is a 100% self-contained, modular manga recap video production engine. Powered by **IndexTTS-2.5**, it automates manga downloading, MAGI v3-assisted panel marking via a local web UI, LLM-guided narration writing, vision packaging, naturally expressive vocal synthesis, audio mastering with EBU R128 normalization, and GPU-accelerated video rendering.

Built with strict environment isolation, `remanga` provisions its own tools, manages its own runtimes, and leaves zero files or modifications outside its root workspace directory.

---

## Table of Contents
- [Key Features](#key-features)
- [System Requirements](#system-requirements)
- [Fresh PC Installation & Setup](#fresh-pc-installation--setup)
- [Quick Start: Master Interactive Wizard](#quick-start-master-interactive-wizard)
- [Configuration & Settings Wizard](#configuration--settings-wizard)
- [Step-by-Step CLI Production Workflow](#step-by-step-cli-production-workflow)
- [Resetting/Restarting a Chapter](#resettingrestarting-a-chapter)
- [LLM Prompting & Vision Asset Guide](#llm-prompting--vision-asset-guide)
  - [Vision Outputs: What to Generate, What to Zip](#vision-outputs-what-to-generate-what-to-zip)
  - [Panel Marker Web UI](#panel-marker-web-ui)
  - [Temporal Horizon Prompting (Zero Spoilers)](#temporal-horizon-prompting-zero-spoilers)
- [Natural, Expressive Narration](#natural-expressive-narration)
- [Reliability: Crashes, Interrupts & Resuming](#reliability-crashes-interrupts--resuming)
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
- **Two-Section Vision Output Control - What to Generate, What to Zip:**
  - **Generate:** individual panel crops (`panels/`, always produced) and, optionally, 2x2 labeled contact sheet composites (`sheets/`) merged at **full original resolution** - never downscaled - to drastically reduce LLM vision token consumption without losing detail.
  - **Package:** zip/PDF any of it for upload - `panels_zip` (on by default), `panels_pdf`, `sheets_zip` (both off by default) - each independently a single file or split into size-capped parts, losslessly re-encoded smaller than the raw files either way.
  - Configurable as a plain two-section checklist, interactively (`./run.sh setup-config`, or a prompt in the main wizard each run) and persistent in `config.json` - see [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip).
- **Natural, Expressive Vocal Synthesis (IndexTTS-2.5):**
  - No forced emotion vector — IndexTTS-2.5 infers its own emotion/prosody straight from each panel's narration text and punctuation, so delivery matches what the panel actually calls for instead of one flat register for every panel.
  - Temperature/top-p left at IndexTTS-2.5's own recommended defaults (`0.8`/`0.8`) for natural-sounding prosody — see [Natural, Expressive Narration](#natural-expressive-narration).
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
- **Safe to Interrupt, Safe to Resume:** Ctrl+C (or a crash) mid-synthesis never leaves a corrupt clip behind — panel exports are atomic, and resuming automatically re-synthesizes the panel that was interrupted plus the two just before it, rather than trusting whatever's on disk. A worker that stops responding gets killed and replaced automatically instead of hanging forever. See [Reliability](#reliability-crashes-interrupts--resuming).
- **Three-Tier Chapter Reset:** hard (keep only downloads), marks-only (also keep your panel marks), or soft (also keep the cropped panels and narration script) — pick how much work to throw away. See [Resetting/Restarting a Chapter](#resettingrestarting-a-chapter).

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
1. Downloads and provisions static `bin/uv`, `bin/ffmpeg`, and `bin/ffprobe` — `ffmpeg` is pinned to a specific tested build rather than always the newest one, so its NVENC GPU encoder keeps working across a wide range of NVIDIA driver versions instead of silently requiring whatever driver was newest the day it was compiled (see [Troubleshooting #3](#troubleshooting--faq)).
2. Provisions **three** isolated Python 3.11 virtual environments instead of one:
   - `.venv/` — remanga's own lightweight core (Pillow, Pydantic, requests, rich, pydub, Flask). No ML libraries at all.
   - `.tools/venv-indextts/` — PyTorch + IndexTTS-2.5's own pinned dependencies.
   - `.tools/venv-magi/` — PyTorch + MAGI v3's own pinned dependencies (including a `transformers` capped below its DaViT-breaking `4.52`).

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
│ 3. Review/Adjust Vision Outputs (generate + zip checklist)  │
│ 4. Download Chapter Pages from MangaDex                     │
│ 5. Mark Panels (Panel Marker web UI, MAGI v3-assisted)      │
│ 6. Crop panels & package vision uploads                     │
│ 7. Prompt for narration.json -> Synthesize Voice            │
│ 8. Mix Master Audio with EBU R128 Normalization             │
│ 9. Render Final 1080p / 2K / 4K MP4 Video                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Configuration & Settings Wizard

Run the interactive settings wizard anytime to configure vocal reference files, background music, video resolution, canvas blur, and vision outputs (what to generate, what to zip/PDF for upload):

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
  "downloader": {
    "zip_pages_enabled": false
  },
  "cropper": {
    "margin_padding_pixels": 8,
    "auto_contrast_clean": false,
    "save_format": "PNG",
    "panels_per_sheet": 4,
    "generate": {
      "sheets": false
    },
    "package": {
      "panels_zip": true,
      "panels_zip_split": false,
      "panels_pdf": false,
      "panels_pdf_split": false,
      "sheets_zip": false,
      "sheets_zip_split": false,
      "max_mb": 50.0
    }
  },
  "marker": {
    "auto_open_browser": true,
    "magi_enabled": true,
    "click_to_select": true
  },
  "tts": {
    "engine": "indextts-2.5",
    "spk_audio_prompt": "path/to/reference_voice.wav",
    "lang": "EN",
    "use_bf16": true,
    "speed": 1.0,
    "temperature": 0.8,
    "top_p": 0.8,
    "sample_rate": 22050,
    "synth_timeout_seconds": 180
  },
  "audio": {
    "sample_rate": 44100,
    "edge_fade_ms": 35,
    "pause_between_panels_ms": 0,
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

A few worth calling out specifically - `cropper.generate`/`cropper.package` are the two-section vision-output checklist, covered in full under [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) below:
- **`downloader.zip_pages_enabled`** (default `false`) — bundles the raw downloaded pages into `pages.zip`. Off by default because nothing downstream reads it; it's only useful if you want to hand a chapter's pages to an LLM by hand. Named for exactly what it zips (the downloaded *pages*) so it's never confused with `cropper.package` below, which zips something completely different.
- **`cropper.generate.sheets`** (default `false`) — generates `sheets/` contact sheet composites. Off by default to skip work nothing needs; `cropper.package.sheets_zip` (below) builds them automatically the moment it's checked, whether or not this is also on. Every sheet is merged from its panels' **full original resolution** — never downscaled — with only lossless re-encoding used to keep the file size down.
- **`marker.click_to_select`** (default `true`) — see [Panel Marker Web UI](#panel-marker-web-ui) for what this protects against.
- **`tts.synth_timeout_seconds`** (default `180`) — see [Reliability](#reliability-crashes-interrupts--resuming).

---

## Step-by-Step CLI Production Workflow

If you prefer scripting individual pipeline stages without the interactive wizard, use the CLI commands below:

### 1. Download Chapter Pages from MangaDex
Pass a title query, title URL, chapter URL, or UUID:
```bash
./run.sh download --project "my_manga" --chapter "1" --url "https://mangadex.org/title/..."
```
*Creates:* `projects/my_manga/chapters/chapter_1/pages/` (plus `pages.zip` if `downloader.zip_pages_enabled` is enabled — off by default)

### 2. Mark Panels
Launches the **Panel Marker** web UI: MAGI v3 pre-fills every page's panel boxes on a GPU, you drag/adjust/delete to correct them, then Save & Continue writes `crops.json`.
```bash
./run.sh mark --project "my_manga" --chapter "1"
```
*Creates:* `projects/my_manga/chapters/chapter_1/crops.json` — see [Panel Marker Web UI](#panel-marker-web-ui) below.

### 3. Crop Panels & Package Vision Uploads
```bash
./run.sh crop --project "my_manga" --chapter "1"
```
*Creates:* `panels/`, `panels_manifest.json`, `sheets/` (whenever it's actually needed - `generate.sheets` on, or `package.sheets_zip` active), and whichever of `panels_zip/panels_1.zip` (on by default), `panels_pdf/panels_1.pdf`, and `sheets_zip/sheets_1.zip` (both off by default) are active per `cropper.package` (see [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) below).

### 4. Generate and Place `narration.json` + `memory.json`
Upload **any one** of your generated vision archives — whichever package formats are active (`panels_zip`, `panels_pdf`, `sheets_zip`) — and `prompts/narration.md` to your LLM, attaching the project's current `memory.json` too, once it has real content, so continuity carries across chapters. The prompt asks for **exactly two fenced JSON code blocks and nothing else** (no commentary before/after), so the LLM's reply can be copy-pasted straight into each file. The interactive wizard prints every archive actually available to upload this run as a ctrl+click-openable path (VS Code and similar editors), and both destination paths, when it gets to this step:
```text
projects/my_manga/chapters/chapter_1/narration.json   (Block 1)
projects/my_manga/memory.json                         (Block 2)
```
`memory.json` is auto-created as an empty placeholder the first time a project is touched, and updated in place chapter over chapter (carried-forward characters/factions, appended plot points, resolved/opened cliffhangers) — it's how the LLM keeps track of the story without re-reading every prior chapter.

### 5. Synthesize Vocal Audio (IndexTTS-2.5)
```bash
./run.sh tts --project "my_manga" --chapter "1"
```
*(Optional: override reference speaker voice with `--voice path/to/voice.wav` or force re-synthesis with `--force`)*

### 6. Mix Master Audio Track
Applies micro edge-fading, mixes optional background music (BGM), and normalizes via EBU R128:
```bash
./run.sh mix --project "my_manga" --chapter "1"
```
*(Optional: override BGM path with `--bgm path/to/music.mp3`)*

### 7. Render Final Recap Video
Composites frames onto the chosen background canvas and renders hardware-accelerated MP4:
```bash
./run.sh render --project "my_manga" --chapter "1"
```
*Output File:* `projects/my_manga/chapters/chapter_1/my_manga_ch1_recap.mp4`

### Check Workspace Status Anytime
```bash
./run.sh status --project "my_manga" --chapter "1"
```

---

## Resetting/Restarting a Chapter

`remanga restart` wipes a chapter's generated artifacts back to one of four levels, always keeping the downloaded pages (and re-verifying/re-fetching them afterward, so a partially-corrupt download never lingers):

| Mode | Flag | Keeps | Use it when... |
|---|---|---|---|
| **Hard** (default) | `--mode hard` | downloaded pages only | starting the chapter completely over |
| **Marks-only** | `--mode marks_only` | + `crops.json` | your panel marks are good, but you changed a cropper setting (margin, gutter-snap, vision format) or just want a fresh narration script — `narration.json` is emptied, not kept |
| **Re-mark** | `--mode remark` | + `crops.json` | same deletion as marks-only, but also reopens the Panel Marker web UI afterward with the kept marks pre-loaded, so you can review/adjust them before continuing instead of trusting them blindly |
| **Soft** | `--mode soft` | + `crops.json`, `panels/`, `narration.json` | you changed voice/BGM/resolution and only need TTS/mix/render redone |

```bash
./run.sh restart --project "my_manga" --chapter "1" --mode marks_only
```
Add `-f`/`--force` to skip the confirmation prompt, or `--no-reverify` to skip re-checking the downloaded pages afterward. `remark` still opens the Panel Marker and waits for you to save even with `--force` — that flag only skips the deletion confirmation, not the marking step itself. The interactive wizard offers the same four levels (plus "Resume") whenever you pick a chapter that already has progress.

Reopening the Panel Marker on a chapter that already has marks — via `remark`, or by just running `remanga mark` again — always pre-loads the existing `crops.json` instead of starting blank, and flags every page it loaded marks for as already-reviewed so MAGI's background assist won't overwrite them.

---

## LLM Prompting & Vision Asset Guide

### Vision Outputs: What to Generate, What to Zip

Two independent sections under `cropper` in `config.json` - `generate` decides what visual content exists at all, `package` decides what gets zipped/PDF'd from it for LLM upload. There's no separate "primary archive" concept to also keep track of - every zip a chapter gets goes through `package` alone.

**Section 1 - `generate`: what content to produce.** Individual panel crops (`panels/panel_001.png`, ...) are always produced - that's what cropping a chapter means - so the only thing to choose here is:

| Key (under `cropper.generate`) | Default | Meaning |
|---|---|---|
| `sheets` | `false` | Build `sheets/` - 2x2 labeled contact sheet composites, merged at each panel's **full original resolution** (the composite canvas is sized *from* the panels, not the other way around - a sheet never loses detail a plain panel crop wouldn't also have). The only thing keeping file size down is picking whichever lossless container (PNG or lossless WEBP) comes out smaller, same as every format below. |

**Section 2 - `package`: what to zip/PDF for upload**, from whatever Section 1 produced - never touching `panels/` itself (still full quality, still what video rendering reads):

| Format | Packages | Container | Default |
|---|---|---|---|
| `panels_zip` | Individual panel crops, one file per panel | zip | **On** |
| `panels_pdf` | The same individual panels, one per PDF page | PDF | Off |
| `sheets_zip` | Contact sheet composites instead - fewer, denser images, lower LLM vision-token cost, still full original resolution (builds `sheets/` automatically the moment this is checked, whether or not `generate.sheets` above is also on) | zip | Off |

**Controlling what actually gets built** is a checklist, not a mode to pick — check either, both, or neither format, and within a format check either or both of:
- `<format>`: generate it as **one single file** holding every image, regardless of size.
- `<format>_split`: generate it **split into multiple size-capped parts** instead - `..._1.zip`/`.pdf`, `..._2.___`, ... packed in reading order, each staying at or under `max_mb`, so a part is never larger than the cap unless a single image alone already exceeds it.

So "only the PDF, nothing else" is exactly `panels_pdf: true` with every other flag `false` — nothing else gets built, full stop. Checking `<format>_split` builds the split version regardless of `<format>` (either one is enough to generate something for that format); checking both together still only produces the split version, not two separate outputs. Reach this checklist two ways:
- `./run.sh setup-config` (step 2), the full settings walkthrough, **or**
- the main interactive wizard's own **"Adjust what gets generated/zipped for this chapter?"** prompt each run (defaults to No, so it never interrupts a normal run uninvited) — the same two-section checklist, without needing to know `setup-config` exists separately.

How each package format stays lossless:
- **panels_zip / sheets_zip:** every image re-encoded as an optimized PNG and as a lossless WEBP, keeping whichever comes out smaller. Manga line art/halftones typically shrink 30-50% this way.
- **panels_pdf:** every image is embedded as a `FlateDecode`-compressed raw bitmap (PDF's own native lossless image representation — the same class of compression a PNG uses internally, just packaged the way PDF expects), optionally TIFF-Predictor-2-filtered first for a better ratio. Pillow's own PDF writer re-encodes RGB images as lossy JPEG with no way to turn that off short of quantizing colors, which is why this is built directly rather than through Pillow's `Image.save(..., "PDF")`.
- Either way, a candidate re-encoding only ever gets used after decoding it back and verifying it's pixel-for-pixel identical to the original — anything that doesn't round-trip exactly is discarded in favor of a safer encoding (or the original file, for the zip formats).

Each part carries the same project/manga/chapter identity, plus which part it is, how many parts total, and that part's image range — as a `chapter_info.json` file for a panels_zip/sheets_zip part, or as page 1 of a PDF part (rendered as plain, readable text, since a PDF can't hold a separate loose file the way a zip can) - true even with splitting off and a single part, so an LLM given only one part never has to guess whether more exist. See the "Chapter Identity" section of [`prompts/narration.md`](prompts/narration.md) for how the LLM is expected to read it.

Every package setting lives together under one `cropper.package` object, so there's exactly one place to look — set it interactively via `./run.sh setup-config` (step 2) or the wizard's own prompt above, or by hand in `config.json`:

| Key (under `cropper.package`) | Default | Meaning |
|---|---|---|
| `panels_zip` | `true` | Build the panels_zip format (individual panels) every crop run. |
| `panels_zip_split` | `false` | Allow the panels_zip format to split into multiple size-capped parts. |
| `panels_pdf` | `false` | Build the panels_pdf format (individual panels) every crop run. |
| `panels_pdf_split` | `false` | Allow the panels_pdf format to split into multiple size-capped parts. |
| `sheets_zip` | `false` | Build the sheets_zip format (contact sheet composites) every crop run. |
| `sheets_zip_split` | `false` | Allow the sheets_zip format to split into multiple size-capped parts. |
| `max_mb` | `50.0` | Size cap per part, in MB — shared by all three formats, only used when their `<format>_split` is on. |

---

## Panel Marker Web UI

Panel cropping is done by hand in a local browser tool instead of an LLM round-trip — `./run.sh mark -p <PROJECT> -c <CHAPTER>` (or step 5 of the interactive wizard) opens it automatically:

- **[MAGI v3](https://github.com/ragavsachdeva/magi)** (a manga-understanding vision model, GPU required) pre-fills every page's panel boxes the moment the tool launches, running in the background while you start adjusting already-detected pages.
- **Draw tool (`D`):** left-click and drag on a page to mark a panel (drag can start outside the page edge, Canva-style, and can start on top of an existing mark to draw an overlapping one without disturbing it — see click-to-select below).
- **Select tool (`V`):** click a mark to select it, then drag its body to move it or a corner/edge handle to resize it. Dashed guide lines appear when an edge lines up with another panel's — a visual aid, not a hard snap.
- **Delete:** right-click a mark.
- **Reorder:** drag a panel's `⠿` grip in the right-hand panel list — that order becomes narration order.
- **Zoom & pan:** Ctrl/Cmd+scroll to zoom (anchored under the cursor), plain scroll or Alt+scroll to pan, spacebar+drag or middle-mouse-drag for the hand tool, `0` to reset the view.
- **Finish:** `Ctrl+S` (`⌘S` on macOS) or the **Save & Continue** button writes `crops.json` and signals the CLI/wizard to move on to cropping.

**Click-to-select (`marker.click_to_select`, default on):** a mark only becomes draggable once it's already selected — a first click just selects it, a second, deliberate drag actually moves/resizes it. This means one accidental click-drag can never nudge the wrong mark on a page with tightly packed panels. It also means the Draw tool never moves an existing mark: starting a new box on top of one (even one you'd already selected) just draws, full stop. Set `"click_to_select": false` in `config.json`'s `"marker"` section to go back to the old any-drag-moves-it behavior.

**Keyboard shortcuts** are fully customizable from the gear icon in the topbar (saved straight into `config.json`'s `marker.shortcuts`, so they persist across runs). Defaults:

| Action | Default key |
|---|---|
| Save & continue | `Ctrl`/`Cmd` + `S` |
| Mark whole page as one panel | `Ctrl`/`Cmd` + `F` |
| Draw tool | `D` |
| Select tool | `V` |
| Previous / next page | `←` / `→` |
| Delete selected mark | `Delete` or `Backspace` |
| Reset zoom & position | `0` |

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

## Natural, Expressive Narration

The narration audio is meant to sound like an actual person reading the script, not a flat robotic monotone — so the pipeline lets IndexTTS-2.5 infer its own emotion and prosody directly from each panel's text, instead of forcing every panel into the same fixed emotional register:

1. **No Forced Emotion Vector:** `audio/synth.py` sends no `emo_vector` to IndexTTS-2.5 at all. With none supplied, the model reads the pacing, emphasis, and rising/falling tone straight out of `narration.json`'s `text` and its own punctuation — an exclamation mark lands as a shout or outburst, a question mark as an actual question, an ellipsis as hesitation — so the delivery matches what the panel actually calls for instead of one flat register for every panel.
2. **Punctuate For It:** `prompts/narration.md` (Rule 3) has the LLM write real punctuation — `!`, `?`, `...` — wherever the panel genuinely is exclamatory, interrogative, or hesitant, and plain measured prose everywhere else. That punctuation *is* the emotion cue now; there's no separate emotion field in `narration.json` — each entry is just `panel_id` + `text`.
3. **Natural Autoregressive Sampling:** `temperature`/`top_p` are left at IndexTTS-2.5's own recommended defaults (`0.8`/`0.8`, not artificially lowered) — this governs how natural a single reading *sounds* (pitch/pacing variation), on top of whatever emotion the text itself inferred. Lowering these trades that naturalness away for a flatter, more robotic-sounding delivery; raising them adds more variation, at some risk of instability on longer lines.
4. **Reference Voice Sample Criteria:**
   - **Length:** 4–7 seconds.
   - **Quality:** Studio clean (zero background noise, room reverb, or vocal fry).
   - **Delivery:** Calm, steady reading — this is the base voice being cloned, not the narration's final emotional range, which comes from the text itself (point 1 above).

---

## Reliability: Crashes, Interrupts & Resuming

TTS synthesis is the longest-running, most interruption-prone stage of the pipeline (one IndexTTS-2.5 call per panel, easily tens of minutes for a full chapter), so it's built to be safely stopped and resumed at any point:

- **Ctrl+C is safe.** It's caught gracefully, the IndexTTS-2.5 worker is asked to shut down cleanly (a few seconds), and a second Ctrl+C during that wait force-kills it instead of leaving it orphaned holding GPU memory.
- **Panel exports are atomic.** Each panel's WAV is written to a temp file and only renamed into place once fully written, so a kill mid-export can never leave a truncated clip that looks finished.
- **Resuming is conservative, not just fast.** `remanga tts` re-synthesizes the panel that was interrupted *and the two immediately before it*, instead of trusting whatever's already on disk near the resume point — cheap insurance against a truncated clip from an older run slipping through.
- **A wedged worker gets replaced automatically.** If IndexTTS-2.5 stops responding for longer than `tts.synth_timeout_seconds` (default 180s), the worker is killed and the next attempt spawns a fresh one, instead of the whole run hanging indefinitely with the model still loaded and the GPU sitting idle.

In short: if a chapter's TTS run gets interrupted or a worker locks up, just re-run the same command. Nothing needs to be cleaned up by hand.

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
./run.sh restart  -p <PROJECT> -c <CHAPTER> [-m hard|marks_only|soft] [-f] [--no-reverify]
```

---

## Workspace Directory Structure

```text
remanga/
├── bin/                        # Isolated standalone binaries (uv, ffmpeg, ffprobe)
├── .venv/                      # Main env - remanga's own lightweight core, no ML libs
├── .tools/
│   ├── venv-indextts/          # Isolated env - PyTorch + IndexTTS-2.5's own pins
│   └── venv-magi/              # Isolated env - PyTorch + MAGI v3's own pins
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
│               ├── pages.zip           # (Optional - off by default) raw pages bundled for manual LLM upload
│               ├── crops.json          # Panel crop coordinates from the Panel Marker web UI
│               ├── panels/             # Cropped individual panel images (full quality - video reads these)
│               ├── panels_manifest.json  # Per-panel crop bookkeeping (crop.py)
│               ├── chapter_info.json   # Project/manga/chapter identity, bundled into every package format below
│               ├── sheets/             # 2x2 vision contact sheets, full original resolution (generate.sheets, or auto-built for sheets_zip)
│               ├── panels_zip/         # (On by default) package format - individual panels - panels_1.zip, ...
│               ├── panels_pdf/         # (Off by default) package format - individual panels - panels_1.pdf, ...
│               ├── sheets_zip/         # (Off by default) package format - 2x2 sheet composites - sheets_1.zip, ...
│               ├── narration.json      # Synchronized narration script
│               ├── audio/              # Synthesized vocal WAV files per panel
│               ├── audio_timing.json   # Panel timeline synchronization map
│               ├── master_audio.wav    # Master audio track (Loudnorm + BGM)
│               ├── video/frames/       # Composited 1080p/2K/4K canvas frames
│               └── <project>_ch<num>_recap.mp4  # FINAL RECAP VIDEO
├── remanga/                    # Python core pipeline package
│   ├── audio/                  # synth.py (talks to the .tools/venv-indextts worker) & mix.py (master audio mixer)
│   │   └── scripts/             # indextts_worker.py - runs inside .tools/venv-indextts, not the main env
│   ├── cropper/                # crop.py (coordinate cropper) & sheets.py (contact sheet generator)
│   ├── downloader/             # mangadex.py (MangaDex client)
│   ├── models/                 # weights.py (talks to .tools/venv-indextts to fetch/verify weights)
│   │   └── scripts/             # download_indextts.py - runs inside .tools/venv-indextts
│   ├── webui/                  # Panel Marker: server.py (entry point/lifecycle), routes.py (Flask app/API),
│   │   │                       # marker_state.py (session state), detection.py + magi_assist.py (MAGI v3),
│   │   │                       # shortcuts_store.py (Shortcuts menu persistence)
│   │   ├── static/js/           # Frontend: render/drag-resize/draw/zoom-pan/shortcuts/magi/page-nav modules
│   │   └── scripts/             # magi_worker.py, download_magi.py - run inside .tools/venv-magi
│   ├── video/                  # compose.py (frame compositor) & render.py (GPU/CPU renderer)
│   ├── venvs.py                 # Locates the .tools/venv-indextts / .tools/venv-magi isolated environments
│   ├── console.py               # The one shared Rich Console every module prints through
│   ├── config.py                # Pydantic configuration schemas (load/save only)
│   ├── paths.py                 # Project/chapter directory layout & metadata persistence
│   ├── status.py                # Chapter production-status computation & display
│   ├── reset.py                 # Chapter restart/reset (hard / marks_only / soft)
│   ├── setup.py                 # Interactive Rich setup-wizard prompts
│   ├── json_io.py               # Shared JSON read/write helpers
│   ├── ffmpeg_io.py             # Shared ffmpeg subprocess helper
│   ├── wizard.py                # Interactive step-by-step production wizard
│   ├── wizard_prompts.py        # Project/chapter picker & resume-vs-restart prompts
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

### 2. A specific narration line sounds unstable, or too dramatic
Emotion/prosody is inferred straight from each panel's `text` and its punctuation now (see [Natural, Expressive Narration](#natural-expressive-narration)), so an over-the-top or unstable-sounding line usually traces back to what's actually written for that panel, not a synthesis bug:
- Check whether that panel's `narration.json` text over-punctuates — a line stacking multiple `!`/`?`/`...` reads as more dramatic than intended. `prompts/narration.md` Rule 3 asks the LLM to reserve emphatic punctuation for panels that genuinely call for it; if it slipped through anyway, trim the line's punctuation back to plain prose and re-run.
- Inspect your reference speaker WAV (`spk_audio_prompt`). A cleaner, steadier reference sample (see the criteria above) makes every inferred emotion sound more natural, not just calm ones.
- If a specific line still sounds unstable even with clean text and a clean reference, `tts.temperature`/`top_p` default to IndexTTS-2.5's own recommended `0.8`/`0.8` for natural-sounding delivery — nudging them down (e.g. `0.6`) trades some of that naturalness for more stability, as a last resort rather than a first fix.

### 3. NVENC GPU encoder error during video rendering
`bootstrap.sh` pins the bundled `bin/ffmpeg` to a specific, tested BtbN build (not the "latest" rolling one) precisely so NVENC works out of the box for a wide range of NVIDIA driver versions — a too-new build otherwise requires a driver version yours may not have yet, and it reports as a generic-looking failure. If GPU encoding still doesn't work:
- Rendering prints the actual encoder error instead of a silent fallback, e.g. `Driver does not support the required nvenc API version` — that tells you whether it's a real driver-too-old problem or something else.
- If it is a driver mismatch, `remanga` automatically tries a system-installed `ffmpeg` next (if one exists) before giving up on GPU entirely — nothing is installed for you, it only checks what's already on your machine.
- If your GPU genuinely doesn't support NVENC, or no working ffmpeg/driver combination is found anywhere, it falls back to CPU encoding (`libx264`) automatically.
- You can manually force CPU encoding by setting `"prefer_gpu": false` in `config.json`.

### 4. How do I get contact sheets instead of individual panels?
Panels are on (`panels_zip: true`) by default. To also get, or switch to, contact sheets:
- Run `./run.sh setup-config` and answer **Section 1 (What to Generate)** and **Section 2 (What to Zip/PDF for Upload)** in **Option 2 (Vision Outputs)** — check `sheets_zip`, uncheck `panels_zip` if you don't want both.
- Or set `"generate": {"sheets": true}` and `"package": {"sheets_zip": true, "panels_zip": false}` directly under `"cropper"` in `config.json`.

### 4b. What are the `panels_zip/`/`panels_pdf/`/`sheets_zip/` folders, and how do I configure them?
They're the [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) package formats — controllable as a checklist of exactly what you want built, e.g. "only the PDF" is a real, fully-supported answer. The **panels_zip is on by default** (one unsplit `panels_1.zip`); **panels_pdf and sheets_zip are off**. None replace `panels/`, and building any of them doesn't cost quality anywhere. Easiest way to change any of them: `./run.sh setup-config` step 2, **or** the main interactive wizard's own "Adjust what gets generated/zipped for this chapter?" prompt each run — both ask yes/no for each format, yes/no for splitting into size-capped parts, and the size cap, no manual editing needed. Or edit `config.json` directly — every setting for all three lives under one `"package"` object in the `"cropper"` section:
```json
"cropper": {
  "package": {
    "panels_zip": true, "panels_zip_split": false,
    "panels_pdf": false, "panels_pdf_split": false,
    "sheets_zip": false, "sheets_zip_split": false,
    "max_mb": 50.0
  }
}
```

### 5. Do I need a GPU to mark panels?
Only for the MAGI v3 auto-detect assist. Marking itself is manual clicking/dragging in the browser and needs no GPU at all — set `"magi_enabled": false` under `"marker"` in `config.json` to skip it and mark every panel by hand.

### 6. TTS synthesis seems frozen — GPU memory is loaded but nothing's happening
The worker now kills and replaces itself automatically after `tts.synth_timeout_seconds` (default 180s) of no response, so this should self-resolve on its own. If you're on an older run without that fix, or want to recover immediately: check `nvidia-smi` — a genuinely stuck worker shows near-idle GPU clocks/power draw despite holding VRAM. Kill the `indextts_worker.py` process (and the `remanga` process above it, or just Ctrl+C twice) and re-run the same command; see [Reliability](#reliability-crashes-interrupts--resuming) for why that's always safe to do.

### 7. A mark keeps snapping back to a different position while I'm dragging it
This was a real bug (fixed): a background MAGI detection poll could overwrite a page's marks mid-drag if that page's very first edit hadn't finished yet. Make sure you're on a current `remanga` checkout — it no longer happens. It's unrelated to the alignment guide lines, which are purely visual and never move a mark on their own.

---

## License

Distributed under the **MIT License**. See `LICENSE` for details.