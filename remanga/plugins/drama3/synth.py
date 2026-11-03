"""Fish Audio Drama 3 - talks to `.tools/venv-drama3`/drama3_worker.py, which
runs speech.cpp's `speech worker`."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.console import console
from remanga.plugins import get
from remanga.plugins.drama3.config import voice_spec
from remanga.plugins.drama3.setup import ensure_speech
from remanga.proc_io import stream_subprocess
from remanga.workers import spawn_script_worker

SPEC = get("tts", "drama3")

# Where `speech pull drama-3` puts the Q4_K file under SPEECH_MODEL_DIR:
# <owner>--<repo>/<sha256>/<file>, by its content (speech.cpp's
# docs/models.md). Pinned to speech.cpp 0.8.11's catalog, so a load can find
# the file without speech.cpp hashing 20.8 GB to name it.
MODEL_SUBPATH = Path("sakasegawa--drama-3-GGUF",
                     "2a57b14c9b208a2ff833ab7305b920ca8f154ad807004a52d96a86a90a55523e",
                     "Drama-35B-A3B-v3-Q4_K.gguf")
MODEL_BYTES = 20_787_264_352


class SpeechModel:
    """The model file, fetched by speech.cpp's own `speech pull` (it checks
    the size and SHA-256 against its catalog, and resumes a stopped fetch).
    Stands in for a ModelManager: the worker base only asks it for
    ensure_model()."""

    def __init__(self, config):
        self.model_dir = Path(config.model_dir).resolve()
        self.model_name = config.model_name

    @property
    def path(self) -> Path:
        return self.model_dir / MODEL_SUBPATH

    def ensure_model(self) -> Path:
        if self.path.is_file() and self.path.stat().st_size == MODEL_BYTES:
            return self.path
        self.model_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[bold cyan]Downloading {SPEC.display_name} ({self.model_name}, 20.8 GB)...[/]")
        returncode, output = stream_subprocess(
            ["env", f"SPEECH_MODEL_DIR={self.model_dir}", str(ensure_speech()), "pull", self.model_name])
        if returncode != 0 or not self.path.is_file():
            raise RuntimeError(f"{SPEC.display_name} download failed: {output.strip()[-2000:]}")
        console.print(f"[bold green]✓ {SPEC.display_name} model ready![/]")
        return self.path


def model_manager(config) -> SpeechModel:
    """Drama 3's model file - what the synthesizer loads and setup.py fetches."""
    return SpeechModel(config)


class Drama3Synthesizer(BaseWorkerSynthesizer):
    """Fish Audio Drama 3 - talks to `.tools/venv-drama3`/drama3_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name
    starting_note = " (20.8 GB: experts the GPU can't hold run on the CPU)"

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.drama3
        super().__init__(audio_config, model_manager(self.engine_config))

    # Set by audio/retakes.py to read a take again another way. In the model's
    # own voice another seed may also shift the voice a little for that take;
    # from a voice file it changes only the delivery.
    seed = 0

    # Short takes - about a page (most are 400-600 characters; a short page
    # shares a take with the next). Drama 3 drops whole sentences from a long
    # take: on HimeSama ch1 in its own voice, the chapter as one take matched
    # 73% of the script, ~3-minute takes 33-100%. A page is short enough that
    # a take that still leaves words out is cheap to read again
    # (audio/retakes.py:retake_mismatches). Lower temperature is not the fix:
    # 0.7/0.7 ran to max_seconds, 30%.
    max_take_seconds = 45

    # Between two takes (about a page each): as long as one of the voice's
    # own longer pauses, not Kokoro's 420 ms - inside a take Drama 3 pauses
    # 350-1,200 ms after a sentence (scripts/drama3_worker.py:fit_pause), and
    # a page turn shorter than that sounded rushed beside them.
    take_gap_ms = 700

    # Measured on the 3060: the deep male voice read a whole chapter (HimeSama
    # ch1, 14,156 characters) at 10.3 characters a second - slower than on a
    # short line (12.6-14.1), and the other voices read short lines at
    # 15.5-17.2. The slowest is what sizes the takes, so a slow reading is
    # never taken for a runaway one (audio/takes.py:RUNAWAY_FACTOR).
    chars_per_second = 10.5

    # That chapter took ~0.66x real time (0.82 on a short line), ~0.15s of
    # wall clock a character - past the base class's 0.125, so twice it.
    def _timeout_for(self, text: str) -> float:
        return max(self._synth_timeout_seconds(), len(text) * 0.3)

    def _spawn_worker(self, model_path: Path) -> subprocess.Popen:
        return spawn_script_worker(
            "drama3", "plugins/drama3", "drama3_worker.py",
            "--speech", str(ensure_speech()),
            "--model", str(model_path),
            "--voices_dir", str(Path(self.engine_config.model_dir).resolve() / "voices"),
            "--threads", str(self.engine_config.threads),
            "--headroom_gb", str(self.engine_config.gpu_headroom_gb),
        )

    def _on_ready(self, event: dict) -> None:
        console.print(f"[bold green]✓ {self.display_name} worker ready on {event.get('device', '?')}.[/]")

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        spec = voice_spec(voice) if voice else self.engine_config.spec
        return {
            "cmd": "synthesize",
            "text": text,
            "voice": spec.name,
            "cue": spec.cue,
            "voice_file": self.engine_config.voice_file,
            "voice_seed": self.engine_config.seed,
            "seed": self.engine_config.seed + 1000 * self.seed,
            "output_path": str(output_wav.resolve()),
        }
