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

A band "boost" here is a RELATIVE one - the bands either side are pulled
down and the whole signal brought back up - because adding a filtered copy
does not survive contact with real speech. See `_boost_band`."""

from __future__ import annotations

from pydub import AudioSegment
from pydub.effects import compress_dynamic_range

WARMTH_BAND_HZ = (110, 320)
PRESENCE_BAND_HZ = (2200, 5500)


def _band_energy_db(audio: AudioSegment, low_hz: int, high_hz: int) -> float:
    """Energy inside a band, as pydub's filters actually pass it."""
    return audio.high_pass_filter(low_hz).low_pass_filter(high_hz).dBFS


def _boost_band(audio: AudioSegment, low_hz: int, high_hz: int, boost_db: float) -> AudioSegment:
    """`audio` with the band between low_hz and high_hz lifted by boost_db.

    Done by REBUILDING the signal from three bands with the outer two pulled
    down, then restoring the overall level - not by overlaying a boosted copy
    of the band onto the original.

    That distinction was expensive to learn and is the whole reason this
    function looks the way it does. Adding a filtered copy is the obvious
    approach and it measures beautifully on white noise: calibrated, it
    delivered +3.00dB for +3.0dB asked. On real narration the same code
    delivered **+0.12dB**. Addition is phase-dependent, pydub's filters are
    single-pole and shift phase across the passband, and speech - unlike
    noise - has rapidly varying phase, so the copy cancels itself by an amount
    that changes moment to moment. No calibration constant can fix a factor
    that is not constant.

    Attenuation has no such problem: scaling a band is deterministic whatever
    its phase. The same reconstruction is what makes ducking.carve_speech_band
    work, which measured exactly as asked on the same material. So a "boost"
    here is really a relative one - everything else comes down, then the whole
    signal comes back up - which is audibly identical and actually happens."""
    if boost_db <= 0 or len(audio) == 0:
        return audio
    # Released as they are folded in - see the same note in
    # ducking.carve_speech_band. Every one of these is a full copy of the
    # track, and the full-manga narration is 56 minutes long.
    out = audio.low_pass_filter(low_hz) - boost_db
    highs = audio.high_pass_filter(high_hz) - boost_db
    out = out.overlay(highs)
    del highs
    mids = audio.high_pass_filter(low_hz).low_pass_filter(high_hz)
    out = out.overlay(mids)
    del mids
    return out + boost_db


# Why this is applied PER PANEL CLIP rather than to the assembled track
# (see audio/mix.py and full_recap/timeline.py):
#
# pydub's compress_dynamic_range builds a Python list holding one bytes
# object per audio FRAME, then joins it. At 44.1kHz a 56-minute full-manga
# narration is 147 million frames, and at ~41 bytes of per-object overhead
# that list alone is about 6GB - before the join allocates the whole track
# again alongside it. Measured: it invoked the kernel OOM killer at 13.5GB on
# a 14GB machine.
#
# Per clip the same work happens in bounded pieces: a 5-second line is ~220k
# frames, so peak memory is a few MB regardless of how long the chapter or
# the whole manga is. Nothing about the RESULT suffers - the warmth and
# presence stages are time-invariant filters, so per-clip is the same audio
# either way, and compressing per line is arguably more correct than
# compressing across the whole recap: makeup gain restores each clip to its
# own original RMS, so a shouted line stays louder than a quiet one while
# each is internally evened out.


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
        # Threshold RELATIVE to this track's own level, not an absolute dBFS
        # figure. A fixed threshold depends on how loud the engine happened to
        # synthesize: measured on real narration sitting at -26dBFS RMS, an
        # absolute -18 threshold barely engaged at all (crest 23.01 -> 22.88dB),
        # because almost nothing ever reached it. Anchoring to the RMS makes the
        # setting mean the same thing whatever the voice or engine.
        before_rms = voice.dBFS
        if before_rms == float("-inf"):
            return voice
        # attack/release left at pydub's defaults (5ms / 50ms): fast enough to
        # catch a consonant, slow enough not to chew the vowel behind it.
        compressed = compress_dynamic_range(
            voice, threshold=before_rms + compress_threshold_db, ratio=compress_ratio,
        )
        # Makeup gain. Without it this stage is not compression, it is
        # attenuation: measured, compressing alone took the track from
        # -26.3 to -29.5dBFS RMS, i.e. it made the narration quieter, which is
        # the opposite of what anyone turns compression on for. Restoring the
        # original RMS is what converts reduced dynamic range into density -
        # the peaks come down, then everything comes back up, so the quiet
        # parts end up louder than they started.
        if compressed.dBFS != float("-inf"):
            makeup_db = before_rms - compressed.dBFS
            # Never into clipping: pydub saturates rather than wrapping, and a
            # clipped narration track is far worse than an uncompressed one.
            headroom = -1.0 - (compressed.max_dBFS + makeup_db)
            compressed = compressed + makeup_db + min(0.0, headroom)
        voice = compressed
    return voice
