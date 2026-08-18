# remanga

**remanga** is an ultra-lightweight, modular, LLM-guided manga recap video production pipeline. Driven by standalone environment isolation powered by `uv`, it streamlines manga downloading, AI-assisted panel coordinate cropping, zero-shot neural voice cloning with **IndexTTS-2.5**, clickless audio edge-fading, dynamic audio mastering, and GPU-accelerated video rendering with clean black canvas composition.

---

## Key Features

- **Hermetic Environment with `uv`:** Automatically installs standalone Python 3.11 and pre-compiled wheels, completely avoiding host Python 3.14 compilation errors and header conflicts.
- **Automated IndexTTS-2.5 Model Fetching:** Automatically downloads official checkpoint weights from `IndexTeam/IndexTTS-2.5` on Hugging Face into `checkpoints/indextts_2.5/`.
- **Zero-Shot Speaker Cloning:** Supply any 3–10s clean reference voice WAV path in `config.json` (`spk_audio_prompt`) or via `--voice` in CLI.
- **8-Dimensional Neural Emotion Conditioning:** Dynamically maps 7 high-level recap emotion tags (`hype`, `tense`, `serious`, `shock`, `emotional`, `mysterious`, `neutral`) into IndexTTS emotion vectors.
- **Lightweight Contact Sheets (`sheets.zip`):** Automatically packages cropped panels into 2x2 labeled contact sheets inside `sheets.zip` for maximum LLM vision token efficiency.
- **Temporal Horizon Prompting:** Master recap prompt enforcing strict zero-spoiler rules (forbids using character names, relationships, or future plot reveals before they visually and textually occur).
- **Audio Mastering & Normalization:** Per-panel micro edge-fading to eliminate digital clicks, optional background music looping with ducking, and broadcast EBU R128 loudness normalization.
- **GPU-Accelerated Compositor & Renderer:** 1080p black canvas compositor with automatic NVENC GPU hardware encoding (`h264_nvenc`) and CPU fallback (`libx264`).

---

## Installation & Setup

1. **Bootstrap Environment:**
   ```bash
   bash bootstrap.sh
   ```
   This automatically provisions `uv`, creates a nested Python 3.11 virtual environment, installs dependencies, downloads IndexTTS-2.5 from Hugging Face, and initializes `config.json`.

2. **Set Your Reference Voice:**
   Open `config.json` and set `spk_audio_prompt` to your reference WAV audio file (e.g. `assets/voices/my_voice.wav`).

---

## Standard Workflow

### Option A: Interactive Guided Mode (Recommended)
Run the master interactive script:
```bash
./pipeline.sh
```
Follow the terminal instructions to download chapters, crop panels, review `sheets.zip`, generate `narration.json`, synthesize speech, and render the final recap video.

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
*(Optional: override your reference voice on the fly with `--voice path/to/voice.wav`)*

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