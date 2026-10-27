"""Fish Audio Drama 3's settings block: which narrator it is asked for, and
the seed that keeps that narrator the same from chapter to chapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from remanga.config.base import ConfigModel


@dataclass(frozen=True)
class DramaVoice:
    name: str
    label: str
    cue: str
    use: str


# Drama 3 has no named voices: with no recording it picks a voice itself, and
# a cue in brackets at the start of the text steers which (speech.cpp's
# docs/models/drama3.md, "A voice described in words"). The cue is not read
# aloud. Each take opens with the cue under the same seed, so each take picks
# the same narrator (or, with `voice_file`, every take is read from a voice
# file made once from it - scripts/drama3_worker.py).
DRAMA_VOICES: tuple[DramaVoice, ...] = (
    DramaVoice("deep_male", "Deep male narrator", "[deep, calm male narrator voice]",
               "low and steady, documentary"),
    DramaVoice("warm_male", "Warm male narrator", "[warm, clear male narrator voice]",
               "friendly storyteller"),
    DramaVoice("warm_female", "Warm female narrator", "[warm, clear female narrator voice]",
               "friendly storyteller"),
    DramaVoice("calm_female", "Calm female narrator", "[soft, calm female narrator voice]",
               "gentle, audiobook"),
    # Picked by ear from 17 auditioned descriptions (2026-10-27): seed 1 gives a smooth,
    # slightly deep young man (~82 Hz). The cue must stay word for word - with the seed,
    # it is what the voice file was made from.
    DramaVoice("smooth_young_male", "Smooth young male narrator",
               "[smooth, slightly deep young man's voice, casual]", "smooth, slightly deep, casual"),
    DramaVoice("model", "Model's choice", "",
               "no description - the model picks, and the seed decides"),
)

VOICE_BY_NAME = {v.name: v for v in DRAMA_VOICES}
DEFAULT_VOICE = "deep_male"


def voice_spec(name: str) -> DramaVoice:
    """The voice named, or the default for a name it doesn't have - a typo in
    config.json narrates in the default voice rather than failing mid-chapter."""
    return VOICE_BY_NAME.get((name or "").strip(), VOICE_BY_NAME[DEFAULT_VOICE])


class Drama3Config(ConfigModel):
    """fishaudio/drama-3 as speech.cpp's Q4_K file (20.8 GB), run by speech.cpp
    on Vulkan with the experts the GPU cannot hold on the CPU. A described
    voice, no reference recording; `seed` is fixed so the same description
    gives the same narrator every chapter."""

    voice: str = DEFAULT_VOICE
    seed: int = 1
    model_name: str = "drama-3"
    model_dir: str = "checkpoints/speech_cpp"
    threads: int = 0   # 0 = speech.cpp's own default (the performance cores)
    # GPU memory kept free for speech.cpp's working buffers, in GiB - see
    # scripts/drama3_worker.py. More = fewer layers' experts on the GPU
    # (each ~0.45 GB), slower but safer; 0 ran a 12 GB card out of memory.
    gpu_headroom_gb: float = 2.5
    # Read every take from a voice file of the described voice (made once)
    # rather than in the model's own voice (scripts/drama3_worker.py). On: in
    # its own voice the narrator changed from page to page (per-take median
    # pitch 79-123 Hz over a chapter, against 90-107 from a voice file) -
    # the user heard it ("voice don't match") and asked for it fixed,
    # 2026-10-25.
    voice_file: bool = True

    def voice_options(self) -> list[tuple[str, str]]:
        """Every voice it can read in - see KokoroConfig.voice_options."""
        return [(v.name, f"{v.label} - {v.use}") for v in DRAMA_VOICES]

    @property
    def spec(self) -> DramaVoice:
        return voice_spec(self.voice)

    @property
    def voice_label(self) -> str:
        return self.spec.label

    @property
    def voice_detail(self) -> str:
        return f"{self.spec.label} ({self.spec.name}, seed {self.seed})"

    def identity(self) -> dict[str, Any]:
        # "voice_file": 1 when the takes are read from a voice file - a take
        # made the other way is another reading, made again.
        return {"engine": "drama3", "voice": self.spec.name, "seed": self.seed,
                "voice_file": int(self.voice_file)}
