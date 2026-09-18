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
                 duration_ms: int, pause_after_ms: int) -> dict[str, Any]:
    """One panel's row: where it starts, how long it sounds, and how long its
    slot is once the pause after it is counted. Milliseconds are what the
    mix works in; the seconds are there for reading."""
    end_ms = start_ms + duration_ms
    total_slot_ms = duration_ms + pause_after_ms
    return {
        "index": index,
        "panel_id": panel_id,
        "text": text,
        "audio_file": clip_name,
        "start_time_ms": start_ms,
        "end_time_ms": end_ms,
        "duration_ms": duration_ms,
        "pause_after_ms": pause_after_ms,
        "total_slot_ms": total_slot_ms,
        "start_time_sec": round(start_ms / 1000.0, 3),
        "end_time_sec": round(end_ms / 1000.0, 3),
        "total_slot_sec": round(total_slot_ms / 1000.0, 3),
    }


def write_timing(path: Path, chapter_num: str, panels: list[dict[str, Any]], *, boost_db: float,
                 total_ms: int, voice: dict[str, Any] | None) -> dict[str, Any]:
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
    audio and redo themselves.

    `boost_db` is what is actually baked into the clips this file describes,
    read back at the top of the next run to work out the difference. It also
    earns its keep in the staleness chain above: a changed boost changes this
    file, so mix and render both notice and redo themselves, which is what
    makes turning that knob reach the finished video with no extra flag."""
    document: dict[str, Any] = {
        "chapter": str(chapter_num),
        "volume_boost_db": boost_db,
        "total_timeline_ms": total_ms,
        "total_timeline_sec": round(total_ms / 1000.0, 3),
        "panels": panels,
    }
    if voice is not None:
        document["voice"] = voice

    if read_json_or(path, None) != document:
        write_json(path, document)
    return document
