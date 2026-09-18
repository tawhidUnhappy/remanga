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

    `edge_fade_ms` is a ceiling, not a fixed length: each edge is faded over
    at most the silence that edge actually has, so the fade shapes the
    clip's own lead-in and tail rather than its first and last phonemes.
    That distinction is the whole point. A TTS engine returns audio that
    starts within a few milliseconds of the first phoneme, so applying the
    configured 35ms flat - as this used to - ramped the opening consonant
    itself: across a finished chapter the first 35ms of 52 of 60 clips
    came back ~36x quieter than the speech immediately following it, which
    is what swallowed the start of nearly every line."""
    if edge_fade_ms <= 0 or len(segment) < 4 * DECLICK_FADE_MS:
        return segment

    lead_ms = detect_leading_silence(segment, silence_threshold=EDGE_SILENCE_DBFS)
    trail_ms = detect_leading_silence(segment.reverse(), silence_threshold=EDGE_SILENCE_DBFS)

    fade_in_ms = max(DECLICK_FADE_MS, min(edge_fade_ms, lead_ms))
    fade_out_ms = max(DECLICK_FADE_MS, min(edge_fade_ms, trail_ms))
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
