"""audio_timing.json: which clip each panel is, how long it sounds, and the
gap held after it.

Everything downstream lays itself out from this file - the mix concatenates
by it (audio/master.py), the video builds its frame timeline from it, and
both treat its mtime as "did the synthesized audio change", which is why it
is only ever rewritten when its content actually differs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.json_io import read_json_or, write_json


def panel_timing(index: int, panel_id: str, text: str, clip_name: str, *, start_ms: int,
                 duration_ms: int, pause_after_ms: int, clip_start_ms: int = 0,
                 fade_in: bool = True, fade_out: bool = True) -> dict[str, Any]:
    """One panel's row: where it starts, how long it sounds, and how long its
    slot is once the pause after it is counted. Milliseconds are what the
    mix works in; the seconds are there for reading.

    `fade_in`/`fade_out` say whether this panel's edges are real edges. In a
    batched chapter they are not: consecutive panels are slices of one
    generation, already adjacent samples, and fading each one would dip the
    middle of a sentence (audio/clips.py:apply_edge_fades). Written only when
    false, so a per-panel chapter's rows are byte-identical to what they were
    and nothing downstream re-mixes over a key that says what it assumed.

    `clip_start_ms` and `duration_ms` are the part of the clip file that is
    used - the mix takes exactly that slice (audio/clips.py:speech_bounds
    chose it), so the master's length is what this file says it is and the
    video's frame timeline stays in step with the voice. A row from before
    this existed has no `clip_start_ms` and a `duration_ms` covering the whole
    file, which slices to the whole file: older chapters keep playing as they
    were until they are narrated again."""
    end_ms = start_ms + duration_ms
    total_slot_ms = duration_ms + pause_after_ms
    row: dict[str, Any] = {
        "index": index,
        "panel_id": panel_id,
        "text": text,
        "audio_file": clip_name,
        "start_time_ms": start_ms,
        "end_time_ms": end_ms,
        "clip_start_ms": clip_start_ms,
        "duration_ms": duration_ms,
        "pause_after_ms": pause_after_ms,
        "total_slot_ms": total_slot_ms,
        "start_time_sec": round(start_ms / 1000.0, 3),
        "end_time_sec": round(end_ms / 1000.0, 3),
        "total_slot_sec": round(total_slot_ms / 1000.0, 3),
    }
    if not fade_in:
        row["fade_in"] = False
    if not fade_out:
        row["fade_out"] = False
    return row


def write_timing(path: Path, chapter_num: str, panels: list[dict[str, Any]], *, total_ms: int,
                 voice: dict[str, Any] | None,
                 batches: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Writes the manifest, skipping the write entirely when the content is
    identical to what is already there.

    This isn't just tidiness - audio/mix.py treats this file's mtime as "did
    the synthesized audio actually change" to decide whether it needs to
    re-mix (and video/render.py, in turn, treats master_audio.wav's mtime the
    same way to decide whether to re-encode). Rewriting it on every single
    TTS call - even a fully-resumed one where nothing was regenerated - would
    make that staleness check permanently useless: every downstream step
    would think something changed every time, forever re-mixing and
    re-encoding chapters that are actually already done.

    `voice` is written only when there is something to say about it (see
    narration_voice.py): adding it to an untouched older manifest would
    change the file for nothing, and mix and render would take that as new
    audio and redo themselves."""

    document: dict[str, Any] = {
        "chapter": str(chapter_num),
        "total_timeline_ms": total_ms,
        "total_timeline_sec": round(total_ms / 1000.0, 3),
        "panels": panels,
    }
    if voice is not None:
        document["voice"] = voice
    # What each batch was made from, so a re-run can tell "this take is still
    # the one this text asks for" from "this text changed". Absent for a
    # per-panel chapter, which resumes clip by clip instead.
    if batches is not None:
        document["batches"] = batches

    if read_json_or(path, None) != document:
        write_json(path, document)
    return document
