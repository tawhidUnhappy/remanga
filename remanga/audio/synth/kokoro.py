"""Kokoro-82M - talks to `.tools/venv-kokoro`/kokoro_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import DISPLAY_NAME
from remanga.models import ModelManager
from remanga.workers import spawn_script_worker


class KokoroSynthesizer(BaseWorkerSynthesizer):
    """Kokoro-82M - talks to `.tools/venv-kokoro`/kokoro_worker.py."""

    tool_name = "kokoro"
    display_name = DISPLAY_NAME

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config
        super().__init__(audio_config, ModelManager(
            self.engine_config.model_dir, self.engine_config.hf_repo_id,
            tool_name="kokoro", download_script="download_kokoro.py",
            expected_files=("kokoro-v1_0.pth",), display_name=DISPLAY_NAME,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        # lang_code is derived from the voice rather than configured: Kokoro
        # takes the accent separately from the voice name, and a mismatch
        # makes a voice speak through the wrong accent's phonemes instead of
        # raising anything. See TTSConfig.lang_code.
        return spawn_script_worker(
            "kokoro", "audio", "kokoro_worker.py",
            "--model_dir", str(model_dir.resolve()),
            "--lang_code", self.engine_config.lang_code,
            "--repo_id", self.engine_config.hf_repo_id,
            "--sample_rate", str(self.engine_config.sample_rate),
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, voice: str, output_wav: Path) -> dict[str, Any]:
        """One page's request.

        `voice` is a Kokoro voice NAME, not a path to a reference clip -
        this engine does not clone. Speed is applied by the model itself
        rather than by an ffmpeg pass afterwards, so there is no
        _post_synthesize step to undo: Kokoro takes it as a generation
        parameter and the audio comes back already at that rate."""
        return {
            "cmd": "synthesize",
            "voice": voice,
            "text": text,
            "output_path": str(output_wav.resolve()),
            "speed": self.tts_config.speed,
        }
