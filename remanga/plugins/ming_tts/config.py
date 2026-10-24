"""Ming-3.0-tts's settings block: which of its built-in English voices reads."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from remanga.config.base import ConfigModel


@dataclass(frozen=True)
class MingVoice:
    name: str
    label: str
    accent: str
    use: str


# Its English "IP" voices, as upstream's cookbooks/instruction_en.md lists
# them. The name is what the model is asked for, exactly.
MING_VOICES: tuple[MingVoice, ...] = (
    MingVoice("US_Stella", "Stella (female)", "american", "narration, warm, youthful"),
    MingVoice("US_James", "James (male)", "american", "narration, documentary reads"),
    MingVoice("US_Emma", "Emma (female)", "american", "narration, conversational"),
    MingVoice("UK_Charlotte", "Charlotte (female)", "british", "audiobooks, measured narration"),
    MingVoice("UK_George", "George (male)", "british", "audiobooks, formal"),
)

VOICE_BY_NAME = {v.name: v for v in MING_VOICES}
DEFAULT_VOICE = "US_Stella"


def voice_spec(name: str) -> MingVoice:
    """The voice named, or the default for a name it doesn't have - a typo in
    config.json narrates in the default voice rather than failing mid-chapter."""
    return VOICE_BY_NAME.get((name or "").strip(), VOICE_BY_NAME[DEFAULT_VOICE])


class MingConfig(ConfigModel):
    """inclusionAI/Ming-3.0-tts-0.5B in `.tools/venv-ming-tts`: a built-in voice
    (its "IP" task), no reference recording, no delivery instruction - one
    steady register."""

    voice: str = DEFAULT_VOICE
    hf_repo_id: str = "inclusionAI/Ming-3.0-tts-0.5B"
    model_dir: str = "checkpoints/ming_tts_0_5b"

    def voice_options(self) -> list[tuple[str, str]]:
        """Every voice it can read in - see KokoroConfig.voice_options."""
        return [(v.name, f"{v.label} - {v.accent}, {v.use}") for v in MING_VOICES]

    @property
    def spec(self) -> MingVoice:
        return voice_spec(self.voice)

    @property
    def voice_label(self) -> str:
        return self.spec.label

    @property
    def voice_detail(self) -> str:
        return f"{self.spec.label} ({self.spec.name})"

    def identity(self) -> dict[str, Any]:
        return {"engine": "ming", "voice": self.spec.name}
