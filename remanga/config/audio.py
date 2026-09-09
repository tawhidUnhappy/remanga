"""Audio mixing settings (BGM, loudnorm, edge fades) - see remanga/audio/mix.py."""

from __future__ import annotations

from remanga.config.base import ConfigModel


class AudioConfig(ConfigModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # The gap inserted between one panel's narration clip and the next in the
    # assembled master track (audio/mix.py) - not the silence a reaction-beat
    # panel's own empty-text clip gets (that's a fixed 500ms floor in
    # audio/tts.py, since it's the panel's content, not a gap between two
    # panels' audio).
    #
    # Not 0. Each panel is a whole sentence or two, and the engine hands back
    # clips trimmed tight to the speech - measured over a chapter, a median
    # of 35ms of lead-in and 81ms of tail. Butting those together leaves
    # ~115ms between the last phoneme of one sentence and the first of the
    # next, where a narrator reading aloud takes 300-600ms. That is what made
    # the narration sound like the words were running into each other: not
    # the synthesis, the assembly. 350ms puts the total gap in the middle of
    # that natural range.
    pause_between_panels_ms: int = 350
    bgm_enabled: bool = False
    bgm_path: str = ""
    # Fixed gain applied to the music, in dB. Used as-is when
    # bgm_auto_level is off; ignored when it is on.
    #
    # Worth knowing what this number is NOT: it is relative to the music
    # FILE's own loudness, not an absolute level. Two tracks mastered 6dB
    # apart at the same bgm_volume_db sit 6dB apart under the narration, so
    # a value tuned for one track is wrong for the next one dropped in.
    # That is what bgm_auto_level exists to fix.
    bgm_volume_db: float = -22.0
    # The separation the "correct my levels" action aims for, in dB.
    #
    # Not applied at mix time - nothing here runs automatically. It is the
    # target the settings action uses when it MEASURES your narration and
    # your music and writes a corrected bgm_volume_db above, so the value in
    # config stays a plain number you can read and adjust.
    #
    # 18 is the middle of broadcast practice (15-20 below dialogue). Under
    # 15 the music starts masking consonants, worst on phone speakers.
    bgm_target_below_narration_db: float = 18.0
    enable_loudnorm: bool = True
