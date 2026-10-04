"""Kokoro-82M - talks to `.tools/venv-kokoro`/kokoro_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.models import ModelManager
from remanga.plugins import get
from remanga.workers import spawn_script_worker

SPEC = get("tts", "kokoro")
SCRIPTS = Path(__file__).parent / "scripts"


def model_manager(config) -> ModelManager:
    """Kokoro's weights - what the synthesizer loads and setup.py fetches."""
    return ModelManager(
        config.model_dir, config.hf_repo_id,
        tool_name="kokoro", download_script=SCRIPTS / "download_kokoro.py",
        expected_files=("kokoro-v1_0.pth",), display_name=SPEC.display_name,
    )


# Kokoro's measured words per minute at each speed, relative to speed 1.0.
_PACE_BY_SPEED = ((1.0, 1.0), (1.3, 225 / 185), (1.33, 237 / 185), (1.36, 266 / 185))


def _pace(speed: float) -> float:
    """How much faster than speed 1.0 Kokoro reads at `speed`: in proportion
    below 1.0, along the measured points above it, and no faster than the
    last of them past that. Guessing too fast is the harmful direction - it
    makes ordinary takes look like collapses - so it is never extrapolated."""
    if speed <= 1.0:
        return max(speed, 0.1)
    for (s0, p0), (s1, p1) in zip(_PACE_BY_SPEED, _PACE_BY_SPEED[1:]):
        if speed <= s1:
            return p0 + (p1 - p0) * (speed - s0) / (s1 - s0)
    return _PACE_BY_SPEED[-1][1]

class KokoroSynthesizer(BaseWorkerSynthesizer):
    """Kokoro-82M - talks to `.tools/venv-kokoro`/kokoro_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.kokoro
        super().__init__(audio_config, model_manager(self.engine_config))

    @property
    def chars_per_second(self) -> float:
        """Kokoro reads slower than Qwen. Measured at speed 1.0 on af_heart as
        joined batches of a real chapter: 782 characters came back 48.5s, 833
        50.8s, 1,045 62.5s, 999 63s and 341 21s - 15.9 to 16.7. Held to Qwen's
        22.5 every take ran about 1.45x its estimate, right on the collapse
        line, and a 164-character panel read in an ordinary 11s failed the
        chapter as a collapse.

        Speed is not linear past 1.0, so it follows what was measured rather
        than multiplying: 185 wpm at 1.0, 225 at 1.3, 237 at 1.33, 266 at 1.36."""
        return 16.0 * _pace(float(self.engine_config.speed))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        # lang_code is derived from the voice rather than configured: Kokoro
        # takes the accent separately from the voice name, and a mismatch
        # makes a voice speak through the wrong accent's phonemes instead of
        # raising anything. See KokoroConfig.lang_code.
        return spawn_script_worker(
            "kokoro", "plugins/kokoro", "kokoro_worker.py",
            "--model_dir", str(model_dir.resolve()),
            "--lang_code", self.engine_config.lang_code,
            "--repo_id", self.engine_config.hf_repo_id,
            "--sample_rate", str(self.engine_config.sample_rate),
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        """One panel's request. Speed is a generation parameter here, so the
        audio comes back already at that rate - no pass afterwards."""
        return {
            "cmd": "synthesize",
            "voice": voice or self.engine_config.voice,
            "text": text,
            "output_path": str(output_wav.resolve()),
            "speed": self.engine_config.speed,
        }
