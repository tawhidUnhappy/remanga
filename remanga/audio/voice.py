"""Makes the narration sound thick and forward, instead of thin and far away.

The complement to ducking (audio/ducking.py). That one gets the music out of
the voice's way; this one gives the voice something worth listening to once
the way is clear. A recap narrator competing with music needs both - a thin
track with the bed pulled down is still thin.

The chain is the conventional broadcast one, in the conventional order,
because the order is what makes it work:

  1. **High-pass.** Below ~85Hz a voice carries no information, only rumble
     and plosive thump. Removing it FIRST matters more than it looks: every
     later stage is level-dependent, and a compressor fed unfiltered lows
     spends its gain reduction reacting to energy nobody can hear.
  2. **Warmth**, a lift around 110-320Hz - the body of a voice, and what
     "thick" actually means. Overdone this is the classic muddy-podcast
     sound, so the default is deliberately modest.
  3. **Presence**, a lift around 2.2-5.5kHz - consonant definition, and what
     makes a voice read as close rather than distant. This is also the band
     the music carve clears out (ducking.carve_speech_band), so the two are
     designed to meet: the music steps out of exactly the range the voice
     steps into.
  4. **Compression** LAST. It evens out the difference between a loud line
     and a quiet one, which is what makes narration sit at a constant
     distance from the listener rather than drifting. Placed after the EQ so
     it responds to the voice as finally shaped - compressing first and
     boosting afterwards would just re-introduce the variation it removed.

A band "boost" here is an overlay of a band-passed copy, since pydub has no
shelving EQ, and the gain applied to that copy is calibrated against the
actual audio rather than derived - see `_boost_band` for the measurement that
made that necessary."""

from __future__ import annotations

from pydub import AudioSegment
from pydub.effects import compress_dynamic_range

WARMTH_BAND_HZ = (110, 320)
PRESENCE_BAND_HZ = (2200, 5500)


def _band_energy_db(audio: AudioSegment, low_hz: int, high_hz: int) -> float:
    """Energy inside a band, as pydub's filters actually pass it."""
    return audio.high_pass_filter(low_hz).low_pass_filter(high_hz).dBFS


def _boost_band(
    audio: AudioSegment, low_hz: int, high_hz: int, boost_db: float, *, probe_ms: int = 15000,
) -> AudioSegment:
    """`audio` with the band between low_hz and high_hz lifted by boost_db.

    Implemented by overlaying a band-passed copy, since pydub has no shelving
    EQ. The copy has to be attenuated before it is added, and working out by
    how much is where this gets interesting.

    The algebra says solve 1 + x = 10^(boost/20) - overlaying an unattenuated
    copy doubles the band, i.e. +6dB. That is what this did first, and
    MEASURED IT DELIVERS UNDER HALF: asking +3.0dB produced +1.26dB in the
    warmth band and +1.13dB in the presence band. The algebra assumes the
    copy adds coherently, and it does not - pydub's filters are single-pole,
    so the copy comes back phase-shifted and partially cancels, by an amount
    that depends on the band and on the material.

    Rather than pick a fudge factor, the copy's gain is calibrated against
    this actual audio: a short probe slice is boosted at trial gains until
    the measured band delta matches what was asked. Bisection, on a slice
    rather than the whole track, so the cost is a handful of filter passes
    over ~15 seconds regardless of how long the chapter is. What the setting
    promises is then what the mix delivers, which for a number a human is
    supposed to tune by ear is the whole point."""
    if boost_db <= 0 or len(audio) == 0:
        return audio

    # A slice from the middle: the head of a narration track is often a beat
    # of near-silence, and calibrating against that measures the room, not
    # the voice.
    if len(audio) > probe_ms:
        start = (len(audio) - probe_ms) // 2
        probe = audio[start:start + probe_ms]
    else:
        probe = audio
    if probe.dBFS == float("-inf"):
        return audio

    baseline = _band_energy_db(probe, low_hz, high_hz)

    def delivered(copy_gain_db: float) -> float:
        band = probe.high_pass_filter(low_hz).low_pass_filter(high_hz) + copy_gain_db
        return _band_energy_db(probe.overlay(band), low_hz, high_hz) - baseline

    # Bracket: -60dB is inaudible, +12dB is far past doubling. Bisect to
    # within a tenth of a dB, which is below what anyone can hear anyway.
    low, high = -60.0, 12.0
    if delivered(high) < boost_db:
        copy_gain_db = high            # cannot reach it; get as close as possible
    else:
        for _ in range(24):
            mid = (low + high) / 2
            if delivered(mid) < boost_db:
                low = mid
            else:
                high = mid
            if high - low < 0.1:
                break
        copy_gain_db = (low + high) / 2

    band = audio.high_pass_filter(low_hz).low_pass_filter(high_hz) + copy_gain_db
    return audio.overlay(band)


def enhance_voice(
    voice: AudioSegment,
    *,
    highpass_hz: int,
    warmth_db: float,
    presence_db: float,
    compress: bool,
    compress_threshold_db: float,
    compress_ratio: float,
) -> AudioSegment:
    """The narration track, processed. Returns it untouched if every stage is
    disabled, so a caller can run this unconditionally."""
    if len(voice) == 0:
        return voice

    if highpass_hz > 0:
        voice = voice.high_pass_filter(highpass_hz)
    voice = _boost_band(voice, *WARMTH_BAND_HZ, warmth_db)
    voice = _boost_band(voice, *PRESENCE_BAND_HZ, presence_db)

    if compress:
        # attack/release left at pydub's defaults (5ms / 50ms): fast enough to
        # catch a consonant, slow enough not to chew the vowel behind it.
        voice = compress_dynamic_range(
            voice, threshold=compress_threshold_db, ratio=compress_ratio,
        )
    return voice
