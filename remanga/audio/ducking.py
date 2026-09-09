"""Pulls the music down under the narration, and lets it back up between lines.

The mix used to sit the BGM at one fixed level for the whole recap
(`audio.bgm_volume_db`), which forces an unwinnable choice: loud enough to be
worth having, or quiet enough to stay out of the narrator's way. At -26dB it
is doing neither well - present enough to blur the words, too quiet to carry
a scene on its own. Ducking removes the choice: the music plays at a level
worth hearing and steps aside whenever someone is speaking.

Why an explicit envelope rather than ffmpeg's `sidechaincompress`: a
sidechain compressor infers where the speech is from the signal, and gets it
wrong at exactly the moments that matter - a soft line opens the gate late
and clips its own first syllable, a breath or a room tone holds the music
down through a pause. This pipeline does not have to infer anything. It
assembles the narration panel by panel from `audio_timing.json`, so the
speech boundaries are known exactly, to the millisecond, before a single
sample is mixed. Ducking to ground truth is both simpler and better than
ducking to a detector's guess.

Nearby spans are merged (see `merge_spans`) so the music does not pump up and
down through the short gaps between panels - a human mixer rides the fader
down for a passage of speech, not for each sentence in it."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydub import AudioSegment

# Speech spans closer together than this (after their fades are accounted
# for) are treated as one passage. Roughly the gap below which letting the
# music swell back up reads as a mistake rather than a breath.
_MERGE_GAP_MS = 1200

# The band speech intelligibility actually lives in. Consonants - the
# difference between "back" and "bat" - sit here, and music with energy in
# the same band masks them however the levels are set.
_SPEECH_BAND_LOW_HZ = 900
_SPEECH_BAND_HIGH_HZ = 4500


def merge_spans(spans: Iterable[tuple[int, int]], gap_ms: int = _MERGE_GAP_MS) -> list[tuple[int, int]]:
    """Overlapping or nearly-touching spans, combined into single passages."""
    ordered = sorted((int(s), int(e)) for s, e in spans if e > s)
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start - merged[-1][1] <= gap_ms:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def carve_speech_band(music: AudioSegment, carve_db: float) -> AudioSegment:
    """`music` with its middle rebuilt quieter, leaving a hole for the voice.

    This is the half of the job ducking cannot do on continuous narration.
    Measured on a real chapter: 75 panels separated by 350ms pauses merge into
    ONE speech passage, because there is no gap long enough to bring the music
    back up in. Ducking such a track is arithmetically just a level change -
    the music is down for the whole chapter, which `bgm_volume_db` already
    does. Yet the narration still sounds buried, because the problem was never
    only level: music with energy between roughly 1-4kHz masks the consonants
    that carry intelligibility, at ANY level where it is still worth hearing.

    So the middle is pulled down RELATIVE to the bass and the air, which is
    where a music bed does its emotional work. Note "relative": the level
    duck that runs after this lowers the whole bed as well, so the lows are
    not literally untouched - what the carve buys is that the reduction is
    concentrated where it helps. Measured on a real chapter, carve plus duck
    took 10.6dB out of the 0.9-4.5kHz band against 9dB everywhere else, and
    the narration went from 19.6dB to 30.2dB above the music IN THAT BAND.
    Because the music now stays out of the way, `bgm_volume_db` can usually
    come UP - a bed that is present between lines and transparent under them
    beats one that is uniformly quiet and still muddying the consonants.

    Reconstructed from three filtered copies rather than with a true
    parametric EQ, because pydub has no biquad: lows + highs at full level,
    mids attenuated. The band edges are gentle single-pole rolloffs, which is
    an advantage here - a surgical notch would sound like a hole, and this
    sounds like a mix."""
    if carve_db >= 0 or len(music) == 0:
        return music
    lows = music.low_pass_filter(_SPEECH_BAND_LOW_HZ)
    highs = music.high_pass_filter(_SPEECH_BAND_HIGH_HZ)
    mids = music.high_pass_filter(_SPEECH_BAND_LOW_HZ).low_pass_filter(_SPEECH_BAND_HIGH_HZ) + carve_db
    return lows.overlay(highs).overlay(mids)


def duck_under_speech(
    music: AudioSegment,
    spans: Sequence[tuple[int, int]],
    *,
    depth_db: float,
    fade_ms: int,
) -> AudioSegment:
    """`music` with every speech passage attenuated by `depth_db`.

    The dip starts `fade_ms` BEFORE each passage and recovers `fade_ms` after
    it, so the narrator opens their mouth into music that has already stepped
    back rather than pushing it out of the way mid-word - the same anticipation
    a person riding a fader would use, and the reason this reads as intentional
    rather than as an automatic gate chattering.

    Returns `music` unchanged when there is nothing to duck, so a caller can
    hand it any timeline without special-casing silence."""
    if not spans or depth_db >= 0 or len(music) == 0:
        return music

    fade_ms = max(0, int(fade_ms))
    total = len(music)
    passages = merge_spans(spans)

    out = AudioSegment.empty()
    cursor = 0
    for start, end in passages:
        dip_start = max(0, min(total, start - fade_ms))
        dip_end = max(0, min(total, end + fade_ms))
        if dip_end <= cursor:
            continue
        dip_start = max(dip_start, cursor)

        # Music at full level up to where the dip begins.
        if dip_start > cursor:
            out += music[cursor:dip_start]

        # Ramp down, hold, ramp up. Each ramp is applied to its own slice so
        # the gain change is a real interpolation rather than a step - a step
        # here is audible as a click on a sustained note.
        ramp_down_end = min(dip_start + fade_ms, dip_end)
        if ramp_down_end > dip_start:
            out += music[dip_start:ramp_down_end].fade(
                from_gain=0.0, to_gain=depth_db, start=0, duration=ramp_down_end - dip_start,
            )
        ramp_up_start = max(ramp_down_end, dip_end - fade_ms)
        if ramp_up_start > ramp_down_end:
            out += music[ramp_down_end:ramp_up_start] + depth_db
        if dip_end > ramp_up_start:
            out += music[ramp_up_start:dip_end].fade(
                from_gain=depth_db, to_gain=0.0, start=0, duration=dip_end - ramp_up_start,
            )
        cursor = dip_end

    if cursor < total:
        out += music[cursor:]

    # Slice arithmetic on a lossy frame grid can land a frame or two out;
    # the mix overlays this onto a track of a known length, so pin it.
    if len(out) > total:
        return out[:total]
    if len(out) < total:
        return out + music[len(out):]
    return out
