"""Edge voices' settings block: which of Microsoft's US English neural voices
reads, and how fast."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from remanga.config.base import ConfigModel


@dataclass(frozen=True)
class EdgeVoice:
    name: str
    label: str
    use: str


# US English voices of `edge-tts --list-voices` (checked against the service
# 2026-10-24). The name is what the service is asked for, exactly.
EDGE_VOICES: tuple[EdgeVoice, ...] = (
    EdgeVoice("en-US-GuyNeural", "Guy (male)", "news, narration - the classic recap voice"),
    EdgeVoice("en-US-AndrewNeural", "Andrew (male)", "warm, confident, conversational"),
    EdgeVoice("en-US-BrianNeural", "Brian (male)", "approachable, casual"),
    EdgeVoice("en-US-ChristopherNeural", "Christopher (male)", "reliable, authoritative"),
    EdgeVoice("en-US-EricNeural", "Eric (male)", "rational, plain"),
    EdgeVoice("en-US-RogerNeural", "Roger (male)", "lively"),
    EdgeVoice("en-US-SteffanNeural", "Steffan (male)", "rational, plain"),
    EdgeVoice("en-US-AriaNeural", "Aria (female)", "positive, confident"),
    EdgeVoice("en-US-AvaNeural", "Ava (female)", "expressive, caring"),
    EdgeVoice("en-US-EmmaNeural", "Emma (female)", "cheerful, clear"),
    EdgeVoice("en-US-JennyNeural", "Jenny (female)", "friendly, considerate"),
    EdgeVoice("en-US-MichelleNeural", "Michelle (female)", "friendly, pleasant"),
)

VOICE_BY_NAME = {v.name: v for v in EDGE_VOICES}
DEFAULT_VOICE = "en-US-GuyNeural"


def voice_spec(name: str) -> EdgeVoice:
    """The voice named, or the default for a name it doesn't have - a typo in
    config.json narrates in the default voice rather than failing mid-chapter."""
    return VOICE_BY_NAME.get((name or "").strip(), VOICE_BY_NAME[DEFAULT_VOICE])


class EdgeConfig(ConfigModel):
    """Microsoft Edge's online voices in `.tools/venv-edge-tts`, read raw at
    the service's own pace: no speed/rate setting (user, 2026-10-27: "used
    raw instead of speed up"). An old config's "speed" is ignored."""

    voice: str = DEFAULT_VOICE

    def voice_options(self) -> list[tuple[str, str]]:
        """Every voice it can read in - see KokoroConfig.voice_options."""
        return [(v.name, f"{v.label} - {v.use}") for v in EDGE_VOICES]

    @property
    def spec(self) -> EdgeVoice:
        return voice_spec(self.voice)

    @property
    def voice_label(self) -> str:
        return self.spec.label

    @property
    def voice_detail(self) -> str:
        return f"{self.spec.label} ({self.spec.name})"

    def identity(self) -> dict[str, Any]:
        # "speed": 1.0 stays so takes made before the setting went are still
        # the same recipe (store/versions.py) and are reused.
        return {"engine": "edge", "voice": self.spec.name, "speed": 1.0}
