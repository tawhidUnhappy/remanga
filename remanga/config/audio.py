"""Audio mixing settings (BGM, loudnorm, edge fades) - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import BaseModel


class AudioConfig(BaseModel):
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
    bgm_volume_db: float = -22.0
    # Duck the music under the narration instead of holding it at one fixed
    # level for the whole recap (see audio/ducking.py).
    #
    # Off by default because it changes the character of a mix someone may
    # already be happy with, and because a fixed bed is the conventional
    # thing to expect. Turn it on when the narration is competing with the
    # music rather than sitting on top of it - which is the usual complaint,
    # and is not really fixable with bgm_volume_db alone: that one number has
    # to be quiet enough to stay clear of the words AND loud enough to be
    # worth having, and no value is both.
    #
    # This does NOT infer where the speech is. The mix assembles narration
    # panel by panel from audio_timing.json, so the spans are known exactly -
    # see ducking.duck_under_speech for why that beats a sidechain
    # compressor's guess.
    duck_music_under_narration: bool = False
    # How far the music drops while someone is speaking, in dB. Applied on
    # top of bgm_volume_db, so with ducking on it is usually right to RAISE
    # bgm_volume_db - the music can afford to be louder between lines
    # precisely because it gets out of the way during them.
    duck_depth_db: float = -9.0
    # Ramp either side of a speech passage. The dip starts this far BEFORE
    # the first word and recovers this long after the last, so the narrator
    # enters into music that has already stepped back. Too short reads as a
    # gate chattering; too long and the music is still receding when the line
    # is over.
    duck_fade_ms: int = 220
    # How much of the music's SPEECH BAND (~0.9-4.5kHz) is taken out while
    # ducking is on, in dB. This is the part that actually makes a difference
    # on continuous narration.
    #
    # Measured on a real chapter: 75 panels with 350ms pauses merge into one
    # speech passage, because nothing separates them by long enough to bring
    # the music back up. Level ducking there is just a quieter bed - which
    # bgm_volume_db already gives you - and the narration still sounds buried,
    # because masking is about WHERE the music's energy is, not only how much.
    # Pulling the middle down leaves the bass and air that make a bed worth
    # having, and stops the music competing for the consonants. Set to 0 to
    # duck by level alone.
    duck_carve_db: float = -7.0
    enable_loudnorm: bool = True
