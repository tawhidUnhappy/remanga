# remanga

**remanga** is an ultra-lightweight, modular, LLM-guided manga recap video production pipeline. Driven by standalone environment isolation, it streamlines manga downloading, AI-assisted panel coordinate cropping, edge-faded text-to-speech voice generation, audio normalization, and GPU-accelerated video rendering with solid black canvas composition.

---

## Key Features

- **Zero Global Dependency Footprint:** Automatically installs its own isolated Python environment and static `ffmpeg` binaries.
- **MangaDex Downloader:** Direct chapter image fetching by manga title, UUID, or URL with rate-limiting backoff and URL reuse across chapters.
- **Interactive Terminal Workflow:** Seamless terminal navigation with GNU Readline arrow keys, auto-suggestions, and chapter tracking.
- **LLM-Guided Precision Cropping:** Bypasses heavy local CV models by using compact, normalized `[0-1000]` coordinate JSON files generated directly by LLMs.
- **Vocal Synthesis & Dynamic Mixing:** High-fidelity TTS generation via `edge-tts` with `en-US-GuyNeural`, per-panel micro edge-fading, optional background music looping with ducking, and EBU R128 loudness normalization.
- **Lightweight Black Canvas Compositor:** Clean, centered, aspect-ratio-preserving panel composition on a solid `#000000` background.
- **GPU Acceleration:** Automatic hardware encoding detection (`h264_nvenc`) with automatic CPU (`libx264`) fallback.
- **Subtitle Generation:** Automatic time-aligned SRT subtitle creation from narration timing metadata.

---

## Installation & Setup

1. **Bootstrap Isolated Environment:**
   ```bash
   bash bootstrap.sh
   ```
   This provisions the Python virtual environment and generates `config.json`.

---

## Standard Workflow

### Option A: Interactive Guided Mode (Recommended)
Run the master interactive script:
```bash
./pipeline.sh
```
Follow the terminal instructions. The script allows you to choose or create projects, automatically reuses saved Manga URLs, downloads pages, indicates the exact path to place your `crops.json`, crops the panels, prompts for `narration.json`, synthesizes speech using `en-US-GuyNeural`, mixes audio, and renders the final MP4 recap video.

---

### Option B: Step-by-Step CLI Mode

#### 1. Download Chapter
```bash
./run.sh download --project "solo_leveling" --url "https://mangadex.org/title/..." --chapter "1"
```
*(On subsequent chapters for the same project, `--url` is optional as it is automatically loaded from project metadata).*

#### 2. Generate and Place `crops.json`
Feed the page images along with `prompts/crop_generation_prompt.md` into your LLM. Save the resulting JSON to:
```text
projects/solo_leveling/chapters/chapter_1/crops.json
```

#### 3. Crop Panels
```bash
./run.sh crop --project "solo_leveling" --chapter "1"
```

#### 4. Generate and Place `narration.json`
Feed the panels and previous memory along with `prompts/narration_generation_prompt.md` into your LLM. Save the resulting JSON to:
```text
projects/solo_leveling/chapters/chapter_1/narration.json
```

#### 5. Generate Voice & Mix Master Audio
```bash
./run.sh tts --project "solo_leveling" --chapter "1"
./run.sh mix --project "solo_leveling" --chapter "1"
```

#### 6. Render Final Video
```bash
./run.sh render --project "solo_leveling" --chapter "1"
```
The output MP4 is saved to: `projects/solo_leveling/chapters/chapter_1/solo_leveling_ch1_recap.mp4`

#### Check Workspace Status at Any Time
```bash
./run.sh status --project "solo_leveling" --chapter "1"
```

---

## License
MIT License.
