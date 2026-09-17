"""Which voice a chapter's clips are in, and whether that is still the voice
being asked for.

audio_timing.json records the recording the clips beside it were cloned from,
so a resume can tell "these clips are what I would produce now" from "these
clips are another voice" - where resuming would otherwise narrate half a
chapter in a voice nobody asked for."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def narration_voice_identity(recording: Path) -> dict[str, Any]:
    """The recording cloned - by path, and by size and mtime, so replacing the
    file in place counts as a new voice too."""
    stat = recording.stat()
    return {"engine": "chatterbox", "voice": str(recording.resolve()), "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns}


def voice_changed_from(previous_timing: dict[str, Any], identity: dict[str, Any]) -> str | None:
    """The voice the clips on disk are in, when that is not `identity` - None
    when it is, or when there are no clips yet."""
    if not previous_timing:
        return None
    previous = previous_timing.get("voice") or {}
    if previous == identity:
        return None
    if previous.get("voice") == identity["voice"]:
        return f"an earlier version of {Path(identity['voice']).name}"
    return f"{previous.get('engine', 'another engine')}, {Path(str(previous.get('voice', 'another voice'))).name}"
