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
    # How far the music's LOUD PARTS sit under the narration, in loudness
    # units (LU): the voice measured whole, the music by its loud parts
    # (audio/mix.py:music_gain_db), so a chorus or a drop never comes up
    # louder than this, whatever the track. 18 is a quiet bed felt under every
    # word; 20+ is barely there; under 14 it starts to mask consonants on
    # phone speakers, which lose the music's bass but not the voice.
    bgm_below_voice_lu: float = 18.0
    # The level last typed in as "Custom..." (Settings - Music volume), kept so
    # it is offered again next time beside the presets, whichever level is in
    # use. None until one has been typed.
    bgm_custom_lu: float | None = None
