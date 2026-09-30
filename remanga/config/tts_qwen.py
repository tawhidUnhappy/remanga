"""Qwen3-TTS's settings block: a preset speaker, a recording to clone, or a
voice designed from a description, and how it reads (instruct)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.config.base import ConfigModel

# Qwen3-TTS's own presets, as its model card names them, with what they sound
# like. `instruct` steers all of them; the list is what the voice menu shows.
QWEN_SPEAKERS: tuple[tuple[str, str], ...] = (
    ("Ryan", "male - warm, steady, an easy narrator"),
    ("Eric", "male - deeper, matter of fact"),
    ("Aiden", "male - younger, brighter"),
    ("Dylan", "male - relaxed, conversational"),
    ("Uncle_Fu", "male - older, gravelly"),
    ("Serena", "female - clear and even"),
    ("Vivian", "female - lively, expressive"),
    ("Ono_Anna", "female - soft, Japanese-accented English"),
    ("Sohee", "female - gentle, Korean-accented English"),
)


QWEN_SPEAKER_NAMES = tuple(name for name, _ in QWEN_SPEAKERS)


# What `design` says when the voice is a recording someone supplied rather
# than a description the model built a voice from - the two take different
# paths in audio/synth/qwen.py (a recording has no transcript).
RECORDING_PREFIX = "recording: "


class QwenConfig(ConfigModel):
    """Qwen3-TTS (Alibaba, Apache 2.0) in `.tools/venv-qwen-tts`, in one of two
    ways:

    - a **preset narrator** (`speaker`), optionally steered by `instruct`
      ("calm, unhurried"). One model, and identical on every call.
    - a **designed voice**: `design` describes the narrator in words, the
      Settings screen generates one sample from that description, and every
      panel is then spoken from THAT sample. The sample is what keeps the
      voice identical across a chapter - describing the voice again for every
      panel is what makes a designed voice drift."""

    # Which preset narrates when no voice has been designed.
    speaker: str = "Ryan"
    # How to deliver the lines, in words. PRESETS ONLY: upstream's
    # generate_voice_clone takes no `instruct` at all, so a cloned or designed
    # voice cannot be steered this way - it carries whatever delivery its
    # recording or its description already had. The settings screen hides this
    # row for those voices rather than letting it be set and ignored.
    # Deliberately blunt. Asked for "a calm narrator telling a story" the model
    # ACTS, leaning into every line like someone auditioning (user report), and
    # asking for "flat, like a documentary voice-over" measured no flatter
    # (3.98 vs 4.02 semitones of pitch spread on the same line). Asking for a
    # technical manual does: 3.09 st, and the 5-95% swing down from 10.2 to
    # 8.6 st. The panels carry the drama; the voice reads.
    instruct: str = ("monotone and unemotional, like reading a technical manual aloud: "
                     "no rise or fall, no stress on any word")
    # The description a voice was designed from, empty until one is designed.
    design: str = ""
    # The sample that design produced, and the line spoken in it. Narration
    # clones this file, so it is the voice itself, not a note about it.
    designed_sample: str = ""
    designed_text: str = ""
    language: str = "English"
    # One directory per model variant, fetched only when that way is used.
    model_root: str = "checkpoints/qwen3_tts"

    def voice_options(self) -> list[tuple[str, str]]:
        """Qwen3-TTS's preset narrators - see KokoroConfig.voice_options. A
        designed voice is not in here: there is only ever one, and it is
        already a sample on disk."""
        return [(name, hint) for name, hint in QWEN_SPEAKERS]

    @property
    def designed(self) -> bool:
        """Whether a designed voice is what narrates (it needs its sample)."""
        return bool(self.design and self.designed_sample and Path(self.designed_sample).is_file())

    @property
    def voice_label(self) -> str:
        if not self.designed:
            return self.speaker.replace("_", " ")
        if self.design.startswith(RECORDING_PREFIX):
            return f"clone of {Path(self.designed_sample).name}"
        return f"designed: {self.design[:40]}"

    @property
    def voice_detail(self) -> str:
        if self.designed:
            if self.design.startswith(RECORDING_PREFIX):
                return f"cloned from {self.designed_sample}"
            return f"designed voice - {self.design}"
        return f"{self.speaker.replace('_', ' ')} ({self.instruct})" if self.instruct else self.speaker

    def identity(self) -> dict[str, Any]:
        if self.designed:
            sample = Path(self.designed_sample)
            return {"engine": "qwen", "voice": f"designed:{self.design}", "sample": sample.name,
                    "sample_mtime_ns": sample.stat().st_mtime_ns}
        return {"engine": "qwen", "voice": self.speaker, "instruct": self.instruct}
