"""Kokoro-82M narration settings - see remanga/audio/synth/kokoro.py.

hexgrad/Kokoro-82M runs in its own isolated `.tools/venv-kokoro`. It has fixed,
named voices (config/kokoro_voices.py) - no reference recording."""

from __future__ import annotations

from typing import Any

from pydantic import model_validator

from remanga.config.base import ConfigModel
from remanga.config.kokoro_voices import DEFAULT_VOICE, KokoroVoice, lang_code_for, voice_spec

DISPLAY_NAME = "Kokoro-82M"


class TTSConfig(ConfigModel):
    # Which of Kokoro's built-in voices narrates.
    voice: str = DEFAULT_VOICE
    # Speaking rate, applied by the model itself (1.0 = normal).
    speed: float = 1.0
    # Gain on every synthesized clip, in dB. With background music and the
    # master's loudness normalization this mostly sets how far the music sits
    # under the voice. Changing it re-applies only the difference to clips
    # already synthesized - see audio/tts.py.
    volume_boost_db: float = 0.0
    # How long one synthesize call may take before the worker is treated as hung.
    synth_timeout_seconds: int = 180
    hf_repo_id: str = "hexgrad/Kokoro-82M"
    model_dir: str = "checkpoints/kokoro_82m"
    # Kokoro's native output rate; the pipeline resamples from here.
    sample_rate: int = 24000

    @model_validator(mode="before")
    @classmethod
    def _from_engine_blocks(cls, data: Any) -> Any:
        """A config.json from the multi-engine version kept Kokoro's settings
        in a `kokoro` block beside the other engines' - lifted up here, the
        rest dropped."""
        if not isinstance(data, dict):
            return data
        lifted = {key: value for key, value in data.items() if key in cls.model_fields}
        block = data.get("kokoro")
        if isinstance(block, dict):
            lifted.update({key: value for key, value in block.items() if key in cls.model_fields})
        return lifted

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
