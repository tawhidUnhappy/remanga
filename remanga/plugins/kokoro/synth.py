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


class KokoroSynthesizer(BaseWorkerSynthesizer):
    """Kokoro-82M - talks to `.tools/venv-kokoro`/kokoro_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.kokoro
        super().__init__(audio_config, model_manager(self.engine_config))

    # No take limit: Kokoro has no generation budget to run out of and no
    # reference to drift from - it splits whatever it is given into ~510-
    # phoneme pieces itself and reads each with the same fixed voice, leaving
    # a natural ~0.85s pause between them (measured: 0.33s lead + ~0.5s tail).
    # So a whole chapter can be ONE take, and there is no join between takes
    # anywhere in it - the joins were what made a line start straight after
    # the last with no breath (user report, 2026-10-04).
    max_take_seconds = float("inf")

    # Kokoro reads slower than Qwen. Measured on af_heart, at its own pace, as
    # joined batches of a real chapter: 782 characters came back 48.5s, 833
    # 50.8s, 1,045 62.5s, 999 63s and 341 21s - 15.9 to 16.7. Held to Qwen's
    # 22.5 every take ran about 1.45x its estimate, right on the collapse
    # line, and a 164-character panel read in an ordinary 11s failed the
    # chapter as a collapse.
    chars_per_second = 16.0

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
        """One panel's request: the text in the voice, read raw - at the
        voice's own pace, nothing done to the audio afterwards. The
        configured voice comes with its mix, if one is set; a voice named for
        one call (the voice sampler) is that voice alone."""
        request = {
            "cmd": "synthesize",
            "voice": voice or self.engine_config.voice,
            "text": text,
            "output_path": str(output_wav.resolve()),
        }
        mix = None if voice else self.engine_config.mix
        if mix:
            request.update(mix_voice=mix.name, mix_percent=self.engine_config.mix_percent)
        return request
