"""What happens to one synthesized panel clip between the engine and disk.

The edge fades and the atomic write - what every clip goes through once the
synthesizer hands it back, and neither of which has anything to do with
walking a chapter's narration or building its timing manifest. Kept together
here, audio/tts.py is left doing the one job its name claims: turning a
narration script into a chapter of audio."""

from __future__ import annotations

from pathlib import Path

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

# What counts as silence when measuring how much room a clip has at its
# edges. Well below speech but above the synthesizer's noise floor, so a
# near-silent lead-in still reads as silence to fade over.
EDGE_SILENCE_DBFS = -50.0


def apply_edge_fades(segment: AudioSegment, edge_fade_ms: int) -> AudioSegment:
    """De-clicks a clip's edges without ever ramping its speech.

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
    if edge_fade_ms <= 0 or len(segment) < 4 * DECLICK_FADE_MS:
        return segment

    lead_ms = detect_leading_silence(segment, silence_threshold=EDGE_SILENCE_DBFS)
    trail_ms = detect_leading_silence(segment.reverse(), silence_threshold=EDGE_SILENCE_DBFS)

    fade_in_ms = max(DECLICK_FADE_MS, min(edge_fade_ms, lead_ms))
    room_at_end = max(trail_ms, int(len(segment) * TAIL_INTO_SPEECH))
    fade_out_ms = max(DECLICK_FADE_MS, min(edge_fade_ms, room_at_end))
    return segment.fade_in(int(fade_in_ms)).fade_out(int(fade_out_ms))


def atomic_export(segment: AudioSegment, final_path: Path) -> None:
    """Exports to a temp file alongside `final_path`, then atomically renames
    it into place, so a process killed mid-export (Ctrl+C, OOM-kill, crash)
    never leaves a truncated file sitting at `final_path` looking finished -
    a resume check only ever sees either the complete previous file or
    nothing there at all."""
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    segment.export(tmp_path, format="wav")
    tmp_path.replace(final_path)
