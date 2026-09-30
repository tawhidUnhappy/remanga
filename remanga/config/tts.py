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

from typing import Any

from pydantic import BaseModel, Field, model_validator

from remanga.config.base import ConfigModel
from remanga.config.tts_engines import TTS_ENGINE_SPECS, TTS_ENGINES, TTSEngineSpec, engine_spec

from .tts_kokoro import KokoroConfig
from .tts_qwen import QwenConfig

__all__ = [
    "TTS_ENGINES",
    "TTS_ENGINE_SPECS",
    "KokoroConfig",
    "QwenConfig",
    "TTSConfig",
    "TTSEngineSpec",
    "engine_spec",
]


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
