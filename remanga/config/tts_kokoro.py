"""Kokoro-82M's settings block: a named voice and a speed."""

from __future__ import annotations

from typing import Any

from remanga.config.base import ConfigModel
from remanga.config.kokoro_voices import DEFAULT_VOICE, KOKORO_VOICES, KokoroVoice, lang_code_for, voice_spec


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

    def voice_options(self) -> list[tuple[str, str]]:
        """Every voice this engine can read in: (what it is called in config,
        what a person should see). The settings list and the voice sampler
        both read this, so neither can list a voice the other does not."""
        return [(v.name, f"{v.label} - grade {v.grade}, {v.accent}") for v in KOKORO_VOICES]

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
