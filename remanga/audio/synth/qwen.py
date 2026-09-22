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

# How much of a reference recording the clone is built from. Qwen conditions
# on the start of the clip anyway, and a long one makes every generation
# slower - a 31-second reference pushed one chunk past the three-minute
# timeout, where 15 seconds of the same recording reads it comfortably, and
# 30 seconds blew a 670s timeout on a take the 15s clip finished in 325s.
#
# A ceiling, not the cut: where the clip actually ends is decided with its
# transcript, at the last sentence that finishes inside this (see
# audio/reference_text.py). Cutting on the stopwatch instead is what put
# words in a chapter that nobody wrote.
REFERENCE_MAX_SECONDS = 15.0

# The line a designed voice says in its sample. Long enough for the clone to
# have something to work with, and dull on purpose - it is never in a video.
DESIGN_SAMPLE_TEXT = (
    "Evening falls over the quiet capital, and the traveller stops at the well to drink, "
    "thinking that he has walked further today than he meant to."
)


def reference_pair_path(sample: Path) -> Path:
    """Where the clip-and-transcript pair built from a recording is kept -
    beside the recording, named after it. One file describing both halves, so
    a transcript can never be read next to a clip it is not of."""
    return sample.with_name(f"{sample.stem}.reference.json")


def _fallback_clip(path: Path) -> Path:
    """The clone's reference when no pair was built (nothing could read the
    recording): the first REFERENCE_MAX_SECONDS of it, cut on the stopwatch.

    Safe only because a clip with no transcript is used through
    x_vector_only_mode - the speaker embedding alone - where the model is
    given no words at all and so has none to leak. The moment there IS a
    transcript, the pair decides the cut instead (audio/reference_text.py)."""
    from pydub import AudioSegment

    audio = AudioSegment.from_file(path)
    limit_ms = int(REFERENCE_MAX_SECONDS * 1000)
    if len(audio) <= limit_ms:
        return path.resolve()
    trimmed = path.with_name(f"{path.stem}.reference.wav")
    if not trimmed.exists() or trimmed.stat().st_mtime < path.stat().st_mtime:
        audio[:limit_ms].export(trimmed, format="wav")
    return trimmed.resolve()


def reference_pair(config: QwenConfig) -> tuple[Path, str]:
    """The clip the clone is built from and what it says - the pair
    audio/reference_text.py built, or the embedding-only fallback.

    The text is worth having rather than "": with it, the clone uses the
    recording IN CONTEXT instead of the speaker embedding alone. Measured on a
    take that collapses either way, in-context read 863 words where
    embedding-only managed 98, and 40% of the script was findable in it
    against 2%. It is only worth having while it is TRUE of the clip beside
    it, which is the whole job of reference_text.py."""
    sample = Path(config.designed_sample)
    if config.designed_text.strip():
        # remanga wrote this sample and chose its words - exact by construction.
        return sample.resolve(), config.designed_text.strip()
    try:
        saved = json.loads(reference_pair_path(sample).read_text(encoding="utf-8"))
        clip = sample.with_name(saved["clip"])
        text = str(saved["text"]).strip()
        if clip.exists() and text:
            return clip.resolve(), text
    except (OSError, ValueError, KeyError):
        pass
    return _fallback_clip(sample), ""


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
    # costs proportionally - and a cloned voice carries the reference in its
    # context too, which makes it slower again. 260 characters is two or three
    # sentences, which lands well inside the synthesis timeout on a 3060.
    chunk_max_chars = 260

    def __init__(self, tts_config: TTSConfig, audio_config: AudioConfig):
        self.tts_config = tts_config
        self.engine_config: QwenConfig = tts_config.qwen
        self.mode = "clone" if self.engine_config.designed else "custom"
        super().__init__(audio_config, _model_manager(self.engine_config, self.mode))

    def _spawn_worker(self, model_dir: Path) -> subprocess.Popen:
        config = self.engine_config
        args = ["--model_dir", str(model_dir.resolve()), "--mode", self.mode, "--language", config.language]
        if self.mode == "clone":
            # The clip and what it is KNOWN to say, from one place so they
            # cannot disagree (reference_pair). Words the clip does not
            # actually contain are worse than no words at all: the model is
            # shown a sentence it never hears finished, and finishes it out
            # loud in the narration - which is exactly what happened to a
            # chapter before reference_text.py cut the two together. No
            # transcript means the embedding alone, which can leak nothing.
            clip, text = reference_pair(config)
            args += ["--ref_audio", str(clip), "--ref_text", text]
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
    The caller records `text` as the sample's transcript (QwenConfig.
    designed_text): knowing what the reference says lets the clone use it in
    context, which sounds closer than the speaker embedding alone.

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
