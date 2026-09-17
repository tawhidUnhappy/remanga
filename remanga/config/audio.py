"""Audio settings: pauses, background music, loudness - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # Silence after each page's narration before the next page's. Not 0: clips
    # come back trimmed tight to the speech, and butted together the sentences
    # run into each other; a narrator reading aloud takes 300-600ms.
    pause_between_pages_ms: int = Field(350, validation_alias=AliasChoices("pause_between_pages_ms",
                                                                           "pause_between_panels_ms"))
    # Background music: off until a file is chosen.
    bgm_enabled: bool = False
    bgm_path: str = ""
    # Gain on the music in dB, relative to the music FILE's own loudness - so a
    # value tuned for one track is wrong for a louder or quieter one. -35 puts a
    # typical modern track (about -10 LUFS) roughly 20 LU under Kokoro's
    # narration.
    bgm_volume_db: float = -35.0
    # Normalize the finished mix to broadcast loudness (EBU R128).
    enable_loudnorm: bool = True
