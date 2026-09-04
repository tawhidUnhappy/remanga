"""IndexTTS-2.5 - talks to `.tools/venv-indextts`/indextts_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import engine_spec
from remanga.models import ModelManager
from remanga.venvs import get_scripts_dir, get_tool_python

# This engine's identity as config.json and every menu know it - taken from
# the spec rather than repeated here, so the name shown while a chapter
# synthesizes is provably the name that selected this class.
SPEC = engine_spec("indextts-2.5")


class IndexTTSSynthesizer(BaseWorkerSynthesizer):
    """IndexTTS-2.5 - talks to `.tools/venv-indextts`/indextts_worker.py."""

    tool_name = "indextts"
    display_name = SPEC.display_name
    spec = SPEC

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        super().__init__(audio_config, ModelManager(
            tts_config.model_dir, tts_config.hf_repo_id,
            tool_name="indextts", download_script="download_indextts.py",
            expected_files=("gpt.pth", "s2mel.pth"), display_name=SPEC.display_name,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("indextts")
        script = get_scripts_dir("audio") / "indextts_worker.py"

        cmd: List[str] = [
            str(python), "-u", str(script),
            "--cfg_path", str(Path(self.tts_config.cfg_path).resolve()),
            "--model_dir", str(model_dir.resolve()),
        ]
        if self.tts_config.use_bf16:
            cmd.append("--use_bf16")

        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> Dict[str, Any]:
        """Deliberately sends no emo_vector: IndexTTS-2.5 infers its own
        emotion/prosody straight from `text`'s own wording and punctuation
        ("!"/"?"/"..." etc - see prompts/narration.md Rule 3) when none is
        supplied, which is what makes narration sound naturally expressive
        instead of a forced-flat reading of whatever the text actually
        says. Temperature/top_p (TTSConfig) are left at IndexTTS-2.5's own
        recommended defaults for natural prosody within that inferred
        emotion."""
        request: Dict[str, Any] = {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "text": text,
            "lang": (self.tts_config.lang or "EN").strip().upper(),
            "output_path": str(output_wav.resolve()),
            "temperature": self.tts_config.temperature,
            "top_p": self.tts_config.top_p,
        }
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            request["duration_factor"] = round(1.0 / self.tts_config.speed, 3)
        return request

    def _post_synthesize(self, output_wav: Path, request: Dict[str, Any]) -> None:
        # duration_factor already handles speed on the model side when supported;
        # only fall back to the ffmpeg post-process if the worker couldn't use it
        # (older IndexTTS checkouts without a duration_factor parameter).
        if "duration_factor" not in request and abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)


