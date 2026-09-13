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
    # Off until a music file is actually chosen - nothing ships one, and a
    # mix that starts by warning about a path that was never set is a worse
    # first run than a recap with no bed under it. Choosing a file in
    # Settings -> Audio levels (or Assets) turns it on.
    bgm_enabled: bool = False
    bgm_path: str = ""
    # Fixed gain applied to the music, in dB.
    #
    # Worth knowing what this number is NOT: it is relative to the music
    # FILE's own loudness, not an absolute level. Two tracks mastered 6dB
    # apart at the same bgm_volume_db sit 6dB apart under the narration, so
    # a value tuned for one track is wrong for the next one dropped in.
    #
    # Which is why no default can be right for a file nobody has picked yet.
    # This one is the arithmetic for a TYPICAL modern-mastered track, about
    # -10 LUFS: Kokoro's narration measures -25.7 LUFS, so -35 puts the bed
    # at -45 LUFS, a little over 19 LU under the voice. That is close enough
    # to be listenable on the first render with any ordinary music file,
    # rather than the old -22, which left the same track roughly 6 LU under
    # the narration - loud enough to fight every line.
    #
    # It is still a guess about somebody else's file. Settings -> Audio
    # levels -> "Balance voice and music automatically" measures both sides
    # and replaces it with the real number (audio/leveling.py).
    bgm_volume_db: float = -35.0
    # The separation the automatic balance aims for, in LU (ITU-R BS.1770
    # loudness units - the same scale EBU R128 uses).
    #
    # Not applied at mix time - nothing here runs automatically. It is the
    # target the settings action uses when it MEASURES your narration and
    # your music and writes a corrected bgm_volume_db above, so the value in
    # config stays a plain number you can read and adjust.
    #
    # 20 is just past the quiet end of broadcast practice (15-20 below
    # dialogue), and that is deliberate: broadcast dialogue shares the track
    # with scenes the music carries alone, where a recap is spoken word from
    # first panel to last. Under 15 the music starts masking consonants,
    # worst on phone speakers. See leveling.BALANCE_PRESETS for the named
    # choices the settings screen offers around this one.
    #
    # Measured in LOUDNESS, not RMS, and the difference is real: this repo's
    # bed reads -12.61 dBFS RMS but -9.90 LUFS, so an RMS-derived gain leaves
    # the music ~2.7dB louder than intended - and by a margin that changes
    # with the track's spectral content.
    bgm_target_below_narration_db: float = 20.0
    enable_loudnorm: bool = True
