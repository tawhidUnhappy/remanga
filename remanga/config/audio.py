"""Audio settings: pauses, background music, loudness - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    # Silence after each page's narration before the next page's. Not 0: clips
    # come back trimmed tight to the speech, and butted together the sentences
    # run into each other; a narrator reading aloud takes 300-600ms.
    pause_between_pages_ms: int = Field(350, validation_alias=AliasChoices("pause_between_pages_ms",
                                                                           "pause_between_panels_ms"))
    # Background music: off until a file is chosen.
    bgm_enabled: bool = False
    bgm_path: str = ""
    # How far the music sits under the narration, in loudness units (LU). Both
    # are measured at mix time and the music's gain is set to match, so every
    # track sits at the same level however loud its file is mastered - a fixed
    # dB gain left one track 6 LU louder than another. 14 keeps the music
    # present enough to carry energy while every word stays clear; 18+ is a
    # quiet bed, under 12 starts to mask consonants on phone speakers.
    bgm_below_voice_lu: float = 14.0
    # Normalize the finished mix to `loudness_target_lufs` (two-pass, linear -
    # the level changes, the dynamics don't).
    enable_loudnorm: bool = True
    # -14 LUFS is what YouTube normalizes to: a quieter video is not turned up
    # and sounds weaker next to others.
    loudness_target_lufs: float = -14.0
