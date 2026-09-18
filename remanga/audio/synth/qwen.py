"""Qwen3-TTS - talks to `.tools/venv-qwen-tts`/qwen_tts_worker.py.

Two ways to narrate, and the worker is started for whichever is configured
(config/tts.py:QwenConfig):

- a **preset narrator**: the CustomVoice model, a speaker name and an optional
  instruction about delivery;
- a **designed voice**: the sample the description produced is cloned by the
  Base model for every panel. The clone prompt is built once per run, so every
  panel of a chapter is the same voice - re-describing the voice per panel is
  what makes a designed voice drift.

Designing itself (description -> one sample) is `design_voice` below: a single
run of the VoiceDesign model, asked for by the settings screen, not something
a chapter ever does."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from remanga.audio.synth.base import BaseWorkerSynthesizer
from remanga.config import AudioConfig, TTSConfig
from remanga.config.tts import QwenConfig
from remanga.config.tts_engines import engine_spec
from remanga.console import console, escape as _esc
from remanga.models import ModelManager
from remanga.paths import get_scripts_dir
from remanga.tool_envs import ensure_tool
from remanga.workers import spawn_script_worker

SPEC = engine_spec("qwen")

# The three variants, each fetched only when the way that needs it is used.
# Named here rather than in config.json: they are what the code calls, not a
# choice anyone makes.
VARIANTS = {
    "custom": ("Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice", "custom_voice"),
    "design": ("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign", "voice_design"),
    "clone": ("Qwen/Qwen3-TTS-12Hz-1.7B-Base", "base"),
}
# What proves a download finished: the weights and the tokenizer the model
# loads. The download script checks the small files itself.
EXPECTED_FILES = ("model.safetensors", "config.json")

# The line a designed voice says in its sample. Long enough for the clone to
# have something to work with, and dull on purpose - it is never in a video.
DESIGN_SAMPLE_TEXT = (
    "Evening falls over the quiet capital, and the traveller stops at the well to drink, "
    "thinking that he has walked further today than he meant to."
)


def _model_manager(config: QwenConfig, variant: str) -> ModelManager:
    repo_id, folder = VARIANTS[variant]
    return ModelManager(
        str(Path(config.model_root) / folder), repo_id,
        tool_name=SPEC.tool_name, download_script="download_qwen_tts.py",
        expected_files=EXPECTED_FILES, display_name=f"{SPEC.display_name} ({variant})",
    )


class QwenSynthesizer(BaseWorkerSynthesizer):
    """Qwen3-TTS - talks to `.tools/venv-qwen-tts`/qwen_tts_worker.py."""

    tool_name = SPEC.tool_name
    display_name = SPEC.display_name

    # Qwen3-TTS generates speech tokens autoregressively, so a very long line
    # costs proportionally; this keeps one call to a few sentences, the same
    # reason every worker engine has a ceiling.
    chunk_max_chars = 400

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config: QwenConfig = tts_config.qwen
        self.mode = "clone" if self.engine_config.designed else "custom"
        super().__init__(audio_config, _model_manager(self.engine_config, self.mode))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        config = self.engine_config
        args = ["--model_dir", str(model_dir.resolve()), "--mode", self.mode, "--language", config.language]
        if self.mode == "clone":
            args += ["--ref_audio", str(Path(config.designed_sample).resolve()),
                     "--ref_text", config.designed_text or DESIGN_SAMPLE_TEXT]
        return spawn_script_worker(self.tool_name, "audio", "qwen_tts_worker.py", *args)

    def _synth_timeout_seconds(self) -> float:
        return self.tts_config.synth_timeout_seconds

    def _build_request(self, text: str, output_wav: Path, voice: str | None = None) -> dict[str, Any]:
        """One panel's request: the text, and - for a preset - who says it."""
        request: dict[str, Any] = {
            "cmd": "synthesize",
            "text": text,
            "output_path": str(output_wav.resolve()),
        }
        if self.mode == "custom":
            request["speaker"] = voice or self.engine_config.speaker
            request["instruct"] = self.engine_config.instruct
        return request


def design_voice(config: QwenConfig, description: str, out_wav: Path, text: str = DESIGN_SAMPLE_TEXT) -> Path:
    """One sample of the voice `description` asks for, written to `out_wav`.

    A single run of the VoiceDesign model rather than a long-lived worker:
    designing happens once, in the settings screen, and holding a second
    multi-gigabyte model open for the rest of the session to do it would cost
    more than the run itself."""
    model_dir = _model_manager(config, "design").ensure_model()
    python = ensure_tool(SPEC.tool_name)
    script = get_scripts_dir("audio") / "qwen_tts_worker.py"
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    console.print(f"[cyan]Designing a voice from your description with {SPEC.display_name}...[/]")
    request = json.dumps({"cmd": "synthesize", "text": text, "output_path": str(out_wav.resolve()),
                          "instruct": description})
    result = subprocess.run(
        [str(python), "-u", str(script), "--model_dir", str(Path(model_dir).resolve()), "--mode", "design",
         "--language", config.language],
        input=request + "\n", capture_output=True, text=True, check=False,
    )
    ok = out_wav.exists() and out_wav.stat().st_size > 1000
    if not ok:
        tail = (result.stderr or result.stdout or "").strip().splitlines()[-3:]
        raise RuntimeError(f"Designing the voice failed: {_esc(' '.join(tail)) or 'no audio came back'}")
    return out_wav
