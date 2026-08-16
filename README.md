# remanga

**remanga** is an ultra-lightweight, modular, LLM-guided manga recap video production pipeline. Driven by standalone environment isolation (using `uv` and portable `ffmpeg`), it streamlines manga downloading, AI-assisted panel coordinate cropping, edge-faded text-to-speech voice generation, audio normalization, and GPU-accelerated video rendering with solid black canvas composition.

---

## Key Features

- **Zero Global Dependency Footprint:** Automatically installs its own isolated Python 3.12, `uv`, and static `ffmpeg` binaries within `.tools/` and `.venv/`.
- **MangaDex Downloader:** Direct chapter image fetching by manga title, UUID, or URL with rate-limiting and retry backoff.
- **LLM-Guided Precision Cropping:** Bypasses heavy local CV models by using compact, normalized `[0-1000]` coordinate JSON files generated directly by LLMs.
- **Vocal Synthesis & Dynamic Mixing:** High-fidelity TTS generation via `edge-tts` with per-panel micro edge-fading (eliminating clicks/pops), optional background music looping with ducking, and EBU R128 loudness normalization.
- **Lightweight Black Canvas Compositor:** Clean, centered, aspect-ratio-preserving panel composition on a solid `#000000` background.
- **GPU Acceleration:** Automatic hardware encoding detection (`h264_nvenc`) with automatic CPU (`libx264`) fallback.
- **Subtitle Generation:** Automatic time-aligned SRT subtitle creation from narration timing metadata.

---

## Directory Structure

```text
remanga/
├── .gitignore
├── pyproject.toml
├── bootstrap.sh
├── run.sh
├── pipeline.sh
├── config.json
├── config.example.json
├── prompts/
│   ├── crop_generation_prompt.md
│   └── narration_generation_prompt.md
└── remanga/
    ├── __init__.py
    ├── config.py
    ├── downloader/
    │   ├── __init__.py
    │   └── mangadex.py
    ├── cropper/
    │   ├── __init__.py
    │   └── json_cropper.py
    ├── audio/
    │   ├── __init__.py
    │   ├── tts_engine.py
    │   └── audio_processor.py
    ├── video/
    │   ├── __init__.py
    │   ├── compositor.py
    │   └── renderer.py
    └── cli.py
```

---

## Installation & Setup

1. **Bootstrap Isolated Environment:**
   ```bash
   bash bootstrap.sh
   ```
   This provisions an isolated Python 3.12 environment, downloads portable `uv` and static `ffmpeg`, and generates `config.json`.

---

## Standard Workflow

### Option A: Interactive Guided Mode (Recommended)
Run the master interactive script:
```bash
./pipeline.sh
```
Follow the terminal instructions. The script prompts you for manga details, downloads pages, indicates the exact path to place your `crops.json`, crops the panels, indicates where to place `narration.json`, synthesizes speech, mixes audio, and renders the final MP4 recap video.

---

### Option B: Step-by-Step CLI Mode

#### 1. Download Chapter
```bash
./run.sh download --project "solo_leveling" --url "https://mangadex.org/title/..." --chapter "1"
```
Pages are saved to: `projects/solo_leveling/chapters/chapter_1/pages/`

#### 2. Generate and Place `crops.json`
Feed the page images along with `prompts/crop_generation_prompt.md` into your LLM. Save the resulting JSON to:
```text
projects/solo_leveling/chapters/chapter_1/crops.json
```

#### 3. Crop Panels
```bash
./run.sh crop --project "solo_leveling" --chapter "1"
```
Cropped panels are saved to: `projects/solo_leveling/chapters/chapter_1/panels/`

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

## Configuration (`config.json`)

```json
{
  "system": {
    "prefer_gpu": true,
    "gpu_codec": "h264_nvenc",
    "fallback_codec": "libx264",
    "threads": 4
  },
  "tts": {
    "engine": "edge-tts",
    "voice": "en-US-ChristopherNeural",
    "rate": "+0%",
    "pitch": "+0Hz"
  },
  "audio": {
    "sample_rate": 44100,
    "edge_fade_ms": 35,
    "pause_between_panels_ms": 300,
    "bgm_enabled": false,
    "bgm_path": "assets/bgm/default_recap.mp3",
    "bgm_volume_db": -22.0,
    "enable_loudnorm": true
  },
  "video": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "background_color": "#000000",
    "panel_padding_percent": 3
  }
}
```

---

## License
MIT License.
