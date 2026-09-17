"""Chatterbox Turbo - talks to `.tools/venv-chatterbox`/chatterbox_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import DISPLAY_NAME
from remanga.models import ModelManager
from remanga.workers import spawn_script_worker

# What proves the download finished: the three checkpoints from_local() loads,
# plus the two tokenizer files big enough for ModelManager's size check to
# mean anything. download_chatterbox.py checks the small ones itself.
EXPECTED_FILES = (
    "t3_turbo_v1.safetensors", "s3gen_meanflow.safetensors", "ve.safetensors",
    "vocab.json", "merges.txt",
)


class ChatterboxSynthesizer(BaseWorkerSynthesizer):
    """Chatterbox Turbo - talks to `.tools/venv-chatterbox`/chatterbox_worker.py."""

    tool_name = "chatterbox"
    display_name = DISPLAY_NAME

    # Turbo samples at most 1000 speech tokens per call - 40 seconds of audio
    # at its 25 tokens a second - and simply stops there: no error, the clip
    # just ends mid-sentence. 300 characters is roughly 20 seconds of
    # narration, which leaves room for a slow voice.
    chunk_max_chars = 300

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        super().__init__(audio_config, ModelManager(
            tts_config.model_dir, tts_config.hf_repo_id,
            tool_name="chatterbox", download_script="download_chatterbox.py",
            expected_files=EXPECTED_FILES, display_name=DISPLAY_NAME,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker("chatterbox", "audio", "chatterbox_worker.py",
                                   "--model_dir", str(model_dir.resolve()))

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, voice: str, output_wav: Path) -> dict[str, Any]:
        """One page's request. `voice` is the PATH of the recording to clone."""
        return {
            "cmd": "synthesize",
            "reference_audio": str(Path(voice).resolve()),
            "text": text,
            "output_path": str(output_wav.resolve()),
        }
