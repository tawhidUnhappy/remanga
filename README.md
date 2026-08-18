# remanga

**remanga** is a 100% self-contained, modular, LLM-guided manga recap video production pipeline. Built with strict environment isolation, it provisions its own tools, manages its own runtimes, and leaves zero files outside the root directory.

---

## Key Features

- **100% Isolated & Cleanly Removable:**
  - Contains its own standalone `uv` package manager in `bin/uv`.
  - Downloads and uses isolated static `ffmpeg` and `ffprobe` binaries in `bin/`.
  - Provisions a standalone Python 3.11 interpreter inside `.cache/`.
  - All Hugging Face and PyTorch caches are locked inside `.cache/`.
  - **Deleting the `remanga/` folder leaves ZERO leftover files or tool modifications on your system.**
- **High-Speed Model Fetching (`hf-transfer`):** Automatically downloads official `IndexTeam/IndexTTS-2.5` model weights from Hugging Face using multi-connection parallel streams.
- **Interactive Voice & BGM Prompting:** The terminal automatically validates your reference voice WAV and BGM path. If missing or invalid, it prompts you in the terminal with immediate file verification and saves it directly to `config.json`.
- **Zero-Shot Neural Vocal Synthesis (IndexTTS-2.5):** Clones any 3–10s reference speaker voice with 8-dimensional emotion vector conditioning.
- **Lightweight Contact Sheets (`sheets.zip`):** Packages cropped panels into 2x2 labeled contact sheets inside `sheets.zip` for maximum LLM vision token efficiency.
- **Temporal Horizon Prompting:** Master recap prompt enforcing strict zero-spoiler rules (forbids using character names, relationships, or future plot reveals before they visually and textually occur).
- **Audio Mastering & Normalization:** Per-panel micro edge-fading to eliminate digital clicks, optional background music looping with ducking, and broadcast EBU R128 loudness normalization.
- **GPU-Accelerated Compositor & Renderer:** 1080p black canvas compositor with automatic NVENC GPU hardware encoding (`h264_nvenc`) and CPU fallback (`libx264`).

---

## Installation & Setup

1. **Bootstrap Isolated Environment:**
   ```bash
   bash bootstrap.sh
   ```
   This provisions `uv`, downloads static `ffmpeg`, sets up Python 3.11, installs dependencies, turbo-downloads IndexTTS-2.5 from Hugging Face, and initializes `config.json`.

---

## Standard Workflow

### Option A: Interactive Guided Wizard (Recommended)
Run the master interactive script:
```bash
./pipeline.sh
```
The wizard guides you through:
1. Selecting or creating projects and chapters.
2. Interactively prompting and verifying your reference voice audio file and background music (if not already set in `config.json`).
3. Downloading pages from MangaDex.
4. Prompting for `crops.json`.
5. Cropping panels and compiling `sheets.zip`.
6. Prompting for `narration.json`.
7. Synthesizing voice audio via IndexTTS-2.5.
8. Mastering audio with loudness normalization.
9. Rendering the final 1080p recap video.

---

### Option B: Step-by-Step CLI Mode

#### 1. Download Chapter
```bash
./run.sh download --project "yandere_sister" --url "https://mangadex.org/title/..." --chapter "1"
```

#### 2. Generate and Place `crops.json`
Feed the page images along with `prompts/crop_generation_prompt.md` into your LLM. Save the resulting JSON to:
```text
projects/yandere_sister/chapters/chapter_1/crops.json
```

#### 3. Crop Panels & Build `sheets.zip`
```bash
./run.sh crop --project "yandere_sister" --chapter "1"
```
This crops all panels, compiles 2x2 vision contact sheets, and creates `sheets.zip`.

#### 4. Generate and Place `narration.json`
Feed `sheets.zip` along with `prompts/narration_generation_prompt.md` into your LLM. Save the resulting JSON to:
```text
projects/yandere_sister/chapters/chapter_1/narration.json
```

#### 5. Generate Voice & Mix Master Audio
```bash
./run.sh tts --project "yandere_sister" --chapter "1"
./run.sh mix --project "yandere_sister" --chapter "1"
```
*(Optional: override reference voice with `--voice path/to/voice.wav` or BGM with `--bgm path/to/bgm.mp3`)*

#### 6. Render Final Video
```bash
./run.sh render --project "yandere_sister" --chapter "1"
```
The recap MP4 is saved to: `projects/yandere_sister/chapters/chapter_1/yandere_sister_ch1_recap.mp4`

#### Check Workspace Status at Any Time
```bash
./run.sh status --project "yandere_sister" --chapter "1"
```

---

## License
MIT License.