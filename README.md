# remanga

**remanga** is a 100% self-contained, modular manga recap video production engine. Powered by **Kokoro-82M**, it automates manga downloading, MAGI v3-assisted panel marking via a local web UI, LLM-guided narration writing, vision packaging, naturally expressive vocal synthesis, audio mastering with EBU R128 normalization, and GPU-accelerated video rendering.

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
  - [YouTube Upload Text](#youtube-upload-text-promptsyoutubemd)
- [Narration Voice & Delivery](#narration-voice--delivery)
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
- **Fast, Consistent Vocal Synthesis (Kokoro-82M):**
  - One even narrator register for the whole recap — the delivery is cloned from the reference clip and stays consistent panel to panel, instead of lurching between emotional registers while it describes what happens.
  - **48x faster than real time** on an RTX 3060 (measured): a 450-panel recap synthesizes in under a minute instead of 58.
  - 54 built-in studio voices, graded A–F by the model's authors and shown with their grades in the picker — no reference clip, no cloning, no transcript.
  - Apache-2.0 weights, 327MB, ~2-3GB VRAM — see [The TTS Engine](#the-tts-engine).
- **Strict Temporal Horizon Prompting (Anti-Spoiler & Anti-Hallucination):**
  - Forbids unintroduced character names, future plot reveals, motives, or hallucinated actions.
  - Strict 0–1000 normalized integer bounding box coordinate system (`[ymin, xmin, ymax, xmax]`).
- **Broadcast Audio Mastering:**
  - Per-panel 35ms micro edge-fading to eliminate digital clicks.
  - Optional background music (BGM) looping at a fixed gain, with one loudness-normalization pass over the finished master.
  - Broadcast EBU R128 loudness normalization (`-16 LUFS`).
- **Multi-Resolution Video Compositor & GPU Renderer:**
  - Presets for **1080p Full HD**, **1440p 2K QHD**, **2160p 4K UHD**, and **720p HD**.
  - Fast Bokeh Canvas Blur (<1.5ms per frame) or Solid Black canvas.
  - Automatic NVIDIA NVENC GPU hardware encoding (`h264_nvenc`) with automatic CPU fallback (`libx264`).
- **Safe to Interrupt, Safe to Resume:** Ctrl+C (or a crash) mid-synthesis never leaves a corrupt clip behind — panel exports are atomic, and resuming automatically re-synthesizes the panel that was interrupted plus the two just before it, rather than trusting whatever's on disk. A worker that stops responding gets killed and replaced automatically instead of hanging forever. See [Reliability](#reliability-crashes-interrupts--resuming).
- **Three-Tier Chapter Reset:** hard (keep only downloads), marks-only (also keep your panel marks), or soft (also keep the cropped panels and narration script) — pick how much work to throw away. See [Resetting/Restarting a Chapter](#resettingrestarting-a-chapter).

---

## System Requirements

`bootstrap.sh` detects the machine it runs on and installs what fits it, so
there is no single required configuration. A GPU makes synthesis and
rendering dramatically faster; nothing here *requires* one.

| Component | Minimum | Recommended |
|---|---|---|
| **Operating System** | Linux, macOS, or Windows (native via Git Bash, or WSL2) | Linux or WSL2 |
| **Architecture** | x86_64 or arm64 (Apple Silicon, ARM laptops, ARM servers) | x86_64 |
| **GPU** | none — CPU-only works, just slowly | 8 GB+ VRAM (RTX 3060/4060 or better) |
| **CPU** | 4 cores | 8+ cores |
| **RAM** | 8 GB | 16 GB+ |
| **Disk Space** | 20 GB free (five isolated venvs + models + workspace) | 35 GB+ SSD |

**What gets installed for which machine**, decided by `remanga/hardware.py`
and reported by `./run.sh hardware`:

| Machine | PyTorch wheels | Video encoder |
|---|---|---|
| NVIDIA, driver 580+ | `cu129` | `h264_nvenc` |
| NVIDIA, driver 525+ (528+ on Windows) | `cu128` | `h264_nvenc` |
| NVIDIA, driver older than that | `cpu` + a warning | `h264_nvenc` (probed, falls back) |
| AMD with ROCm (Linux) | `rocm6.4` | `h264_vaapi` |
| Apple Silicon | default PyPI (Metal/MPS) | `h264_videotoolbox` |
| Anything else | `cpu` | `libx264` |

Why the CUDA index isn't simply "the newest your driver supports":
This project targets `torch==2.8.*`, and PyTorch's `cu130` index starts at 2.9
while `cu118` stops at 2.7 — neither has it. The table above picks the
newest index that the driver can run *and* that still carries 2.8.

Override the choice at any time:
```bash
REMANGA_TORCH_BACKEND=cpu bash bootstrap.sh      # skip the ~2.5 GB CUDA download
REMANGA_TORCH_BACKEND=cu126 bash bootstrap.sh    # pin a different index
```

---

## Fresh PC Installation & Setup

Follow these steps to set up `remanga` from scratch on a new machine.

### Step 1: Install System Prerequisites
Ubuntu / Debian / WSL2:
```bash
sudo apt update && sudo apt install -y git curl wget tar bzip2 unzip libgl1 libglib2.0-0
```
macOS (ffmpeg is not bundled for macOS — there is no static build to fetch):
```bash
brew install git curl ffmpeg
```
Windows: either **WSL2** (recommended, with NVIDIA drivers on the Windows
host) or native **Git Bash**, where `bootstrap.sh` fetches the `win64` /
`winarm64` ffmpeg build and `uv.exe` for you.

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
0. **Detects this machine** — OS, CPU architecture, and whether there's an
   NVIDIA, AMD or Apple GPU — and picks the matching PyTorch wheel index,
   ffmpeg build and video encoder from it. Everything below follows from
   that one answer, so the same script provisions a CUDA box, an Apple
   laptop and a CPU-only server without being edited. Re-check what it
   decided at any time with `./run.sh hardware`. It never aborts on an
   optional step: anything skipped is listed as a warning in its summary.
1. Downloads and provisions static `bin/uv`, `bin/ffmpeg`, and `bin/ffprobe` for this platform (macOS uses the system ffmpeg) — `ffmpeg` is pinned to a specific tested build rather than always the newest one, so its NVENC GPU encoder keeps working across a wide range of NVIDIA driver versions instead of silently requiring whatever driver was newest the day it was compiled (see [Troubleshooting #3](#troubleshooting--faq)).
2. Provisions **five** isolated Python 3.11 virtual environments instead of one, each installed from the wheel index this machine needs:
   - `.venv/` — remanga's own lightweight core (Pillow, Pydantic, requests, rich, pydub, Flask). No ML libraries at all.
   - `.tools/venv-kokoro/` — PyTorch + Kokoro and its misaki/spaCy G2P stack.
   - `.tools/venv-magi/` — PyTorch + MAGI v3's own pinned dependencies (including a `transformers` capped below its DaViT-breaking `4.52`).

MAGI v3 pins `transformers<4.52` and DeepSeek-OCR-2 pins `==4.46.3` — separate environments mean neither can ever silently break the other. The main env only ever talks to them as subprocesses (see `remanga/venvs.py`); the storage trade-off buys permanent isolation instead of a pin that has to be babysat.
3. Turbo-downloads official `hexgrad/Kokoro-82M` weights into `checkpoints/kokoro_82m` and `ragavsachdeva/magiv3` weights into `checkpoints/magiv3`.
5. Initializes default `config.json`.

---

## Quick Start: Master Interactive Wizard

The easiest way to produce a recap video is through the interactive terminal wizard:

```bash
./pipeline.sh
```
*(or run `./run.sh interactive`)*

### How the menus work

Every screen is an arrow-key menu — **↑/↓** to move, **Enter** to pick, **type to filter**, **Esc** to back out one level, **Ctrl+Q** (or the **Exit remanga** row every menu ends with) to quit outright from wherever you are, however deep. Checklists add **Space** to toggle (**Ctrl+A** all, **Ctrl+R** none), and confirmations take **y**/**n** as well as Enter. Whatever is currently configured is pre-highlighted, so Enter alone is always "leave it as it is". Nothing has to be typed from memory: the wizard lists what's actually there. The few places you do type — a project name, a chapter number, a path — are full readline lines: ←/→ move the cursor, Home/End jump, Ctrl+A/Ctrl+E/Ctrl+W and friends work, and ↑/↓ walk that prompt's history.

```
? remanga — MyProject
❯ Setup                settings, shared assets, and model weights
  Chapter Production   one chapter, from download to rendered video
  Project-wide         set the whole manga up, compile it, check it, clean it up
  Pipeline             download → mark → crop → narration → review → tts → mix → render
  Switch project       currently: MyProject
  Quit
  Exit remanga         quit from here
  ↑↓ move · enter select · type to filter · esc back · ctrl+q exit
```

Short, fixed lists are **numbered** instead, so picking one is a single keystroke rather than an arrow and an Enter. Type the number to pick it, `0` to back out (the same convention the non-tty fallback prompts have always used); the arrow keys still work.

Six commands have a menu of their own — `tts`, `mix`, `render`, `crop`, `full-recap` and `remix` — because the voice, the pacing, the levels, the music and the resolution are things you notice at the moment you go to run them, not while walking through `setup-config`. Row 1 runs the command; the rest are the settings it reads, each stating its current value and opening the same screen the settings menu opens:

```
? tts
  Generate vocal audio from narration.json · or change what it runs with
❯ 1. Run tts  Generate vocal audio from narration.json
  2. TTS engine  Kokoro-82M · Heart (female)
  3. Narrator voice  Heart (female) (af_heart, grade A)
  4. Narration language  English (EN)
  5. Narration pacing  1x speed · 350ms between panels
     Back
     Exit remanga  quit from here
  uses the configured voice and engine unless you pick otherwise
  type 1-5 · ↑↓ move · enter select · 0 or esc back · ctrl+q exit
```

```
? render
  Render final recap MP4 video · or change what it runs with
❯ 1. Run render  Render final recap MP4 video
  2. Video resolution  1080p Full HD (1920x1080)
  3. Canvas background  Bokeh canvas blur
  4. Hardware acceleration  h264_nvenc preferred
  5. Panel framing  4% padding (adaptive) · 2px border
     Back
  renders at the resolution, background and encoder set below
  type 1-5 · ↑↓ move · enter select · 0 or esc back · ctrl+q exit
```

The rows are pointers, not copies — each runs the very same function `setup-config` runs, so the two can never describe a setting differently. Commands with no settings behind them (`download`, `crop`, `mark`, …) still run straight away. On the CLI nothing changed: `remanga tts` synthesizes a chapter, and every setting keeps its own screen under `setup-config`.

Picking a category opens its commands, and running one lands you back in the same list — chaining `mark` → `crop` → `write` is picking three rows in a row. The menu is generated from the command registry, so every command `remanga --help` lists is here too, described the same way.

**The wizard doesn't ask for anything it can find out:**

| Question | Where the answer comes from instead |
| --- | --- |
| Which chapter? | The chapters this project has, each row showing its production status; "New chapter…" is pre-filled with the first chapter **MangaDex lists that you don't have yet** — not "one more than your newest", which is the same number only for gapless whole-number manga (a project on 4.1 needs 4.2, not 5.1) |
| Which manga/URL? | `project.json`'s saved source — asked once, on the first download |
| Which way does it read? | MangaDex's `originalLanguage` (`ja` → right-to-left, `ko`/`zh` → left-to-right) |
| Which engine / voice / music this run? | Not asked at all — what's configured is stated and used. All three are set once and kept, so `--engine`/`--voice`/`--bgm` cover the rare one-off and the settings screens cover a permanent change |
| Which voice / music file? | The voice is a **pick from a list** — Kokoro's own named voices, shown with the grade Kokoro published for each, no file involved. Music is a file picker over `global/bgm/`, or type a path for one elsewhere |
| What to keep when wiping? | A checklist of exactly what that chapter has on disk right now — and what you picked last time, remembered per project |
| What to package for the LLM? | A checklist of every format, opened on what this project builds — your pick is remembered for the next chapter |
| Which pipeline steps? | An ordered checklist of the real step registry — the number shown is the run order, and it opens on the steps you ran last time. Confirming it saves the pipeline and shows it back to you; it never starts a run by itself |
| Which restart mode? | The four presets, each row saying what survives it |

Chapter production runs in order — download → mark panels → crop → package → narration → review → TTS → mix → render — either step by step from the menu, or in one go with `run`, which follows the steps this project has chosen. Choosing them is the same ordered checklist the main menu's **Pipeline** row opens, and confirming it saves: pick "tts, mix, render" once because the render died, and every later run opens on exactly that, already ticked, in that order. There's one stored list per project (`project.json`'s `pipeline`), so `run`, the Pipeline row and the CLI can't disagree about what the pipeline is. `--steps` on the CLI stays a true one-off — it never saves.

**Setting up a pipeline and running one are two different moments.** Ticking the last box in the checklist doesn't start anything: it hands back to the pipeline's staging screen, which writes the plan out in order — position, step name, what that step does — and then asks. Running it is a row you choose on purpose, and so is changing the list and looking again. Both doors lead here: the main menu's **Pipeline** row (which asks for a chapter only once you actually pick Run), and `run`, which asks for the chapter first and then stages the same screen against it.

```
Pipeline for 'MyProject' — 11 step(s), in this order
   1. download        Download chapter pages from MangaDex
   2. mark            Mark panels via the Panel Marker web UI (writes crops.json)
   3. crop            Crop panels out of the marked pages
   4. package         Package the panels into the chosen upload formats (sheets/zips/PDF)
   5. init-narration  Create a completely empty narration.json - zero bytes, not even {} - for the script to be written into
   6. pause           Wait for Enter before going on - room to fill something in by hand first
   7. narration       Write narration.json + memory.json via LLM copy/paste
   8. review          Review narration via the Narration Reviewer web UI
   9. tts             Synthesize vocal audio via TTS
  10. mix             Mix master audio track (narration + BGM + loudnorm)
  11. render          Render the final recap video

? Pipeline — MyProject
  the steps above are saved for this project · nothing runs until you say Run
❯ 1. Run the pipeline  asks which chapter
  2. Choose steps      download → mark → crop → package → init-narration → pause → narration → …
     Back
```

**`init-narration`** puts the chapter's `narration.json` on disk as a genuinely empty file — zero bytes, not `{}`, not `[]`, nothing at all — so the script has a place to be written into before anything tries to write it. Zero bytes is the placeholder state the rest of remanga already understands: every "has this chapter been narrated yet?" question is answered by file size, so an empty `narration.json` reads as *not written yet* to the status panel, to `verify` and to the `narration` step. The file exists, the chapter is still honestly unnarrated, and no later stage is fooled into thinking there's a script here. A chapter that already has a written script is never blanked on the way past: it asks, with **No** as the answer Enter gives, and a piped or scripted run keeps the file without asking — nobody is there to say no, and that file is the one thing in a chapter that can't be rebuilt from anything else on disk.

**`pause`** is a stage that does nothing but stop. Every other step runs something; this one holds a place in the order for work that isn't remanga's — filling in the `narration.json` that `init-narration` just left empty, dropping a file into the chapter folder, checking a crop by eye. It prints the chapter folder and waits; Enter continues to the next stage. Without it, "let the pipeline get this far, then let me do a thing, then let it carry on" means running two pipelines and remembering where the seam was. A non-interactive run doesn't wait — there's no one to press Enter, and a piped `run` blocking on stdin would turn a checkpoint into a hang.

If stdin isn't a terminal (a piped script, CI, an editor's output pane), every menu falls back to the plain numbered prompts remanga has always had, with `0` as back/quit at each level.

---

## Configuration & Settings Wizard

**config.json is this machine; each manga can disagree with it.** Where ffmpeg lives, whether to prefer the GPU, which port the web UIs open on — those describe your PC, so they live in `config.json` and apply everywhere. But the narrator's voice, the background music, the resolution, the canvas style and the crop settings describe *the work*, and a dark fantasy series shouldn't have to sound like the school comedy you set up last month. Change any of those from inside a project — the wizard, or any CLI command that takes `-p` — and they're saved as that project's own, in its `project.json`:

```json
"settings": {
  "tts.kokoro.voice": "am_fenrir",
  "audio.bgm_path": "global/bgm/Dread.wav",
  "video.height": 1440
}
```

Only what you actually changed is stored; everything else follows `config.json`, so raising the global resolution moves every project that never picked its own. Put a setting back to the machine value and it stops being an override. `tts.*`, `audio.*`, `video.*` and `cropper.*` work this way; machine-wide settings edited from inside a project still go to `config.json`, and the packaging formats keep their own per-project list (`package_formats`, see [3b](#3b-package-the-upload-formats)). Nothing is migrated: a project with no `settings` block behaves exactly as it did.

Run the settings screen anytime to configure the TTS engine, vocal reference files, background music, narration language, video resolution, canvas background, GPU preference, and vision outputs (what to generate, what to zip/PDF for upload):

```bash
./run.sh setup-config
```

Every row shows what that setting is **right now**, so the screen doubles as a place to check your configuration rather than only change it — open one to change just that one, or pick **Walk through every section** for a first-time setup that covers all of them in order. Each change saves to `config.json` immediately, so backing out never loses an answer you already gave.

```
? Settings
  changes save immediately
❯ TTS engine                              Kokoro-82M · Heart (female)
  Narrator voice                          Heart (female) (af_heart, grade A)
  Assets (BGM)                            bgm: ok
  Narration language                      English (EN)
  Narration pacing                        1x speed · 350ms between panels
  Audio levels                            voice +0.0dB · music -26.0dB · normalized
  Panel detection                         MAGI, gutter-snap, trim, dedupe
  Panel framing                           4% padding (adaptive) · 2px border
  Vision outputs (what to generate/zip)   sheets, panels_zip (split at 50MB)
  Video resolution                        1080p Full HD (1920x1080)
  Canvas background                       Bokeh canvas blur
  Hardware acceleration                   auto preferred
  Walk through every section              first-time setup, in order
  Show full summary                       everything config.json holds
  Done
```

Just need to swap the BGM file? `./run.sh paths` opens that same Assets screen on its own — showing whether it currently resolves to a real file, with a picker listing the audio files already in `global/bgm/` so you rarely have to type a path at all. It lives under `global/` by default — one shared, gitignored location for assets that aren't tied to any single manga project. (The narrator's voice isn't here: it's a name from Kokoro's own catalogue, so it has its own **Narrator voice** picker row.)

### Tuning how it sounds and looks

Four screens cover the settings you find by watching a chapter back and adjusting — the ones that used to be reachable only by hand-editing `config.json`:

| Screen | Controls | Where it also appears |
|---|---|---|
| **Narration pacing** | narration speed, and the silence held after each panel | under `tts` |
| **Audio levels** | narration gain, music gain, loudness normalization on/off | under `mix` |
| **Panel detection** | MAGI auto-detection, gutter-snap, whitespace trim, duplicate dropping | under `crop` |
| **Panel framing** | padding around each panel, adaptive padding, bokeh brightness, border width | under `render` |

They're grouped by the question you're actually asking, not by which config block the answer lives in — "the narration is too fast" shouldn't require knowing that speed is a `tts` setting while the gap between panels is an `audio` one.

Two things worth knowing before you turn these:

- **Raising the narration mostly turns the music *down*.** With loudness normalization on (the default), the finished master is pulled to a fixed target afterwards, so boosting the voice pushes the BGM under it rather than making the file louder. Turn off **Audio levels → normalize** if you want the boost to survive into the absolute output level.
- **Changing the narration gain does not force a re-synthesis.** `audio_timing.json` records the gain already baked into the clips on disk, and the next `tts` run applies only the difference to clips it would otherwise reuse.

Every **Panel detection** pass is normally right and occasionally wrong on an unusual layout — a splash page, a double-page spread, art that bleeds to the edge. Being able to switch one off without editing JSON is the difference between diagnosing a bad crop in a minute and giving up on the chapter.

### Key Configurable Parameters (`config.json`):

```json
{
  "system": {
    "prefer_gpu": true,
    "gpu_codec": "auto",
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
    "engine": "kokoro",
    "lang": "EN",
    "speed": 1.0,
    "synth_timeout_seconds": 180,
    "kokoro": {
      "hf_repo_id": "hexgrad/Kokoro-82M",
      "model_dir": "checkpoints/kokoro_82m",
      "voice": "af_heart",
      "volume_boost_db": 0.0,
      "sample_rate": 24000
    }
  },
  "audio": {
    "sample_rate": 44100,
    "edge_fade_ms": 35,
    "pause_between_panels_ms": 350,
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
- **`marker.auto_detect_scope`** (default `"chapter"`), **`marker.auto_save`** (default `true`) and **`marker.auto_order`** (default `false`) — the action bar's scope and Options switches, written by the marker itself when you change them in the browser. See [Mark Panels](#2-mark-panels).
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

**The whole manga in one go** — `download-all` (Project-wide in the wizard) takes every chapter MangaDex lists for this project, with no picker and no selection to make:
```bash
./run.sh download-all --project "my_manga"
```
It fetches the feed in the configured translation language (`downloader.language`, `en` by default) and, where a chapter number appears more than once — two scanlation groups, or one of them re-uploading a fix — takes **the newest upload of it**. Left alone that duplication shows up as the same chapter listed twice in the picker and a download that takes whichever copy the API happened to return first, which is not a choice anyone made and can differ between two runs of the same command; now the picker and the download agree, and both mean "the latest one".

It prints how many chapters exist and how many you already have, then asks once before starting. Chapters already downloaded are *verified*, not re-fetched, so re-running it after a new chapter drops costs a check per chapter and downloads only what's actually missing. `--force` re-fetches every chapter clean instead.

### 2. Mark Panels
Launches the **Panel Marker** web UI: draw panel boxes yourself, or press **Detect** and MAGI v3 finds them on a GPU; you drag/adjust/delete to correct them, then Save & Continue writes `crops.json`. Nothing is detected until you press Detect.
```bash
./run.sh mark --project "my_manga" --chapter "1"
```
*Creates:* `projects/my_manga/chapters/chapter_1/crops.json` — see [Panel Marker Web UI](#panel-marker-web-ui) below.

**Every chapter in one tab** — `mark-all` (Project-wide in the wizard) hands the marker the whole project instead of one chapter:
```bash
./run.sh mark-all --project "my_manga"
./run.sh mark-all --project "my_manga" --chapters 4,5,6
```
One server, one browser tab, one session. **Save & Next chapter** writes that chapter's `crops.json` and swaps the next chapter's pages into the page already open — no reload, so the zoom, the tool and the shortcuts survive it — and the **‹ Ch › arrows** in the top bar go back to a chapter already done, so checking chapter 3's marks after finishing chapter 9 costs a click rather than another run of the command. Leaving a chapter always writes its `crops.json` first, so nothing lives only in the server's memory. **Finish here** ends the session early and leaves the remaining chapters unmarked; it asks first, because the terminal is blocked on the session and closing the tab tells it nothing.

Chapters with nothing downloaded are named and skipped before the browser opens.

**You choose which pages, and what to do with them.** The top of the sidebar is the **action bar**, pinned above the *This page / All chapters* tabs so it stays on screen whichever one is open: one scope picker and three buttons —

```
[ This chapter            ▾ ]
[ ✦ Detect ] [ ⇅ Reorder ] [ ✂ Recrop ]
━━━━━━━━━━━━━━━━  Done · detected 3 chapters
› Options · auto-order
```

**Detect** (MAGI finds the panels), **Reorder** (renumber them into reading order) and **Recrop** (cut fresh panel images from the marks). All three take the same scope:

| Scope | What the buttons work on |
|---|---|
| **This page** | just the page on screen (Detect and Reorder — Recrop is greyed out, see below) |
| **This chapter** | the chapter on screen (what the button always used to mean) |
| **Chapter range…** | every chapter from one to another, inclusive — a from/to pair of dropdowns, opening on *this chapter → the last one* |
| **All chapters** | every chapter in the session |

Each button's tooltip says what it does. The three switches fold away under **Options**, and the fold's summary line names the ones that are on, so auto-order quietly re-sorting pages is never hidden just because Options is closed.

The range is the one that pays for itself: *"the power went out somewhere around chapter 9"* is a from/to, and saying it any other way is either nine trips through the UI or redetecting a manga that was already three-quarters done. Reversed is fine — pick 9 then 4 and it means the same span.

**Reorder** puts each page's panels into the order a reader meets them — the panel number *is* the narration order, because it becomes `panel_id`. It runs immediately, not in the detection queue, so it never waits behind a long detection run. The ordering is a recursive XY-cut: split the page at a gutter running across every panel and read above before below; failing that, split at a vertical gutter and read the side your manga starts on first (right for right-to-left, from the project's reading direction); then do the same inside each part. A grid beside a tall panel is read row by row, and a tall panel beside a stack comes before or after it depending only on which side it's on.

Real marks overlap their neighbours by 20–70px (MAGI's boxes take in borders and bleed), so a "gutter" allows an overlap of up to a quarter of the smaller panel, not a fixed few pixels. Where no gutter exists at all, panels count as one row only when their **tops line up** — an inset slanting across the bottom of a big panel overlaps it, but is read after it. Checked against a fully narrated project, where the saved order is order a person already verified: it agrees on **126 of 126** pages with two or more panels.

**Recrop** is `./run.sh crop --force` from the browser: for each chapter in scope, the marks are written to `crops.json` if the session holds changes that aren't on disk yet (even with auto-save off — pressing Recrop is asking for panels cut from what's on screen), then `panels/` is cleared and every panel is cut again. A chapter with no unsaved changes is cropped from its `crops.json` as it stands and isn't rewritten. It works on whole chapters only, because the cropper does, and it has its own worker: it never waits behind a detection run, and chapters with no marks at all are left alone.

Recropping a chapter that **already has narration** asks first. If its marks haven't changed since it was narrated, nothing changes — the same panels come out under the same names. But if a panel was moved, added, removed or reordered, its `narration.json` now names panels that don't exist, and TTS and render will stop on that chapter until the narration is updated. After the run each chapter is checked against its narration, and any mismatch stays in the bar in red (details in its tooltip) until the next Recrop, rather than surfacing an hour later when a render refuses to start.

**`Auto-order panels`** decides who owns the order:

- **On:** every chapter stays in reading order. Turning it on reorders the chapter on screen immediately and every other chapter in the session in the background (saving each one that changed); from then on a page is re-sorted every time it's saved, and MAGI's detections arrive already sorted. The drag handles leave the panel list, since a dragged order would be undone on the next save.
- **Off:** the order is yours. Nothing re-sorts anything, the handles come back, and whatever order you drag panels into is saved as-is — which is what the rare page the algorithm gets wrong needs. The Reorder button still works for a one-off pass.

Where a mark came from also survives a save now. `crops.json` used not to record it, so every chapter reopened with **every** mark tagged manual — and with background auto-save, that was every chapter. Each panel now carries `src`; files written before that can't say, and read as manual.

**Detecting a whole project** is **Detect** with *All chapters* (or a range): the chapters are queued and worked through in the background while you mark the one in front of you, so arriving at chapter 6 finds it already detected instead of starting a wait. Nothing is detected on its own — not when the marker opens, and not when you move to another chapter. What gets marked, and when, is your call. **`Auto-save chapters`** controls whether a chapter's `crops.json` is written without being asked for — when you leave it, and when the background detector finishes one. The switches and the scope are **saved into `config.json`** (`marker.auto_save`, `marker.auto_order`, `marker.auto_detect_scope`) and apply to the next session and the next project: they describe how you work, not anything about today's manga.

Everything here is safe on a half-finished project, which is the point:

- **A page you have edited is never overwritten.** The server refuses to apply a detection to a page with marks on it, so the widest scope still only fills in what's actually missing.
- **An empty page and an empty page are not the same thing.** A page you emptied on purpose (a title page, an ad, credits) is a decision MAGI must not overturn; a page that simply hasn't been marked yet is exactly what MAGI is for. `crops.json` records which is which per page (`user_decided`, alongside a `marks_format` marker on the file), so a chapter written before its detection finished — you left it early, or the background worker saved it — doesn't come back with every undetected page frozen as "no panels here". The sidebar shows the difference: a page reads <code>3</code> panels, <code>—</code> (emptied on purpose) or a dashed <code>0</code> (not marked yet), and each chapter's header counts the pages still waiting.
- **Only emptying a page decides it — visiting one doesn't.** The browser autosaves the page you're *leaving*, so paging through a chapter to look at it posts an unchanged empty list for every page on the way. That is not an edit, and it no longer counts as one: a page becomes "deliberately empty" when its marks go from something to nothing (you deleted the last one), not when you scrolled past it. Otherwise browsing a chapter would quietly exclude every blank page you passed.
- Running *This page* on a page recorded as having no panels **does** detect it — naming one page is asking for that page, and there is nothing on it to lose. A page with marks is still refused. That's also the way out for a chapter frozen by a `crops.json` written before this existed: such files keep the old, protective reading (every empty page counts as a decision), since they can't be asked what was meant.
- **A chapter already detected this session isn't detected twice** — asking for "all chapters" when everything is done queues nothing and says so.
- Detection is **one chapter at a time**, on a single worker. Each pass loads MAGI onto the GPU, so two at once is not twice as fast.
- A chapter detected in the background is **written to disk as soon as its pass finishes** (with auto-save on), so a closed tab, an early Finish or another power cut costs nothing that was already computed.

With auto-save **off**, nothing reaches disk until you press Save. Marks still live in the session — leave a chapter and come back and they're there — and the action bar keeps a running count of unsaved chapters. Closing the session asks whether to write them, so "I decide when" never quietly turns into losing an afternoon.

**The session outline** — the sidebar has two tabs: **This page** (the panel list for the page you're on) and **All chapters**, a collapsible tree of the whole session:

```
SESSION OUTLINE                    3 chapter(s) · 54 page(s) · 214 panel(s)
› Chapter 1                                                        18/18 · 71
▾ Chapter 2                                                        17/18 · 68
  │ ▾ 04  002_004.jpg                                                      4
  │     Panel 1   Panel 2   Panel 3   Panel 4
  │ › 05  002_005.jpg                                                      3
  │ › 06  002_006.jpg                                                      0
› Chapter 3                                                        19/19 · 75
```

Every chapter, page and panel in the session, in one place. Click a chapter or a page to **go there**; click the **›** chevron to just expand it in place. Click a panel to jump to its page and select it. Each chapter shows `marked-pages/pages · panels`, and a page with nothing on it shows a dashed `0` — which is the fastest way to spot the page you skipped. Counts for the chapter you're on update live as you mark; the rest come from their `crops.json`.

Nothing below an open chapter is built until it's open — collapsed chapters are one row each, so a hundred-chapter session stays a small page rather than a DOM the browser has to fight.

### 2b. Check Every Chapter's Marks Without Touching Them

`view-marks` (Project-wide) opens the same one-tab session with every edit taken away:
```bash
./run.sh view-marks --project "my_manga"
```
Same outline, same navigation, same pages — no Draw/Adjust tools, no resize handles, no delete, no reorder, and a **Read-only** badge where the tools would be. A mark can still be selected (that's how the outline highlights one, and how you read its size); it just can't be moved.

Read-only is **enforced by the server**, not hidden in the browser: `POST /api/marks` and `POST /api/detect` answer `403`, no `crops.json` is written when a chapter is left or when the session ends, and MAGI never runs — detection fills in marks nobody saved, which is exactly what a verification pass must not invent. Opening it is meant to be the cheap way to be sure, so looking has to be provably free of consequences.


### 3. Crop Panels
```bash
./run.sh crop --project "my_manga" --chapter "1"
```
*Creates:* `chapters/chapter_<num>/panels/` (source) and this chapter's `panels` entry in the project's shared `manifest.json`. **That's all it creates** — cropping cuts panels and stops. Building the LLM upload formats is step 3b, its own command, so a 30MB zip never appears as a side effect of a command you ran to cut panels.

### 3b. Package the Upload Formats
```bash
./run.sh package --project "my_manga" --chapter "1" --formats sheets,panels_zip
```
*Creates* — all under the project-level generated tree, not the chapter's source folder — whichever formats you chose: `sheets/chapter_<num>/`, `panels_zip/chapter_<num>/panels_1.zip`, `panels_pdf/chapter_<num>/panels_1.pdf` (or its zipped/split variants), `sheets_zip/chapter_<num>/sheets_1.zip`, `sheets_folders/chapter_<num>/` (see [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) below).

Whatever you pass is **remembered for that project** (in its `project.json`), so the next chapter builds the same set without being asked. Leave `--formats` off to use that remembered choice, falling back to `config.json`'s `cropper.package` switches for a project that has never chosen. `--formats none` builds nothing. In the wizard this is a checklist rather than a flag, opened on what the project currently builds. Re-run it any time — after changing the size cap, or when you want a different format from an already-cropped chapter — it works straight from `panels/`, no re-crop.

### 3c. Start `narration.json` Yourself (optional)
Not using the LLM copy/paste flow for this chapter? `narration-init` creates the file for you, two ways:
```bash
./run.sh narration-init --project "my_manga" --chapter "1" --mode template
./run.sh narration-init --project "my_manga" --chapter "1" --mode blank
```
- **`template`** (default) — the complete skeleton for this chapter: one entry per cropped panel, in panel order, each with empty `text`. Byte-for-byte the same structure the Narration Writer creates when it opens, so you can fill it in by hand in an editor, or hand it to an LLM as the exact structure to fill in without it having to invent the panel list. Needs the chapter cropped (that's where the panel ids come from).
- **`blank`** — a genuinely empty file. Zero bytes: not `{}`, not `[]`, nothing. That's the placeholder state the rest of remanga reads as "not written yet", so it reserves the path without any stage mistaking it for real content.

It won't overwrite a narration.json that already has content unless you pass `--force` (the wizard asks). A blank file isn't content, so going blank → template needs no flag.

**Every chapter at once** — `narration-init-all` (Project-wide in the wizard) gives every chapter in the project the blank, zero-byte file, so a manga you're going to narrate yourself is set up in one command rather than one per chapter:
```bash
./run.sh narration-init-all --project "my_manga"
./run.sh narration-init-all --project "my_manga" --chapters 12,13,14
```
Chapters that already hold a *written* narration are named and left alone; replacing them is one explicit answer covering all of them (`--force`, or the confirmation it asks a real terminal), never a prompt per chapter. Chapters that already have the blank file are simply not touched — so re-running it says what's there rather than reporting work it didn't do.

### 3d. Make the Narration Safe to Speak
```bash
./run.sh normalize-narration --project "my_manga" --chapter "1" --dry-run
./run.sh normalize-narration --project "my_manga" --chapter "1"
```
LLM output and hand-written text carry things a TTS engine turns into noise. This rewrites the narration text so every engine says what you meant:

| Removed (makes artifacts) | Kept (carries delivery) |
| --- | --- |
| Emoji, arrows, box drawing — anything outside a speakable whitelist | **`?` and `!`** — the engine's own phrasing cues, and the emotion classifier's when it's on |
| Leftover markdown (`**bold**` gets voiced as "asterisk asterisk") | **`...`** — a pause the engine actually performs |
| URLs, email addresses, and citations like `(see https://…)` | Commas, periods, apostrophes, quotes — the phrasing |
| SHOUTED words — many front-ends spell all-caps out letter by letter | Single capitals (`A rank`, `S-class`) — those really are letters |
| Streeeetched letters (capped at three) | Intra-word hyphens |
| Raw digits — `3,000` becomes `three thousand`, `2nd` becomes `second`, `50%` becomes `fifty percent` | |
| Zero-width and control characters, smart quotes, em dashes | |

Runs of `!!!` collapse to one (same meaning to a model, less risk of over-reading), and a mixed `?!` survives intact — that pairing is its own tone.

It also fixes what reads *flat* rather than what glitches:

- **`'speech'` → `"speech"`** — a single quote is also the apostrophe, so a tokenizer can't tell `sneers, 'a worthless skill'` from `Dragon King's Flame`. Double quotes for speech leave `'` meaning exactly one thing.
- **Quoted speech gets a capital** — `pleads, 'please stop!'` reads to the model as the middle of a clause and gets that flat continuation prosody; `pleads, "Please stop!"` starts a fresh utterance, which is what it is.
- **`Mr.` → `Mister`**, and **`A rank` → `A-rank`** — both are otherwise read as letters or as the article "a".

It also reports what it deliberately **doesn't** touch — problems whose only honest fix is a rewrite: empty lines, lines over the 26-word ceiling, narration repeated on two panels, and the one that never announces itself in any single line — most sentences opening the same way:

```
Worth a look - not changed, because only a rewrite fixes these:
  • 59 of 129 lines (46%) open with an '-ing' phrase
      001_001_01: Collapsing to the ground outside the shop, a terrified black...
      001_003_03: Flashing a ruthless smirk, Lloyd coldly states, "I will not ...
    Each line reads fine on its own, but one sentence shape repeated for a whole
    chapter sounds like a drone however well it's synthesized.
```

It always shows every line it would change, with which rules fired, and asks before writing — narration text isn't regenerable from anything on disk. `--dry-run` previews and exits; `--force` skips the confirmation. Running it twice changes nothing the second time.

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

### 5. Synthesize Vocal Audio
```bash
./run.sh tts --project "my_manga" --chapter "1"
./run.sh tts --project "my_manga" --chapter "1" --voice am_fenrir
```
Uses the configured engine and voice unless you say otherwise:
- **`--voice`** — synthesize this run in a different Kokoro voice (a name, e.g. `am_fenrir`) without touching `config.json`. The wizard doesn't ask — it states which voice is configured and uses it, since that's not a per-chapter decision. Change it permanently in `setup-config` → **Narrator voice**.
- **`--force`** — re-synthesize every panel instead of resuming.

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

Re-running `download` for a chapter that's already there re-checks it rather than re-fetching it: every page must exist, be non-empty, and match what MangaDex reports for that chapter *right now* — same chapter id, same page count, same image quality. That record lives in the project's `manifest.json` and is rewritten on every download attempt, marked `verified` only once every page is actually on disk, so a run killed mid-download resumes instead of reporting a complete chapter. If the chapter has changed since it was last fetched here (re-uploaded under a new id, or you switched `image_quality`), the old pages are cleared and every page is re-fetched — they were images of something else.

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
Add `-f`/`--force` to skip the confirmation prompt, or `--no-reverify` to skip re-checking the downloaded pages afterward. `remark` still opens the Panel Marker and waits for you to save even with `--force` — that flag only skips the deletion confirmation, not the marking step itself. In the wizard, `restart` presents the same four levels as a menu, each row spelling out what survives it. `wipe`'s keep-list is a checklist of what the chapter actually has, and — like `package`'s formats — the set you choose is remembered for the project, so the next chapter's wipe opens with it already ticked.

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

`--rebuild` (the wizard asks it as *"How much to rebuild"*) decides how much is thrown away first. One ordered choice rather than a set of yes/no flags to combine, because the three options are strictly increasing in destructiveness and combining them was how people ended up re-synthesizing a project by accident:

| `--rebuild` | Deletes | Keeps | Cost |
|---|---|---|---|
| `missing` *(default)* | nothing | everything already built | fastest — picks up where the last run stopped |
| `outputs` | `audio_modified/`, `video/` | **`audio/` — the synthesized narration** | minutes, no re-narration |
| `everything` | `audio/`, `audio_modified/`, `video/` — every generated file | `chapters/` and the project's json files | slow — re-runs TTS on every panel |
| `sources` | all of the above **plus each chapter's `panels/`** | only what remanga can't rebuild: `pages/` (re-verified), `crops.json`, `narration.json`, project json | slowest — re-crops, re-narrates the audio, re-renders, re-joins |

`outputs` is the one to reach for while tuning how a recap sounds or looks: music, levels, resolution, framing. It rebuilds from narration you already have.

`sources` is the deepest: it keeps only the three things remanga cannot produce for itself — the downloaded `pages/`, the hand-placed `crops.json`, and the LLM-written `narration.json` — and rebuilds everything else, panels included. Pages are kept and **re-verified** rather than re-downloaded: anything that doesn't belong is removed, and only missing images are re-fetched.

`everything` is for when the narration itself is wrong — a voice change, a different engine, or an edited `narration.json`. Before any chapter is touched, every generated folder in the whole project is deleted, and only these survive:
```
projects/<manga>/
├── chapters/       # pages/, crops.json, narration.json — downloaded or hand-authored
├── project.json    # manga source + this project's remembered choices
├── memory.json     # the LLM's story continuity
└── manifest.json   # production bookkeeping + the cached MangaDex chapter list
```
Then every chapter is rebuilt from that: pages re-verified (anything missing re-fetched), panels re-cropped, voice re-synthesized, re-mixed, re-rendered, re-joined. Everything about to be deleted is listed first, with its size, so "this is about to take an hour" is visible before it does.

Wiping the **whole project** up front, rather than each chapter as the compile reaches it, is the point. A per-chapter wipe can only delete folders named after a chapter in the run, so it always leaves the join's own `video/_work/` (a master WAV that can run to hundreds of MB, plus a concat list pointing at frames that are about to be deleted), the previous joined MP4, the artifacts of any chapter you excluded with `--chapters`, and any folder from an output format you've since turned off. Those are exactly the stale files you ran a regenerate to be rid of — so note that this **does** clear chapters outside `--chapters` too; it means the whole project, not the selection.

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
- `./run.sh setup-config` → **Vision outputs**, **or**
- the wizard's **Pipeline** editor, which offers the same checklist right after saving a pipeline that includes `crop` (defaults to No, so it never interrupts uninvited) — without needing to know `setup-config` exists separately.

How each package format stays lossless:
- **panels_zip / sheets_zip:** every image re-encoded as an optimized PNG and as a lossless WEBP, keeping whichever comes out smaller. Manga line art/halftones typically shrink 30-50% this way.
- **pdf / pdf_splite / pdf_zip / pdf_zip_splite:** every image is embedded as a `FlateDecode`-compressed raw bitmap (PDF's own native lossless image representation — the same class of compression a PNG uses internally, just packaged the way PDF expects), optionally TIFF-Predictor-2-filtered first for a better ratio. Pillow's own PDF writer re-encodes RGB images as lossy JPEG with no way to turn that off short of quantizing colors, which is why this is built directly rather than through Pillow's `Image.save(..., "PDF")`.
- Either way, a candidate re-encoding only ever gets used after decoding it back and verifying it's pixel-for-pixel identical to the original — anything that doesn't round-trip exactly is discarded in favor of a safer encoding (or the original file, for the zip formats).

Each part carries the same project/manga/chapter identity, plus which part it is, how many parts total, and that part's image range — as a `chapter_info.json` file for a panels_zip/sheets_zip/pdf_zip part, or as page 1 of a raw PDF part (rendered as plain, readable text, since a plain PDF can't hold a separate loose file the way a zip can) - true even with splitting off and a single part, so an LLM given only one part never has to guess whether more exist. See the "Chapter Identity" section of [`prompts/narration.md`](prompts/narration.md) for how the LLM is expected to read it.

---

## Panel Marker Web UI

Panel cropping is done by hand in a local browser tool instead of an LLM round-trip — `./run.sh mark -p <PROJECT> -c <CHAPTER>` (or step 5 of the interactive wizard) opens it automatically:

- **[MAGI v3](https://github.com/ragavsachdeva/magi)** (a manga-understanding vision model, GPU required) finds panel boxes when you press **Detect** (this page, this chapter, a range or all chapters), running in the background while you keep working. It never runs unless you ask.
- **Draw tool (`D`):** left-click and drag on a page to mark a panel (drag can start outside the page edge, Canva-style, and can start on top of an existing mark to draw an overlapping one without disturbing it — see click-to-select below).
- **Select tool (`V`):** click a mark to select it, then drag its body to move it or a corner/edge handle to resize it. Dashed guide lines appear when an edge lines up with another panel's — a visual aid, not a hard snap.
- **Delete:** right-click a mark.
- **Reorder:** drag a panel's `⠿` grip in the right-hand panel list — that order becomes narration order (with auto-order off; see [Mark Panels](#2-mark-panels)).
- **Action bar** (top of the right sidebar): **Detect**, **Reorder** and **Recrop** for this page, this chapter, a range or all chapters, plus the saved Options switches — see [Mark Panels](#2-mark-panels).
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
4. **Pacing Ceiling:** 10 to 20 words per panel (hard ceiling: 26 words) to ensure optimal retention and natural Kokoro speech pacing.

### YouTube Upload Text (`prompts/youtube.md`)

Nothing in the pipeline reads or writes this — it's a prompt you use by hand when a chapter is rendered. Upload the chapter's `narration.json` and `memory.json` with `prompts/youtube.md`, and it replies with four plain-text blocks to copy straight into YouTube: `=== TITLE ===`, `=== DESCRIPTION ===`, `=== THUMBNAIL TEXT ===` and `=== THUMBNAIL PROMPT ===`.

It's written for reuse rather than for a fresh write-up every chapter: the description is meant to be pasted unchanged from one upload to the next, with the chapter number alone on the opening line so the next chapter is a one-character edit, and the title and thumbnail text carry the number so two uploads never look like the same video. It also holds the line on YouTube's limits (title ≤ 100 characters, aim ≤ 70; the first ~150 characters of the description are all that show above "…more"; exactly 3 hashtags) and on the same zero-spoiler horizon as the narration — a title and thumbnail are read *before* the video, so the chapter's ending appears in neither.

*A fuller version of this — per-chapter `youtube.json` files, a series-wide format lock, and a `youtube` pipeline step that runs the hand-off for you — lives on the [`youtube-publishing-automation`](https://github.com/tawhidUnhappy/remanga/tree/youtube-publishing-automation) branch, for when this stops being a copy/paste job.*

---

## The TTS Engine

remanga drives **Kokoro-82M** (`tts.engine: "kokoro"`), an 82M-parameter StyleTTS 2 / iSTFTNet model with fixed built-in voices, in its own isolated `.tools/venv-kokoro` environment.

It replaced IndexTTS-2.5 and Audio8 TTS, both of which cloned a narrator from a reference clip. If you need what those did, they're preserved on the **`legacy/indextts-audio8`** branch.

**Why the change**, measured on an RTX 3060 (12GB):

| | IndexTTS-2.5 | **Kokoro-82M** |
|---|---|---|
| real-time factor | 1.42 — *slower* than real time | **0.021 — 48x faster than real time** |
| per panel | 7.7s | **0.12s** |
| a 450-panel recap | **58 minutes** of synthesis | **under 1 minute** |
| weights | 3.3GB | 327MB |
| voice | you supply a reference clip | 54 built-in voices |
| licence (weights) | — | Apache-2.0 |

The reference clip was also the single largest source of quality problems: IndexTTS truncates it to its first 15 seconds and derives the narrator's entire delivery from that, so a badly-chosen clip — or one cut mid-word — poisoned every panel of every chapter. Kokoro removes that whole category of failure.

### Choosing the voice

`tts.kokoro.voice` is a **name**, not a path — there is no clip to point at, and no transcript. Pick one from the wizard's **Narrator voice** row (`./run.sh setup-config`), or set it directly:

```json
"tts": {
  "engine": "kokoro",
  "lang": "EN",
  "speed": 1.0,
  "synth_timeout_seconds": 180,
  "kokoro": {
    "hf_repo_id": "hexgrad/Kokoro-82M",
    "model_dir": "checkpoints/kokoro_82m",
    "voice": "af_heart",
    "volume_boost_db": 0.0,
    "sample_rate": 24000
  }
}
```

Kokoro publishes a quality grade per voice, and **the spread is wide — A down to F** — so the picker shows the grade on every row and lists them best-first. The ones worth knowing:

| voice | grade | notes |
|---|---|---|
| **`af_heart`** (default) | **A** | the only grade-A voice it ships |
| `af_bella` | A- | |
| `af_nicole`, `bf_emma` | B- | |
| **`am_fenrir`**, `am_michael`, `am_puck` | C+ | **the best male voices** |
| `bm_fable`, `bm_george` | C | British male |

If you want a male narrator, `am_fenrir` is the pick — but note it's three grades below the default, which is a real quality trade rather than a coin flip. That's exactly why `af_heart` is the default and nothing picks a male voice for you silently.

`lang_code` (American vs British phonemes) is **derived from the voice name**, never configured. Kokoro takes it separately, and a mismatch makes a voice speak through the wrong accent's phonemes instead of raising an error — so remanga doesn't offer you the chance to get it wrong.

`tts --voice <name>` overrides for a single run without touching `config.json`.

### Volume boost

`tts.kokoro.volume_boost_db` is a gain applied to the narration clips, in decibels (`0.0` = untouched, positive = louder). The gain is baked into each panel's WAV as it's written, so the clips on disk really are louder. **What you hear in the finished video depends on `audio.enable_loudnorm`:**

| Your settings | What a boost does |
|---|---|
| loudnorm **on** + BGM on (the default) | Raises the **voice against the music** — the master is normalized to a fixed loudness either way, so boosting narration pushes the BGM further underneath it. This is the useful case. |
| loudnorm **on** + BGM off | **Nothing.** With nothing else in the mix, boosting and then normalizing lands exactly where it started. The pipeline warns you when it sees this combination. |
| loudnorm **off** | Raises the master's absolute level by the full amount. |

**Changing it does not re-synthesize.** `audio_timing.json` records the gain baked into the clips it describes, so going from `+3` to `+6` applies only the `+3` difference to the cached clips — no TTS re-run — and going back down applies a negative one. Because that file's mtime is what `mix` and `render` watch, turning the knob propagates all the way to the finished video on the next run with no extra flag. Values are clamped to ±30 dB, and any panel pushed into clipping is named in the output (pydub saturates rather than wrapping, so it distorts rather than exploding).

**Upgrading is automatic.** A `config.json` written for IndexTTS-2.5 or Audio8 — with `tts.indextts` / `tts.audio8` blocks, or the older flat fields — loads without error: the retired blocks are dropped and `tts.engine` is forced onto a name that still exists. Nothing is carried across, deliberately: a `spk_audio_prompt` path is not a Kokoro voice name, and silently reinterpreting one as the other would narrate a whole chapter in the wrong voice. Per-project `settings` overrides written against the old paths are dropped the same way. **You will need to pick a voice after upgrading** (or accept the `af_heart` default).

---

## Narration Voice & Delivery

A recap narrator should sound like one person telling the story evenly from start to finish — not like someone reacting to it. Kokoro reads every panel in the configured voice's own register, and there is no per-panel emotion system to tune.

1. **The voice is the delivery.** With no cloning and no emotion vector, what you choose in `tts.kokoro.voice` is what every panel sounds like, first to last. If narration sounds wrong, the voice is the thing to change — there is no reference clip to blame any more, which was the point.
2. **Punctuate anyway.** `prompts/narration.md` (Rule 3) has the LLM write real punctuation — `!`, `?`, `...` — wherever the panel genuinely is exclamatory, interrogative, or hesitant. Kokoro reads punctuation for phrasing and pacing. There's no emotion field in `narration.json` — each entry is just `panel_id` + `text`.
3. **Speed** (`tts.speed`) is applied by the model itself as a generation parameter, not by an ffmpeg pass afterwards, so it doesn't cost quality.

## Reliability: Crashes, Interrupts & Resuming

TTS synthesis is the longest-running, most interruption-prone stage of the pipeline (one Kokoro call per panel; far quicker than it used to be, but a full recap still runs unattended), so it's built to be safely stopped and resumed at any point:

- **Ctrl+C is safe.** It's caught gracefully, the Kokoro worker is asked to shut down cleanly (a few seconds), and a second Ctrl+C during that wait force-kills it instead of leaving it orphaned holding GPU memory.
- **Panel exports are atomic.** Each panel's WAV is written to a temp file and only renamed into place once fully written, so a kill mid-export can never leave a truncated clip that looks finished.
- **Resuming is conservative, not just fast.** `remanga tts` re-synthesizes the panel that was interrupted *and the two immediately before it*, instead of trusting whatever's already on disk near the resume point — cheap insurance against a truncated clip from an older run slipping through.
- **A wedged worker gets replaced automatically.** If Kokoro stops responding for longer than `tts.synth_timeout_seconds` (default 180s), the worker is killed and the next attempt spawns a fresh one, instead of the whole run hanging indefinitely with the model still loaded and the GPU sitting idle.

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
./run.sh tts      -p <PROJECT> -c <CHAPTER> [-e <ENGINE>] [-v <VOICE_WAV>] [-f]
./run.sh mix      -p <PROJECT> -c <CHAPTER> [-b <BGM_FILE>]
./run.sh render   -p <PROJECT> -c <CHAPTER> [-f]
./run.sh download-all -p <PROJECT> [-u <URL_OR_ID>] [-f] [--refetch]
./run.sh mark-all -p <PROJECT> [-c <CHAPTER1,CHAPTER2,...>]
./run.sh view-marks -p <PROJECT> [-c <CHAPTER1,CHAPTER2,...>]
./run.sh narration-init-all -p <PROJECT> [-c <CHAPTER1,CHAPTER2,...>] [-f]
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
│   ├── venv-kokoro/            # Isolated env - PyTorch + Kokoro + misaki/spaCy G2P
│   └── venv-magi/              # Isolated env - PyTorch + MAGI v3's own pins
├── checkpoints/
│   ├── kokoro_82m/             # Kokoro-82M weights + all 54 voice packs
│   └── magiv3/                 # MAGI v3 panel-detection weights (Panel Marker assist)
├── prompts/
│   ├── narration.md         # Master objective scriptwriter prompt
│   ├── narration_review.md  # Fix-pass prompt for a human review round
│   └── youtube.md           # Title/description/thumbnail for the upload, in plain text
├── projects/
│   └── <project_name>/
│       ├── project.json        # Saved MangaDex URL, chapter index, and everything this manga has chosen (its settings, pipeline steps, upload formats, wipe keep-list)
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
├── remanga/                    # Python core pipeline package - one directory per concern,
│   │                           # each file small enough to read top to bottom
│   ├── tui/                    # Interactive terminal: arrow-key menus, checklists, confirmations
│   │                           # keys.py (raw tty + mouse/paste immunity), select.py, checklist.py,
│   │                           # confirm.py, text.py, frame.py (how a menu looks), fallback.py (non-tty)
│   ├── commands/               # Every subcommand, shared by the CLI and the wizard:
│   │   │                       # spec.py (Command/Param + argparse glue), registry.py (the list),
│   │   │                       # selection.py (chapter/keep-list parsing)
│   │   └── handlers/            # setup.py, chapter.py, project.py, cleanup.py - the handlers themselves
│   ├── wizard/                 # The interactive session: app.py (menus), projects.py, chapters.py,
│   │                           # params.py (prompts a command's parameters), pipeline_edit.py,
│   │                           # narration.py + review.py + uploads.py + handoff.py (LLM hand-offs)
│   ├── settings/               # Everything that reads/writes config.json: assets.py (voice/BGM/transcript),
│   │                           # vision.py (packaging checklist), presets.py, engine.py, video.py,
│   │                           # sections.py (every setting as one list), wizard.py, paths_ui.py
│   ├── audio/                  # tts.py + mix.py; synth/ = one module per engine over a shared worker base
│   │   └── scripts/             # kokoro_worker.py - runs inside its own venv
│   ├── cropper/                # crop.py (coordinate cropper), sheets.py, gutter/ (edge snapping), ...
│   ├── downloader/             # mangadex.py (MangaDex client) & resolve.py (id/title/language lookup)
│   ├── models/                 # weights.py (talks to the isolated venvs to fetch/verify weights)
│   │   └── scripts/             # download_kokoro.py, download_deepseek_ocr.py
│   ├── webui/                  # Panel Marker: server.py (entry point/lifecycle), routes.py (Flask app/API),
│   │   │                       # marker_state.py (session state), detection.py + magi_assist.py (MAGI v3),
│   │   │                       # settings_store.py (Shortcuts + assist persistence)
│   │   ├── static/js/           # Frontend: render/drag-resize/draw/zoom-pan/shortcuts/magi/page-nav modules
│   │   └── scripts/             # magi_worker.py, download_magi.py - run inside .tools/venv-magi
│   ├── video/                  # compose.py (frame compositor) & render.py (GPU/CPU renderer)
│   ├── full_recap/             # discovery.py, timeline.py (one continuous audio timeline), compiler.py
│   ├── verify/                 # models.py, panels.py, probe.py, runner.py, report.py
│   ├── reset/                  # modes.py (restart presets), entries.py (what exists), actions.py (deletes)
│   ├── status/                 # compute.py (what's on disk) & panel.py (the printed report)
│   ├── config/                 # Pydantic configuration schemas, one file per subsystem
│   ├── paths/                  # Project/chapter directory layout & metadata persistence
│   ├── venvs.py                 # Locates the .tools/venv-* isolated environments
│   ├── console.py               # The one shared Rich Console every module prints through
│   ├── json_io.py               # Shared JSON read/write helpers
│   ├── ffmpeg_io.py             # Shared ffmpeg subprocess helper
│   ├── pipeline.py              # The step registry and each project's saved step list
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
- Kokoro-82M needs only ~2-3GB VRAM, and runs faster than real time on CPU alone.

### 2. A specific narration line sounds unstable, or too dramatic
Every panel is read in the same voice and the same register (see [Narration Voice & Delivery](#narration-voice--delivery)), so an odd-sounding line almost always traces back to what's written for that panel rather than to synthesis:
- Check whether that panel's `narration.json` text over-punctuates — a line stacking multiple `!`/`?`/`...` reads as more dramatic than intended. `prompts/narration.md` Rule 3 asks the LLM to reserve emphatic punctuation for panels that genuinely call for it; if it slipped through anyway, trim the line's punctuation back to plain prose and re-run.
- Run `./run.sh normalize-narration` — leftover markdown, emoji, raw digits and SHOUTED words all turn into artifacts, and it rewrites them into something speakable.
- If the *whole* recap sounds wrong rather than one line, that's the voice, not the text: try a different `tts.kokoro.voice` (grades are shown in the picker; several of the 54 are graded D or F and are genuinely worse).

### 3. NVENC GPU encoder error during video rendering
`bootstrap.sh` pins the bundled `bin/ffmpeg` to a specific, tested BtbN build (not the "latest" rolling one) precisely so NVENC works out of the box for a wide range of NVIDIA driver versions — a too-new build otherwise requires a driver version yours may not have yet, and it reports as a generic-looking failure. If GPU encoding still doesn't work:
- Rendering prints the actual encoder error instead of a silent fallback, e.g. `Driver does not support the required nvenc API version` — that tells you whether it's a real driver-too-old problem or something else.
- If it is a driver mismatch, `remanga` automatically tries a system-installed `ffmpeg` next (if one exists) before giving up on GPU entirely — nothing is installed for you, it only checks what's already on your machine.
- If your GPU genuinely doesn't support NVENC, or no working ffmpeg/driver combination is found anywhere, it falls back to CPU encoding (`libx264`) automatically.
- You can manually force CPU encoding by setting `"prefer_gpu": false` in `config.json`.

### 3b. Why is my CPU busier than my GPU while rendering?
Because `nvidia-smi`'s headline **GPU-Util is not measuring the encoder.** That number reports SM (CUDA core) occupancy; NVENC is separate fixed-function silicon it doesn't count. Measured mid-render on an RTX 3060:

```
utilization.gpu 8 %   utilization.encoder 100 %   ffmpeg ~295% CPU (3 of 12 cores)
```

The encoder is pegged — the GPU is doing exactly the job it was given. Ask for the right counter:
```bash
nvidia-smi --query-gpu=utilization.gpu,utilization.encoder --format=csv
```

Ubuntu's own **Resources** app (`resources`, the default system monitor since it replaced GNOME System Monitor) reads the same NVML counters and shows them separately: its GPU tab has a **Video Encoder** / **Video Decoder** figure alongside the main GPU utilization graph — that's the one that moves during a render, while the headline graph stays near idle. To see it per-process, turn on the **Video Encoder** column in Settings → Processes (or Apps), and ffmpeg's row will show it. Either way, don't read the general "GPU" percentage as "is my GPU being used" for an encode.

The CPU work is real, but it's everything that *isn't* H.264 encoding: decoding the panel PNGs, converting RGB→YUV, duplicating each panel's frame out to the configured fps (a 12-minute recap at 30fps is ~21,000 frames), encoding the AAC audio, and muxing the MP4. None of that has a GPU path worth taking here, and at ~7x realtime it isn't the bottleneck either. The frame-compositing phase *before* the encode is 100% CPU by design (Pillow), as is the audio assembly (pydub).

### 4. How do I get contact sheets instead of individual panels?
Contact sheets (`sheets`) are on by default; `panels_zip` is off. To get individual panels instead of, or in addition to, sheets:
- Run `./run.sh setup-config` and answer the checklist in **Option 2 (Vision Outputs)** — check `panels_zip`, uncheck `sheets`/`sheets_zip` if you don't want both.
- Or set `"package": {"sheets": false, "panels_zip": true}` directly under `"cropper"` in `config.json`.

### 4b. What are the `panels_zip/`/`panels_pdf/`/`sheets_zip/` folders, and how do I configure them?
They're the [Vision Outputs](#vision-outputs-what-to-generate-what-to-zip) package formats — controllable as a checklist of exactly what you want built, e.g. "only the PDF" is a real, fully-supported answer. **`sheets` is on by default**; every zip/PDF format (`sheets_zip`, `pdf`, `pdf_splite`, `pdf_zip`, `pdf_zip_splite`, `panels_zip`, `panels_zip_splites`) is off. None replace `panels/`, and building any of them doesn't cost quality anywhere. Easiest way to change any of them: `./run.sh setup-config` → **Vision outputs**, **or** the wizard's Pipeline editor, which offers the same screen whenever `crop` is part of the pipeline — one checklist, Space to toggle each format, plus the size cap when a split format is on, no manual editing needed. Or edit `config.json` directly — every setting lives under one `"package"` object in the `"cropper"` section:
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
The worker now kills and replaces itself automatically after `tts.synth_timeout_seconds` (default 180s) of no response, so this should self-resolve on its own. If you're on an older run without that fix, or want to recover immediately: check `nvidia-smi` — a genuinely stuck worker shows near-idle GPU clocks/power draw despite holding VRAM. Kill the `kokoro_worker.py` process (and the `remanga` process above it, or just Ctrl+C twice) and re-run the same command; see [Reliability](#reliability-crashes-interrupts--resuming) for why that's always safe to do.

### 7. A mark keeps snapping back to a different position while I'm dragging it
This was a real bug (fixed): a background MAGI detection poll could overwrite a page's marks mid-drag if that page's very first edit hadn't finished yet. Make sure you're on a current `remanga` checkout — it no longer happens. It's unrelated to the alignment guide lines, which are purely visual and never move a mark on their own.

---

## License

Distributed under the **MIT License**. See `LICENSE` for details.