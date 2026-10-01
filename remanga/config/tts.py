"""Narration settings: which engine reads the panels, and each engine's own
voice.

Engines are plug-ins (remanga/plugins/, kind "tts"), and each brings its own
settings block, so TTSConfig is BUILT from whichever engines are registered:
one field per engine, named after it (`tts.kokoro`, `tts.qwen`), holding that
engine's own config model. config.json keeps the same shape it always had.

What every engine shares (which one is active, how long a synthesis may take)
sits at the top. Engines take a voice in their own way, so each block answers
the same three questions about it: `voice_label` (a menu row), `voice_detail`
(exactly which voice) and `identity` (what makes clips comparable - a chapter
narrated in another voice is re-narrated, see audio/narration_voice.py)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, create_model, model_validator

from remanga import plugins
from remanga.config.base import ConfigModel

__all__ = ["TTSConfig"]


class TTSSettings(ConfigModel):
    """The part of TTSConfig every engine shares; TTSConfig adds one block per
    engine plug-in (see the bottom of this module)."""

    # Which engine narrates - a registered "tts" plug-in's name.
    engine: str = ""
    # How long one synthesize call may take before the worker is treated as hung.
    synth_timeout_seconds: int = 300

    @model_validator(mode="before")
    @classmethod
    def _from_older_versions(cls, data: Any) -> Any:
        """A config.json from the single-engine version kept Kokoro's settings
        at the top of `tts` - they move into the default engine's block. An
        unknown engine name falls back to the default rather than failing to
        load.

        Every key this model has is kept, whatever it holds: this also runs on
        assignment (validate_assignment), where dropping a field for not being
        in a shortlist leaves the model without it."""
        if not isinstance(data, dict):
            return data
        names = plugins.names("tts")
        kept = {key: value for key, value in data.items() if key in cls.model_fields}
        default_block = cls.model_fields.get(names[0]) if names else None
        if default_block is not None:
            block_fields = default_block.annotation.model_fields
            lifted = {key: value for key, value in data.items()
                      if key in block_fields and key not in cls.model_fields}
            if lifted:
                kept[names[0]] = {**lifted, **(kept.get(names[0]) or {})}
        if str(kept.get("engine", "")).strip().lower() not in names and names:
            kept["engine"] = names[0]
        return kept

    @property
    def spec(self) -> plugins.TTSEngine:
        """The active engine's plug-in - its display name, its summary and its
        code."""
        return plugins.get("tts", self.engine)

    @property
    def engine_block(self) -> BaseModel:
        """The active engine's own settings."""
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


def _build() -> type[TTSSettings]:
    engines = plugins.items("tts")
    blocks: dict[str, Any] = {}
    for engine in engines:
        model = plugins.resolve(engine.config)
        blocks[engine.config_attr] = (model, Field(default_factory=model))
    default = engines[0].name if engines else ""
    return create_model("TTSConfig", __base__=TTSSettings, __module__=__name__,
                        engine=(str, default), **blocks)


TTSConfig = _build()
