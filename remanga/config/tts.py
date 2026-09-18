"""Narration settings: which engine reads the panels, and each engine's own
voice - see remanga/audio/synth/ and config/tts_engines.py.

What every engine shares (which one is active, how long a synthesis may take)
sits at the top; everything that belongs to ONE engine lives in that engine's
block, which is what makes adding or removing an engine a contained change.
Engines take a voice in their own way, so each block answers the same three
questions about it: `voice_label` (a menu row), `voice_detail` (exactly which
voice) and `identity` (what makes clips comparable - a chapter narrated in
another voice is re-narrated, see audio/narration_voice.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from remanga.config.base import ConfigModel
from remanga.config.kokoro_voices import DEFAULT_VOICE, KokoroVoice, lang_code_for, voice_spec
from remanga.config.tts_engines import TTS_ENGINE_SPECS, TTS_ENGINES, TTSEngineSpec, engine_spec

__all__ = [
    "TTS_ENGINES",
    "TTS_ENGINE_SPECS",
    "KokoroConfig",
    "QwenConfig",
    "TTSConfig",
    "TTSEngineSpec",
    "engine_spec",
]

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


class KokoroConfig(ConfigModel):
    """hexgrad/Kokoro-82M in `.tools/venv-kokoro`: fixed, named voices
    (config/kokoro_voices.py), no reference recording and no design."""

    # Which of Kokoro's built-in voices narrates.
    voice: str = DEFAULT_VOICE
    # Speaking rate, applied by the model itself (1.0 = normal).
    speed: float = 1.0
    hf_repo_id: str = "hexgrad/Kokoro-82M"
    model_dir: str = "checkpoints/kokoro_82m"
    # Kokoro's native output rate; the pipeline resamples from here.
    sample_rate: int = 24000

    @property
    def spec(self) -> KokoroVoice:
        return voice_spec(self.voice)

    @property
    def voice_label(self) -> str:
        return self.spec.label

    @property
    def voice_detail(self) -> str:
        return f"{self.spec.label} ({self.spec.name}, grade {self.spec.grade})"

    @property
    def lang_code(self) -> str:
        """Kokoro's accent code for the voice - derived, since a mismatch makes a
        voice speak through the wrong accent's phonemes without any error."""
        return lang_code_for(self.voice)

    def identity(self) -> dict[str, Any]:
        return {"engine": "kokoro", "voice": self.voice, "speed": round(float(self.speed), 3)}


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
    # How to deliver the lines, in words - optional, and applies to both ways.
    instruct: str = "a calm narrator telling a story, steady and unhurried"
    # The description a voice was designed from, empty until one is designed.
    design: str = ""
    # The sample that design produced, and the line spoken in it. Narration
    # clones this file, so it is the voice itself, not a note about it.
    designed_sample: str = ""
    designed_text: str = ""
    language: str = "English"
    # One directory per model variant, fetched only when that way is used.
    model_root: str = "checkpoints/qwen3_tts"

    @property
    def designed(self) -> bool:
        """Whether a designed voice is what narrates (it needs its sample)."""
        return bool(self.design and self.designed_sample and Path(self.designed_sample).is_file())

    @property
    def voice_label(self) -> str:
        return f"designed: {self.design[:40]}" if self.designed else self.speaker.replace("_", " ")

    @property
    def voice_detail(self) -> str:
        if self.designed:
            return f"designed voice - {self.design}"
        return f"{self.speaker.replace('_', ' ')} ({self.instruct})" if self.instruct else self.speaker

    def identity(self) -> dict[str, Any]:
        if self.designed:
            sample = Path(self.designed_sample)
            return {"engine": "qwen", "voice": f"designed:{self.design}", "sample": sample.name,
                    "sample_mtime_ns": sample.stat().st_mtime_ns}
        return {"engine": "qwen", "voice": self.speaker, "instruct": self.instruct}


class TTSConfig(ConfigModel):
    # Which engine narrates - one of TTS_ENGINES (config/tts_engines.py).
    engine: str = "kokoro"
    # How long one synthesize call may take before the worker is treated as hung.
    synth_timeout_seconds: int = 300
    kokoro: KokoroConfig = Field(default_factory=KokoroConfig)
    qwen: QwenConfig = Field(default_factory=QwenConfig)

    @model_validator(mode="before")
    @classmethod
    def _from_older_versions(cls, data: Any) -> Any:
        """A config.json from the single-engine version kept Kokoro's settings
        at the top of `tts` - they move into the `kokoro` block. An unknown
        engine name falls back to the default rather than failing to load.

        Every key this model has is kept, whatever it holds: this also runs on
        assignment (validate_assignment), where dropping a field for not being
        in a shortlist leaves the model without it."""
        if not isinstance(data, dict):
            return data
        kept = {key: value for key, value in data.items() if key in cls.model_fields}
        lifted = {key: value for key, value in data.items() if key in KokoroConfig.model_fields}
        if lifted:
            kept["kokoro"] = {**lifted, **(kept.get("kokoro") or {})}
        if str(kept.get("engine", "")).strip().lower() not in TTS_ENGINES:
            kept["engine"] = TTS_ENGINES[0]
        return kept

    @property
    def spec(self) -> TTSEngineSpec:
        """The active engine's catalogue entry - its display name, its summary
        and which block is its own."""
        return engine_spec(self.engine)

    @property
    def engine_block(self) -> BaseModel:
        """The active engine's own settings, resolved through its spec rather
        than by branching on the engine name."""
        return getattr(self, self.spec.config_attr)

    @property
    def voice_label(self) -> str:
        return self.engine_block.voice_label

    @property
    def voice_detail(self) -> str:
        return self.engine_block.voice_detail

    def identity(self) -> dict[str, Any]:
        """What the clips on disk were narrated with - engine included, so
        switching engine re-narrates rather than mixing two voices."""
        return self.engine_block.identity()
