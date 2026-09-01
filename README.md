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
- [Switching TTS Engines](#switching-tts-engines)
- [Step-by-Step CLI Production Workflow](#step-by-step-cli-production-workflow)
- [Resetting/Restarting a Chapter](#resettingrestarting-a-chapter)
- [Whole-Manga Video & Remixing BGM](#whole-manga-video--remixing-bgm)
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
- **One Flat Vision Output Checklist - What to Generate, What to Zip:**
  - Individual panel crops (`panels/`) are always produced. Everything else is an independent yes/no switch: `sheets` (contact sheets, 2x2 labeled composites merged at **full original resolution** - never downscaled), `sheets_zip`, `pdf`, `pdf_splite`, `pdf_zip`, `pdf_zip_splite`, `panels_zip`, `panels_zip_splites` - check any combination, losslessly re-encoded smaller than the raw files either way.
  - Configurable as a plain checklist, interactively (`./run.sh setup-config`, or a prompt in the main wizard each run) and persistent in `config.json` - see [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip).
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

After picking a project, the wizard asks which of five things you want to do:

```
1. Process a chapter
2. Compile the whole project into one continuous video (full-recap)
3. Change background music/volume and rebuild video(s) only (no re-narration)
4. Verify audio/video files are complete, not corrupt/truncated
5. Review narration only (no other stage runs before or after)
```

**Option 1** (the normal per-chapter flow):
```
┌─────────────────────────────────────────────────────────────┐
│ 1. Select or Create Project & Chapter                       │
│ 2. Verify Reference Voice WAV & BGM                         │
│ 3. Review/Adjust Vision Outputs (generate + zip checklist)  │
│ 4. Download Chapter Pages from MangaDex                     │
│ 5. Mark Panels (Panel Marker web UI, MAGI v3-assisted)      │
│ 6. Crop panels & package vision uploads                     │
│ 7. Prompt for narration.json (+ memory.json)                │
│ 8. Review Narration (Narration Reviewer web UI, N rounds)   │
│ 9. Synthesize Voice                                         │
│ 10. Mix Master Audio with EBU R128 Normalization             │
│ 11. Render Final 1080p / 2K / 4K MP4 Video                  │
└─────────────────────────────────────────────────────────────┘
```

**Option 2** (`full-recap`, see below) walks you through picking which chapters to include, then builds and keeps each chapter's own MP4 before joining all of them into one continuous video with a single BGM pass and a single loudness pass.

**Option 3** (`remix`, see below) is the fast path for "I just want different music, or a different volume" - pick which chapters, optionally point it at a new BGM file (or hop into `setup-config` first to change `bgm_volume_db`), and it re-mixes + re-renders just those chapters (and re-joins the full-recap video, if one exists) - no re-marking, no re-narrating, no re-synthesizing voice.

**Option 5** (`remanga review`, see [4b](#4b-review-the-narration-narration-reviewer-web-ui)) jumps straight into the Narration Reviewer for one chapter and stops there - no download/mark/crop before it, no TTS/mix/render after it, unlike Option 1 where the review step is one stage among the rest and falls straight through to voice synthesis the moment you approve or run out of flags. Use this to go back and do another review round on a chapter you already moved past, without re-running (or being forced into) anything else.

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
    "package": {
      "sheets": true,
      "sheets_zip": false,
      "pdf": false,
      "pdf_zip": false,
      "pdf_zip_splite": false,
      "panels_zip": false,
      "panels_zip_splites": false,
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

A few worth calling out specifically - `cropper.package` is the flat vision-output checklist, covered in full under [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) below:
- **`downloader.zip_pages_enabled`** (default `false`) — bundles the raw downloaded pages into `pages.zip`. Off by default because nothing downstream reads it; it's only useful if you want to hand a chapter's pages to an LLM by hand. Named for exactly what it zips (the downloaded *pages*) so it's never confused with `cropper.package` below, which zips something completely different.
- **`cropper.package.sheets`** (default `true`) — generates `sheets/` contact sheet composites. `cropper.package.sheets_zip` (below) builds them automatically the moment it's checked, whether or not this is also on. Every sheet is merged from its panels' **full original resolution** — never downscaled — with only lossless re-encoding used to keep the file size down.
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
*Creates:* `chapters/chapter_<num>/panels/` (source), this chapter's `panels` entry in the project's shared `manifest.json`, and - all under the project-level generated tree, not the chapter's source folder - `sheets/chapter_<num>/` (whenever it's actually needed - `package.sheets` on by default, or `package.sheets_zip` active), and whichever of `panels_zip/chapter_<num>/panels_1.zip`, `panels_pdf/chapter_<num>/panels_1.pdf` (or its zipped/split variants), `sheets_zip/chapter_<num>/sheets_1.zip`, and `sheets_folders/chapter_<num>/` (all off by default) are active per `cropper.package` (see [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) below).

### 4. Generate and Place `narration.json` + `memory.json`
Upload **any one** of your generated vision archives — whichever package formats are active (`panels_zip`, `pdf`, `sheets_zip`) — and `prompts/narration.md` to your LLM, attaching the project's current `memory.json` too, once it has real content, so continuity carries across chapters. **From chapter 2 onward, `memory.json` isn't optional** — the interactive wizard blocks and re-prompts until it has real content, since it's the only thing carrying character/plot continuity forward from the previous chapter. The prompt asks for **exactly two fenced JSON code blocks and nothing else** (no commentary before/after), so the LLM's reply can be copy-pasted straight into each file. The interactive wizard prints every archive actually available to upload this run as a ctrl+click-openable path (VS Code and similar editors), and both destination paths, when it gets to this step:
```text
projects/my_manga/chapters/chapter_1/narration.json   (Block 1)
projects/my_manga/memory.json                         (Block 2)
```
`memory.json` is auto-created as an empty placeholder the first time a project is touched, and updated in place chapter over chapter (carried-forward characters/factions, appended plot points, resolved/opened cliffhangers) — it's how the LLM keeps track of the story without re-reading every prior chapter.

### 4b. Review the Narration (Narration Reviewer web UI)
An LLM-written script still gets things wrong — a line attributed to the wrong speaker, a detail
that drifted from the art, a dropped bit of dialogue. Rather than trusting `narration.json` as
final the moment it's pasted in, the wizard opens the **Narration Reviewer**, a local web UI (same
shape as the Panel Marker) showing every panel's cropped image next to its narration line:
```bash
./run.sh review --project "my_manga" --chapter "1"
```
Flag any panel that's wrong with a short note on what's wrong (an optional tag — wrong speaker,
dropped content, spoiler, punctuation, word budget, continuity, other — helps but isn't required),
then either **Approve** (nothing flagged — continue straight to voice synthesis) or **Submit**.
Submitting writes `narration_review.json` and prints exactly what to upload to your LLM next:
`prompts/narration_review.md`, the current `narration.json`, `narration_review.json`,
`memory.json`, and `global/narration_lessons.json`. The LLM fixes only the flagged
panels (everything else is left untouched), then replies with three JSON blocks — the corrected
`narration.json`, an updated `memory.json`, and an updated `narration_lessons.json`. Save each one
over its file and the wizard reopens the reviewer for another round — repeat as many rounds as you
want; nothing moves on to TTS until you approve a round with zero flags (or explicitly choose not
to review further).

`narration_lessons.json` is the mechanism that makes review rounds compound over time: it lives at
`global/narration_lessons.json` (a sibling of `projects/`, not inside it - so it never shows up as
a bogus project in the wizard's project picker), and is **one file shared across every project**,
not per-manga. Every genuinely generalized lesson an LLM
writes there (phrased so it applies to any manga, not just this one — see
`prompts/narration_review.md`) gets read back in as a standing rule on every future chapter's
*first* narration pass (`prompts/narration.md`), for any project. A round's own history is kept
too, under `projects/my_manga/chapters/chapter_1/narration_reviews/round_<n>.json`, in case you
want to look back at what was flagged and fixed.

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

Every restart mode also wipes this chapter's ENTIRE generated tree — sheets, zips/PDFs, audio, video, all of it — under `{manga}/{kind}/chapter_<num>/` (see [Workspace Directory Structure](#workspace-directory-structure)), regardless of mode; the modes only differ in how much of the chapter's *source* folder (`pages/`, `crops.json`, `panels/`, `narration.json`) they keep. So a restart never leaves a stale sheet, zip, audio clip, or old rendered frame sitting around from before it.

---

## Whole-Manga Video & Remixing BGM

Two commands - both reachable from `remanga interactive`'s project-picker menu (options 2 and 3), no flags to remember - cover producing and then tweaking a whole manga's worth of chapters at once:

**`full-recap`** compiles every chapter of a project into ONE continuous video, instead of leaving you with N separate chapter MP4s to stitch together yourself:
```bash
./run.sh full-recap --project "my_manga" [--chapters 1,2,3] [--force]
```
It runs each chapter's remaining TTS/mix/render steps (skipping whatever's already cached) and **keeps every chapter's own MP4** — under `video/chapter_<num>/` — then builds the joined video separately: one continuous narration track, ONE background-music loop under the whole thing (a single fade-in at the very start, a single fade-out at the very end — never restarted per chapter), and ONE loudness-normalization pass, so there's no audible BGM restart or loudness jump at a chapter boundary the way naively concatenating N independently-mixed chapter videos would produce. The result lands at `video/<project>_full_recap.mp4`.

**`remix`** is the fast path once you've already rendered something and just want different music or a different volume:
```bash
./run.sh remix --project "my_manga" [--chapters 1,2] [--bgm new_song.wav] [--no-rejoin]
```
It re-mixes and re-renders only the chapters you name (default: all of them) — never touching TTS or frame compositing, the genuinely expensive steps — then re-joins the full-recap video too if one already exists, so it never silently drifts out of sync with a BGM change applied to its chapters. Pass `--bgm` to swap the music file itself; to change only `bgm_volume_db`, run `setup-config` first (or answer yes when the wizard's remix option offers to) and then remix with no `--bgm`.

---

## LLM Prompting & Vision Asset Guide

### Vision Outputs: What to Generate, What to Zip

One flat checklist under `cropper.package` in `config.json` - every switch is independent, named for exactly what it produces, check any combination. There's no "primary archive" concept to keep track of separately - every zip a chapter gets goes through `package` alone. Individual panel crops are always produced - that's what cropping a chapter means - everything below is extra, never touching `panels/` itself (still full quality, still what video rendering reads).

**File naming:** downloaded pages, cropped panels, and downloaded/cropped/marker directories all share one zero-padded scheme (`remanga/cropper/naming.py`):
- A page: `{chapter}_{page}` (e.g. `003_012.png` - chapter 3, page 12).
- A panel: `{chapter}_{page}_{panel}` (e.g. `003_012_02.png`) - `panel` resets to 1 at the start of every page, so it always answers "which panel on this page," not a running count across the chapter.
- A contact sheet: `{chapter}_{start_panel_name}_{end_panel_name}` - named after the inclusive range of panel names it merges.

Pages/panels/sheets directories are also kept clean automatically on every run - anything in them that doesn't belong (a stray leftover file, an old naming scheme, an interrupted-run remnant) is removed before the fresh download/crop/sheet-generation writes into them, so what's on disk always matches exactly what the current run produced.

**Manifest/info section:** every package format also carries an ordered list of every panel/sheet name it contains, so the LLM (or you) can spot anything missing just by comparing lists, without counting by hand:
- **Zip formats** (`panels_zip`, `sheets_zip`, `pdf_zip`, `pdf_zip_splite`): a `chapter_info.json` inside the zip carries `contents` (this part's items) and `full_manifest` (every item across every part).
- **PDF formats** (`pdf`, `pdf_splite`): the leading page(s) of the PDF render that same manifest as plain text (paginated if it's long) instead of a story panel.
- **Sheets** (`sheets`/`sheets_zip`): the very first sheet (`000_info`) is a plain text image with the same manifest, not a contact sheet of panels.

See `prompts/narration.md`'s **Chapter Identity** section for exactly how the LLM is expected to read all of this.

| Key (under `cropper.package`) | Default | Meaning |
|---|---|---|
| `sheets` | **On** | Build `sheets/` - 2x2 labeled contact sheet composites, merged at each panel's **full original resolution** (the composite canvas is sized *from* the panels, not the other way around - a sheet never loses detail a plain panel crop wouldn't also have). |
| `sheets_zip` | Off | Zip those contact sheets into `sheets_zip/sheets_1.zip` - fewer, denser images than individual panels, lower LLM vision-token cost. Builds `sheets/` automatically the moment this is checked, whether or not `sheets` above is also on. |
| `pdf` | Off | Build `panels_pdf/panels_1.pdf` - individual panels, one per PDF page, single file. |
| `pdf_splite` | Off | Same PDF content, split into size-capped raw `.pdf` files instead - `panels_pdf/panels_1.pdf`, `panels_2.pdf`, ... - **not zipped**. |
| `pdf_zip` | Off | The single PDF, wrapped in a zip - `panels_pdf/panels_1.zip` - for upload interfaces that only accept zip attachments. |
| `pdf_zip_splite` | Off | The PDF split into size-capped parts, each zipped separately - `panels_pdf/panels_1.zip`, `panels_2.zip`, .... |
| `panels_zip` | Off | Build `panels_zip/panels_1.zip` - individual panel crops, one file per panel, single file. |
| `panels_zip_splites` | Off | Same panels zip, split into size-capped parts instead - `panels_zip/panels_1.zip`, `panels_2.zip`, .... |
| `max_mb` | `50.0` | Size cap per part, in MB — shared by every format, only used when its `*splite*` switch is on. |

Every key's name says exactly what it does: `pdf` = single raw file, `pdf_splite` = split raw files (no zip), `pdf_zip` = single file zipped, `pdf_zip_splite` = split files, each zipped — same pattern for `panels_zip`/`panels_zip_splites`. So "only the PDF, nothing else" is exactly `pdf: true` with every other flag `false` — nothing else gets built, full stop. Whenever any `*splite*` switch for a format is on, every active switch for that format uses the split form (checking `pdf` and `pdf_zip_splite` together still only produces split output, not extra single-file output too). Reach this checklist two ways:
- `./run.sh setup-config` (step 2), the full settings walkthrough, **or**
- the main interactive wizard's own **"Adjust what gets generated/zipped for this chapter?"** prompt each run (defaults to No, so it never interrupts a normal run uninvited) — the same checklist, without needing to know `setup-config` exists separately.

How each package format stays lossless:
- **panels_zip / sheets_zip:** every image re-encoded as an optimized PNG and as a lossless WEBP, keeping whichever comes out smaller. Manga line art/halftones typically shrink 30-50% this way.
- **pdf / pdf_splite / pdf_zip / pdf_zip_splite:** every image is embedded as a `FlateDecode`-compressed raw bitmap (PDF's own native lossless image representation — the same class of compression a PNG uses internally, just packaged the way PDF expects), optionally TIFF-Predictor-2-filtered first for a better ratio. Pillow's own PDF writer re-encodes RGB images as lossy JPEG with no way to turn that off short of quantizing colors, which is why this is built directly rather than through Pillow's `Image.save(..., "PDF")`.
- Either way, a candidate re-encoding only ever gets used after decoding it back and verifying it's pixel-for-pixel identical to the original — anything that doesn't round-trip exactly is discarded in favor of a safer encoding (or the original file, for the zip formats).

Each part carries the same project/manga/chapter identity, plus which part it is, how many parts total, and that part's image range — as a `chapter_info.json` file for a panels_zip/sheets_zip/pdf_zip part, or as page 1 of a raw PDF part (rendered as plain, readable text, since a plain PDF can't hold a separate loose file the way a zip can) - true even with splitting off and a single part, so an LLM given only one part never has to guess whether more exist. See the "Chapter Identity" section of [`prompts/narration.md`](prompts/narration.md) for how the LLM is expected to read it.

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

## Switching TTS Engines

remanga can drive more than one text-to-speech engine, each in its own isolated `.tools/venv-*` environment (see [Fresh PC Installation & Setup](#fresh-pc-installation--setup)) so their dependency pins never have to share a resolution:

| Engine (`tts.engine`) | Cloning input | Notes |
|---|---|---|
| `indextts-2.5` (default) | Reference voice WAV only | Zero-shot - infers its own emotion/prosody from `narration.json`'s text and punctuation (see below) |
| `audio8-tts-0.1b` | Reference voice WAV **+ a text transcript of it** | [Audio8/Audio8-TTS-Preview-0.1b](https://huggingface.co/Audio8/Audio8-TTS-Preview-0.1b) - a ~170M-parameter Falcon-H1-based cloning model with its own 44.1kHz codec decoder |

Switch by running `./run.sh setup-config` (step 1, "TTS Engine") or editing `tts.engine` in `config.json` directly. `bootstrap.sh` already provisions both engines' isolated venvs (`.tools/venv-indextts`, `.tools/venv-audio8`) regardless of which one is active, so switching never requires re-running it — only that engine's own model weights get downloaded, and only the first time it's actually used (`checkpoints/audio8_tts_0.1b/`, ~1.7GB).

`audio8-tts-0.1b` needs one extra piece of configuration `indextts-2.5` doesn't: `tts.audio8.reference_text`, an accurate transcript of whatever WAV `tts.spk_audio_prompt` points at — the setup wizard asks for this right after the reference voice file whenever this engine is selected, since this model's cloning quality depends on transcript accuracy, not just the audio itself. `tts.audio8` also holds this engine's own `temperature`/`top_p`/`max_new_tokens` sampling settings, separate from `indextts-2.5`'s own top-level `temperature`/`top_p` fields.

Everything downstream — `remanga tts`, resuming, `full-recap`, `remix` — works identically regardless of which engine is active; `remanga/audio/synth.py`'s `create_synthesizer()` is the only place that picks between them.

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
./run.sh review   -p <PROJECT> -c <CHAPTER>
./run.sh tts      -p <PROJECT> -c <CHAPTER> [-v <VOICE_WAV>] [-f]
./run.sh mix      -p <PROJECT> -c <CHAPTER> [-b <BGM_FILE>]
./run.sh render   -p <PROJECT> -c <CHAPTER> [-f]
./run.sh full-recap -p <PROJECT> [-c <CHAPTER1,CHAPTER2,...>] [-f]
./run.sh remix    -p <PROJECT> [-c <CHAPTER1,CHAPTER2,...>] [-b <BGM_FILE>] [--no-rejoin]
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
│       ├── manifest.json       # Per-chapter pages/panels bookkeeping, one shared file (informational only)
│       ├── chapters/
│       │   └── chapter_<num>/          # SOURCE ONLY - the handful of things nothing else can regenerate
│       │       ├── pages/              # Raw downloaded chapter pages
│       │       ├── crops.json          # Panel crop coordinates from the Panel Marker web UI
│       │       ├── panels/             # Cropped individual panel images (full quality - video reads these)
│       │       └── narration.json      # Synchronized narration script
│       │
│       # Everything below is GENERATED - one shared, per-kind, per-chapter tree,
│       # never mixed into the source chapter folder above. A restart (any mode)
│       # wipes a chapter's entry here in full; the source folder above is what
│       # each restart mode chooses how much of to keep. See remanga/paths.py.
│       ├── pages_zip/chapter_<num>/pages.zip       # (Optional - off by default)
│       ├── sheets/chapter_<num>/                   # 2x2 vision contact sheets (on by default, or auto-built for sheets_zip)
│       ├── sheets_zip/chapter_<num>/sheets_1.zip    # (Off by default) package format
│       ├── sheets_folders/chapter_<num>/folder_1/   # (Off by default) package format - no compositing, plain numbered folders
│       ├── panels_zip/chapter_<num>/panels_1.zip    # (Off by default) package format
│       ├── panels_pdf/chapter_<num>/panels_1.pdf    # (Off by default) package format
│       ├── audio/chapter_<num>/                    # Synthesized vocal WAV per panel + audio_timing.json + master_audio.wav
│       └── video/                                  # Only ever holds finished MP4s at each level - see below
│           ├── chapter_<num>/
│           │   ├── _work/                          # frames/, concat_list.txt - build artifacts, not deliverables
│           │   └── <project>_ch<num>_recap.mp4      # This chapter's own video (kept - see `remix` below)
│           ├── _work/                               # full-recap's own master audio/concat list
│           └── <project>_full_recap.mp4             # `full-recap`'s whole-manga joined video
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
Contact sheets (`sheets`) are on by default; `panels_zip` is off. To get individual panels instead of, or in addition to, sheets:
- Run `./run.sh setup-config` and answer the checklist in **Option 2 (Vision Outputs)** — check `panels_zip`, uncheck `sheets`/`sheets_zip` if you don't want both.
- Or set `"package": {"sheets": false, "panels_zip": true}` directly under `"cropper"` in `config.json`.

### 4b. What are the `panels_zip/`/`panels_pdf/`/`sheets_zip/` folders, and how do I configure them?
They're the [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) package formats — controllable as a checklist of exactly what you want built, e.g. "only the PDF" is a real, fully-supported answer. **`sheets` is on by default**; every zip/PDF format (`sheets_zip`, `pdf`, `pdf_splite`, `pdf_zip`, `pdf_zip_splite`, `panels_zip`, `panels_zip_splites`) is off. None replace `panels/`, and building any of them doesn't cost quality anywhere. Easiest way to change any of them: `./run.sh setup-config` step 2, **or** the main interactive wizard's own "Adjust what gets generated/zipped for this chapter?" prompt each run — both ask yes/no for each switch, plus the size cap when a split switch is on, no manual editing needed. Or edit `config.json` directly — every setting lives under one `"package"` object in the `"cropper"` section:
```json
"cropper": {
  "package": {
    "sheets": true, "sheets_zip": false,
    "pdf": false, "pdf_splite": false, "pdf_zip": false, "pdf_zip_splite": false,
    "panels_zip": false, "panels_zip_splites": false,
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