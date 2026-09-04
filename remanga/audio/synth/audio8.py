"""Audio8/Audio8-TTS-Preview-0.1b - talks to `.tools/venv-audio8`/
audio8_worker.py. See config.Audio8Config for its settings and
audio8_worker.py's module docstring for the model itself."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import engine_spec
from remanga.models import ModelManager
from remanga.settings import read_reference_text
from remanga.venvs import get_scripts_dir, get_tool_python

# This engine's identity as config.json and every menu know it - taken from
# the spec rather than repeated here, so the name shown while a chapter
# synthesizes is provably the name that selected this class.
SPEC = engine_spec("audio8-tts-0.1b")


class Audio8Synthesizer(BaseWorkerSynthesizer):
    """Audio8/Audio8-TTS-Preview-0.1b - talks to `.tools/venv-audio8`/
    audio8_worker.py. See config.Audio8Config for its settings and
    audio8_worker.py's module docstring for the model itself."""

    tool_name = "audio8"
    display_name = SPEC.display_name
    spec = SPEC

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config = tts_config.audio8
        super().__init__(audio_config, ModelManager(
            self.engine_config.model_dir, self.engine_config.hf_repo_id,
            tool_name="audio8", download_script="download_audio8.py",
            expected_files=("model.safetensors", "codec.pth"), display_name=SPEC.display_name,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("audio8")
        script = get_scripts_dir("audio") / "audio8_worker.py"

        cmd: List[str] = [
            str(python), "-u", str(script),
            "--model_dir", str(model_dir.resolve()),
        ]
        if self.engine_config.use_bf16:
            cmd.append("--use_bf16")

        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> Dict[str, Any]:
        # Read fresh each call rather than caching at __init__ - the file is
        # small, this runs once per panel not per token, and it means an
        # edit to the transcript file takes effect on the very next panel
        # without restarting the pipeline.
        return {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "reference_text": read_reference_text(self.engine_config.reference_text_path),
            "text": text,
            "output_path": str(output_wav.resolve()),
            "temperature": self.engine_config.temperature,
            "top_p": self.engine_config.top_p,
            "max_new_tokens": self.engine_config.max_new_tokens,
        }

    def _post_synthesize(self, output_wav: Path, request: Dict[str, Any]) -> None:
        # No model-side speed control for this engine - fall back to the
        # shared ffmpeg-atempo path whenever tts.speed isn't 1.0.
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)


