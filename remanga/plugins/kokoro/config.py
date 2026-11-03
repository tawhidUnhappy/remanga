"""Kokoro-82M's settings block: a named voice, read at its own pace."""

from __future__ import annotations

from typing import Any

from remanga.config.base import ConfigModel
from remanga.plugins.kokoro.voices import (
    DEFAULT_VOICE,
    KOKORO_VOICES,
    VOICE_BY_NAME,
    KokoroVoice,
    lang_code_for,
    marked_label,
    voice_spec,
)


class KokoroConfig(ConfigModel):
    """hexgrad/Kokoro-82M in `.tools/venv-kokoro`: fixed, named voices
    (voices.py), no reference recording and no design."""

    # Which of Kokoro's built-in voices narrates - read raw, at the voice's
    # own pace: no speed setting (user, 2026-10-27: "used raw instead of
    # speed up or any other modification"). An old config's "speed" is ignored.
    voice: str = DEFAULT_VOICE
    # A second voice blended into it (Settings - Mix with; user request,
    # 2026-10-27): the two voice packs averaged, `mix_share` of the second -
    # a voice of its own. "" = no mix. The accent stays the first voice's.
    mix_voice: str = ""
    mix_share: float = 0.3
    hf_repo_id: str = "hexgrad/Kokoro-82M"
    model_dir: str = "checkpoints/kokoro_82m"
    # Kokoro's native output rate; the pipeline resamples from here.
    sample_rate: int = 24000

    def voice_options(self) -> list[tuple[str, str]]:
        """Every voice this engine can read in: (what it is called in config,
        what a person should see). The settings list and the voice sampler
        both read this, so neither can list a voice the other does not."""
        return [(v.name, f"{marked_label(v)} - grade {v.grade}, {v.accent}") for v in KOKORO_VOICES]

    @property
    def spec(self) -> KokoroVoice:
        return voice_spec(self.voice)

    @property
    def mix(self) -> KokoroVoice | None:
        """The voice blended in, when a real mix is set."""
        other = VOICE_BY_NAME.get((self.mix_voice or "").strip())
        return other if other and other.name != self.spec.name and 0 < self.mix_share < 1 else None

    @property
    def mix_percent(self) -> int:
        return round(self.mix_share * 100)

    @property
    def voice_label(self) -> str:
        mix = self.mix
        return f"{self.spec.label} + {self.mix_percent}% {mix.label}" if mix else marked_label(self.spec)

    @property
    def voice_detail(self) -> str:
        mix = self.mix
        blend = f", {self.mix_percent}% {mix.name} mixed in" if mix else ""
        return f"{self.spec.label} ({self.spec.name}, grade {self.spec.grade}{blend})"

    @property
    def lang_code(self) -> str:
        """Kokoro's accent code for the voice - derived, since a mismatch makes a
        voice speak through the wrong accent's phonemes without any error."""
        return lang_code_for(self.voice)

    def identity(self) -> dict[str, Any]:
        # "speed": 1.0 stays so takes made before the setting went are still
        # the same recipe (store/versions.py) and are reused, not read again.
        identity: dict[str, Any] = {"engine": "kokoro", "voice": self.voice, "speed": 1.0}
        if self.mix:  # another voice: its takes are its own
            identity.update(mix=self.mix.name, mix_percent=self.mix_percent)
        return identity
