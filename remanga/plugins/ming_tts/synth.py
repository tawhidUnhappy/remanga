"""Ming-3.0-tts - talks to `.tools/venv-ming-tts`/ming_tts_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.models import ModelManager
from remanga.plugins import get
from remanga.plugins.ming_tts.setup import ensure_source
from remanga.workers import spawn_script_worker

SPEC = get("tts", "ming")
SCRIPTS = Path(__file__).parent / "scripts"


def model_manager(config) -> ModelManager:
    """Ming's weights - what the synthesizer loads and setup.py fetches."""
    return ModelManager(
        config.model_dir, config.hf_repo_id,
        tool_name="ming-tts", download_script=SCRIPTS / "download_ming_tts.py",
        expected_files=("model.safetensors", "campplus.onnx", "tokenizer.json"),
        display_name=SPEC.display_name,
    )


class MingSynthesizer(BaseWorkerSynthesizer):
    """Ming-3.0-tts - talks to `.tools/venv-ming-tts`/ming_tts_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.ming
        super().__init__(audio_config, model_manager(self.engine_config))

    # No take limit, as for Kokoro: upstream's synthesize() splits whatever it
    # is given into short fragments itself and reads each in the same built-in
    # voice, so a whole chapter is one take with no joins between takes.
    max_take_seconds = float("inf")

    # Measured in US_Stella: a whole chapter of 14,890 characters came back
    # 798.6s (18.65), five panels of it 718 in 38.2s (18.8). It made that
    # chapter in 1045s on the 3060 - 0.07s a character, inside the base
    # class's 0.125 timeout allowance.
    chars_per_second = 18.7

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        return spawn_script_worker(
            "ming-tts", "plugins/ming_tts", "ming_tts_worker.py",
            "--model_dir", str(model_dir.resolve()),
            "--src_dir", str(ensure_source()),
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        return {
            "cmd": "synthesize",
            "voice": voice or self.engine_config.spec.name,
            "text": text,
            "output_path": str(output_wav.resolve()),
        }
