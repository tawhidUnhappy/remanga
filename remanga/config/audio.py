"""Audio settings: pauses, background music, loudness - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import AliasChoices, Field

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # Silence after each panel's narration before the next panel's. Not 0: clips
    # come back trimmed tight to the speech, and butted together the sentences
    # run into each other; a narrator reading aloud takes 300-600ms.
    pause_between_panels_ms: int = Field(350, validation_alias=AliasChoices("pause_between_panels_ms",
                                                                            "pause_between_pages_ms"))
    # Narrate several panels in one generation instead of one each. A panel
    # synthesized alone is a take of its own - Qwen reads it with no idea what
    # came before, so the tone resets every panel, which is audible in a way
    # no amount of trimming the joins can fix. Off by default while it proves
    # itself; the per-panel path is unchanged underneath it.
    batch_narration: bool = False
    # About how long one of those generations should be, capped by
    # audio/batching.py:MAX_BATCH_SECONDS - which is also why the default is a
    # minute: a cloned voice measurably drifts away from its reference as a
    # take goes on (see that constant for the numbers), and a minute is where
    # it still measures as the reference. Longer means fewer seams to hear,
    # a voice less like the one asked for, and more audio to make again when
    # one line changes.
    batch_target_minutes: float = 1.0
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
