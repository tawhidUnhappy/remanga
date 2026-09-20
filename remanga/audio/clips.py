"""What happens to one synthesized panel clip between the engine and disk.

The edge fades and the atomic write - what every clip goes through once the
synthesizer hands it back, and neither of which has anything to do with
walking a chapter's narration or building its timing manifest. Kept together
here, audio/tts.py is left doing the one job its name claims: turning a
narration script into a chapter of audio."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_leading_silence

# How much of a clip the fade-out may ramp when the clip has no silence to
# fade over: a voice that stops dead at the last sample clicks and sounds cut
# off, and a few tens of milliseconds at the end is inaudible as a fade but
# audible as its absence. The START is never treated this way - ramping the
# first phoneme is what swallowed the opening of nearly every line once.
TAIL_INTO_SPEECH = 0.15

# A fade this short is inaudible even when it lands directly on a consonant,
# and it's already all it takes to stop a clip that begins on a non-zero
# sample from clicking. It's the floor every clip gets; anything longer has
# to be paid for out of the clip's own silence (see apply_edge_fades).
DECLICK_FADE_MS = 6

# What counts as silence when apply_edge_fades measures how much room a clip
# has to fade over. Well below speech but above the synthesizer's noise
# floor, so a near-silent lead-in still reads as silence to fade over. Only
# the fades use it: deciding where the speech itself begins takes more than a
# threshold (see SUSTAIN_BLOCKS), while a fade only needs to know roughly how
# much quiet it has to work with and costs nothing when it guesses low.
EDGE_SILENCE_DBFS = -50.0


# What a clip is allowed to keep of its own silence at each end. The
# synthesizer bakes in whatever it feels like - measured across a finished
# 137-panel chapter, the lead ran from 0 to 460ms with a median of 370 and a
# standard deviation of 164 - so a clip used as it comes carries a pause
# nobody chose and that changes every panel. That unevenness is what makes a
# chapter sound like someone recording each panel separately rather than
# reading it through. Trimmed to this, the gap between panels is
# `pause_between_panels_ms` and nothing else, which is what that setting has
# always claimed to be. Not zero: the fades need somewhere to land, and a
# join with no silence at all on either side clicks.
SILENCE_KEEP_MS = 25

# How far below a clip's OWN speech level a stretch has to sit to count as
# silence. Relative rather than the absolute threshold this used, because the
# level a clip comes back at belongs to the engine, not to us - Kokoro, a
# Qwen preset narrator and a designed voice all land somewhere different, and
# a fixed number is only ever right for the one it was measured against.
# Across a finished 137-panel Qwen chapter, speech blocks sit at about
# -20 dBFS and the room tone either side of them between -48 and -70.
SPEECH_FLOOR_DB = 22.0

# A clip with nothing above this has no speech in it to find, and is left
# whole rather than trimmed against its own noise floor.
MIN_SPEECH_DBFS = -45.0

# How long a stretch has to hold up before it is called speech, and the block
# the level is measured in. A SINGLE block was enough before this, and that
# is what left the gaps: measured over that same chapter, a clip whose very
# first 10ms of room tone happened to reach -48 dBFS - against a -50
# threshold - had its entire 400ms lead-in kept as if it were speech, and
# butted against the previous clip's equally-kept tail it played as a hole of
# up to 590ms. The pause setting could not close those, because they are not
# pause: they are inside `duration_ms`. Requiring 30ms of sustained level
# takes the worst join from 590ms to 110ms and the joins holding more than
# 120ms of silence from 33 of 136 to none, while the loudest thing trimmed
# anywhere in the chapter is still 16dB below that clip's own speech.
SUSTAIN_BLOCKS = 3
BLOCK_MS = 10


def _block_levels(segment: AudioSegment) -> np.ndarray:
    """The clip as one dBFS reading per BLOCK_MS - the same measure pydub's
    silence helpers take, in a single pass rather than a slice per block."""
    samples = np.asarray(segment.get_array_of_samples(), dtype=np.float64)
    if segment.channels > 1:
        samples = samples.reshape(-1, segment.channels).mean(axis=1)
    per_block = max(1, int(segment.frame_rate * BLOCK_MS / 1000))
    count = len(samples) // per_block
    if count == 0:
        return np.empty(0)
    blocks = samples[:count * per_block].reshape(count, per_block)
    full_scale = float(1 << (8 * segment.sample_width - 1))
    rms = np.sqrt((blocks ** 2).mean(axis=1)) / full_scale
    with np.errstate(divide="ignore"):
        return 20 * np.log10(rms + 1e-12)


def speech_bounds(segment: AudioSegment, keep_ms: int = SILENCE_KEEP_MS) -> tuple[int, int]:
    """Where in a clip its speech starts and stops, leaving `keep_ms` of the
    clip's own silence either side of it.

    Speech is the first and last stretch that holds SUSTAIN_BLOCKS blocks
    above the clip's own speech level less SPEECH_FLOOR_DB - not the first
    block over a fixed threshold, which any stray tick of room tone satisfied
    (see SUSTAIN_BLOCKS for what that cost).

    Returned as offsets rather than a trimmed clip on purpose: they are
    written into audio_timing.json, and everything downstream lays itself out
    from that file. The clip on disk is never cut - it is what the model
    returned, and re-deciding this is a re-mix, not a re-narration."""
    levels = _block_levels(segment)
    if levels.size < SUSTAIN_BLOCKS:
        return 0, len(segment)

    speech_level = float(np.percentile(levels, 95))
    if speech_level < MIN_SPEECH_DBFS:      # nothing but silence - leave it alone
        return 0, len(segment)

    loud = (levels >= speech_level - SPEECH_FLOOR_DB).astype(int)
    held = np.convolve(loud, np.ones(SUSTAIN_BLOCKS, dtype=int), "valid")
    starts = np.flatnonzero(held == SUSTAIN_BLOCKS)
    if starts.size == 0:                    # never holds up - leave it alone
        return 0, len(segment)

    speech_start_ms = int(starts[0]) * BLOCK_MS
    speech_end_ms = (int(starts[-1]) + SUSTAIN_BLOCKS) * BLOCK_MS
    return max(0, speech_start_ms - keep_ms), min(len(segment), speech_end_ms + keep_ms)


def apply_edge_fades(segment: AudioSegment, edge_fade_ms: int, *,
                     fade_in: bool = True, fade_out: bool = True) -> AudioSegment:
    """De-clicks a clip's edges without ever ramping its speech.

    `fade_in`/`fade_out` turn an edge off, for an edge that is not really an
    edge: consecutive panels of one batched take are slices of the same
    generation, so laying them end to end joins samples that were already
    adjacent. There is nothing there to click, and fading every panel's last
    35ms would put an audible dip in the middle of a sentence the model read
    straight through.

    `edge_fade_ms` is the length asked for, and the two edges treat it
    differently.

    At the START it is a ceiling: the fade is at most the silence the clip
    actually has there, so it shapes the lead-in and never the first phoneme.
    Applying the configured 35ms flat - as this once did - ramped the opening
    consonant itself: across a finished chapter the first 35ms of 52 of 60
    clips came back ~36x quieter than the speech right after them, which
    swallowed the start of nearly every line.

    At the END it may ramp speech, up to TAIL_INTO_SPEECH of the clip. Clips
    often end within ten milliseconds of the last word (measured across a
    real chapter), and a voice that stops at the last sample clicks and
    sounds cut off; a few tens of milliseconds of ramp there is inaudible in
    itself."""
    if edge_fade_ms <= 0 or len(segment) < 4 * DECLICK_FADE_MS or not (fade_in or fade_out):
        return segment

    faded = segment
    if fade_in:
        lead_ms = detect_leading_silence(segment, silence_threshold=EDGE_SILENCE_DBFS)
        faded = faded.fade_in(int(max(DECLICK_FADE_MS, min(edge_fade_ms, lead_ms))))
    if fade_out:
        trail_ms = detect_leading_silence(segment.reverse(), silence_threshold=EDGE_SILENCE_DBFS)
        room_at_end = max(trail_ms, int(len(segment) * TAIL_INTO_SPEECH))
        faded = faded.fade_out(int(max(DECLICK_FADE_MS, min(edge_fade_ms, room_at_end))))
    return faded


def atomic_export(segment: AudioSegment, final_path: Path) -> None:
    """Exports to a temp file alongside `final_path`, then atomically renames
    it into place, so a process killed mid-export (Ctrl+C, OOM-kill, crash)
    never leaves a truncated file sitting at `final_path` looking finished -
    a resume check only ever sees either the complete previous file or
    nothing there at all."""
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    segment.export(tmp_path, format="wav")
    tmp_path.replace(final_path)
