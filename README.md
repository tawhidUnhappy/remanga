# remanga

**remanga** is an ultra-lightweight, modular, LLM-guided manga recap video production pipeline. Driven by standalone environment isolation, it streamlines manga downloading, AI-assisted panel coordinate cropping, zero-shot neural voice cloning with **IndexTTS-2.5**, clickless audio edge-fading, dynamic audio mastering, and GPU-accelerated video rendering with clean black canvas composition.

---

## Key Features

- **Zero Global Dependency Footprint:** Automatically provisions its own isolated Python environment and static `ffmpeg` binaries.
- **MangaDex Downloader:** Direct chapter image fetching by manga title, UUID, or URL with rate-limiting backoff and URL reuse across chapters.
- **IndexTTS-2.5 Vocal Synthesis:** State-of-the-art zero-shot voice cloning from any reference speaker audio (`narrator_default.wav`), 8-dimensional neural emotion conditioning, and 2.28× real-time factor acceleration.
- **Lightweight Contact Sheets (`sheets.zip`):** Automatically compiles sequential panels into 2x2 labeled contact sheets packaged into `sheets.zip` to minimize LLM token usage during vision prompt analysis.
- **Temporal Horizon Prompting:** LLM prompt framework strictly preventing premature character name reveals or forward plot spoilers before they visually and textually occur in the chapter.
- **Dynamic Audio Mastering:** Per-panel micro edge-fading to eliminate digital clicks, optional background music looping with ducking, and broadcast EBU R128 loudness normalization.
- **Lightweight Black Canvas Compositor:** Clean, centered, aspect-ratio-preserving panel composition on a solid `#000000` background.
- **GPU Acceleration:** Automatic hardware encoding detection (`h264_nvenc`) with automatic CPU (`libx264`) fallback.
- **Subtitle Generation:** Automatic time-aligned SRT subtitle creation from narration timing metadata.

---

## Installation & Setup

1. **Bootstrap Environment:**
   ```bash
   bash bootstrap.sh
   ```
2. **Download IndexTTS-2.5 Checkpoints:**
   Place the IndexTTS-2.5 model weights into `checkpoints/indextts_2.5/` and your reference narrator voice audio at `assets/voices/narrator_default.wav`.

---

## Standard Workflow

### Option A: Interactive Guided Mode (Recommended)
Run the master interactive script:
```bash
./pipeline.sh
```
Follow the terminal instructions. The script guides you through downloading pages, generating `crops.json`, cropping panels, packaging `sheets.zip`, generating `narration.json`, synthesizing IndexTTS-2.5 speech, mixing audio, and rendering the final recap MP4.

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