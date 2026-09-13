"""Chatterbox Turbo - talks to `.tools/venv-chatterbox`/chatterbox_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import engine_spec
from remanga.models import ModelManager
from remanga.venvs import get_scripts_dir, get_tool_python

# This engine's identity as config.json and every menu know it - see kokoro.py.
SPEC = engine_spec("chatterbox")

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
    display_name = SPEC.display_name
    spec = SPEC

    # Turbo samples at most 1000 speech tokens per call - 40 seconds of audio
    # at its 25 tokens a second - and simply stops there: no error, the clip
    # just ends mid-sentence. 300 characters is roughly 20 seconds of
    # narration, which leaves room for a slow voice.
    chunk_max_chars = 300

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.chatterbox
        super().__init__(audio_config, ModelManager(
            self.engine_config.model_dir, self.engine_config.hf_repo_id,
            tool_name="chatterbox", download_script="download_chatterbox.py",
            expected_files=EXPECTED_FILES, display_name=SPEC.display_name,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("chatterbox")
        script = get_scripts_dir("audio") / "chatterbox_worker.py"
        cmd: list[str] = [str(python), "-u", str(script), "--model_dir", str(model_dir.resolve())]
        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, voice: str, output_wav: Path) -> dict[str, Any]:
        """One panel's request.

        `voice` is the PATH of the reference clip being cloned - validated
        before the run started (settings/assets.py:ensure_valid_voice) and
        resolved here against remanga's working directory, which is what a
        relative path in config.json means everywhere else."""
        return {
            "cmd": "synthesize",
            "reference_audio": str(Path(voice).expanduser().resolve()),
            "text": text,
            "output_path": str(output_wav.resolve()),
            "speed": self.tts_config.speed,
        }

    def _post_synthesize(self, output_wav: Path, request: dict[str, Any]) -> None:
        """Turbo has no speaking-rate control, so tts.speed is applied to the
        finished clip with ffmpeg's pitch-preserving atempo instead - which
        does nothing at 1.0."""
        self._adjust_audio_speed(output_wav, float(request.get("speed", 1.0)))
