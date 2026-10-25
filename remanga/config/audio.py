"""Audio settings: the volume and the background music - see remanga/audio/mix.py.

Deliberately few (user request, 2026-10-25: "just keep the original vocal and
volume and background music volume"). The narration is the engine's take as
it read it: no effects, no pause cutting, the whole chapter in as few takes as
the engine allows, a narrator's pause (420 ms) between takes. The presets and the voice chain
are on the branch backup/presets-effects-2026-10-25."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    # How loud the finished chapter is, in LUFS: one gain over the whole mix,
    # measured. -14 is what YouTube plays at - a quieter video is not turned
    # up there and sounds weaker next to others.
    volume_lufs: float = Field(-14.0, validation_alias=AliasChoices("volume_lufs", "loudness_target_lufs"))
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
    # The level last typed in as "Custom..." (Settings - Music volume), kept so
    # it is offered again next time beside the presets, whichever level is in
    # use. None until one has been typed.
    bgm_custom_lu: float | None = None
