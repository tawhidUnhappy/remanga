"""IndexTTS-2.5 - talks to `.tools/venv-indextts`/indextts_worker.py."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

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
        # This engine's own block - its model, its sampling knobs and its own
        # reference voice, separate from audio8's (see config/tts.py). Read
        # through `engine_config` rather than off tts_config directly so the
        # two synthesizers are shaped the same way, and so nothing here can
        # accidentally pick up the other engine's answer.
        self.engine_config = tts_config.indextts
        super().__init__(audio_config, ModelManager(
            self.engine_config.model_dir, self.engine_config.hf_repo_id,
            tool_name="indextts", download_script="download_indextts.py",
            expected_files=("gpt.pth", "s2mel.pth"), display_name=SPEC.display_name,
        ))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        python = get_tool_python("indextts")
        script = get_scripts_dir("audio") / "indextts_worker.py"

        cmd: list[str] = [
            str(python), "-u", str(script),
            "--cfg_path", str(Path(self.engine_config.cfg_path).resolve()),
            "--model_dir", str(model_dir.resolve()),
        ]
        if self.engine_config.use_bf16:
            cmd.append("--use_bf16")
        # Loading the emotion classifier is a start-up decision, not a
        # per-request one (it costs ~1.2GB of VRAM held for the whole run),
        # so it is a spawn flag; _build_request's use_emo_text below is only
        # meaningful when the worker was started with this.
        if self.engine_config.use_text_emotion:
            cmd.append("--use_qwen_emo")

        return subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, bufsize=1,
        )

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, spk_prompt_path: str, output_wav: Path) -> dict[str, Any]:
        """Builds one panel's synthesis request.

        Emotion is the interesting part. By default nothing emotion-related
        is sent, and IndexTTS-2.5 then reads every panel with the emotional
        contour of spk_audio_prompt (infer_generator sets `emo_audio_prompt =
        spk_audio_prompt` and pins `emo_alpha = 1.0`) - one even register for
        the whole chapter, which is what a recap narrator should sound like
        as long as the reference clip is a calm, steady read.

        Note that this is NOT the "infers emotion from the wording and
        punctuation" behaviour it is often described as, here and upstream;
        the text has no say in it at all. When tts.indextts.use_text_emotion
        is on, `use_emo_text` makes the worker classify each panel's text and
        blend that emotion in instead, scaled by `emo_alpha`
        (text_emotion_strength) so it colours the read rather than steering
        it. Expressive, but for continuous narration usually too much - see
        IndexTTSConfig for the measurements.

        Never an explicit emo_vector either way: that would force one fixed
        emotion onto every panel, which is neither of the two useful
        behaviours. Temperature/top_p stay at IndexTTS-2.5's own recommended
        defaults - they control how natural a single reading sounds within
        whichever emotion is in play."""
        request: dict[str, Any] = {
            "cmd": "synthesize",
            "spk_audio_prompt": spk_prompt_path,
            "text": text,
            "lang": (self.tts_config.lang or "EN").strip().upper(),
            "output_path": str(output_wav.resolve()),
            "temperature": self.engine_config.temperature,
            "top_p": self.engine_config.top_p,
        }
        if self.engine_config.use_text_emotion:
            request["use_emo_text"] = True
            request["emo_alpha"] = self.engine_config.text_emotion_strength
        if abs(self.tts_config.speed - 1.0) >= 0.02:
            request["duration_factor"] = round(1.0 / self.tts_config.speed, 3)
        return request

    def _post_synthesize(self, output_wav: Path, request: dict[str, Any]) -> None:
        # duration_factor already handles speed on the model side when supported;
        # only fall back to the ffmpeg post-process if the worker couldn't use it
        # (older IndexTTS checkouts without a duration_factor parameter).
        if "duration_factor" not in request and abs(self.tts_config.speed - 1.0) >= 0.02:
            self._adjust_audio_speed(output_wav, self.tts_config.speed)


