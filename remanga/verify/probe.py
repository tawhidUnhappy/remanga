"""Deciding whether a media file is actually complete, via ffprobe.

Most of the pipeline's resume checks are deliberately cheap (file exists,
size > 1000 bytes) - fine for skipping expensive work, useless as an
integrity guarantee. This is the expensive check: a truncated file from a
kill mid-write fails here even though existence and size both pass it."""

from __future__ import annotations

import json
from pathlib import Path

from remanga.ffmpeg_io import run_ffmpeg
from remanga.verify.models import MediaCheck


def probe_media(path: Path) -> MediaCheck:
    """Runs ffprobe on `path` and reports whether it's actually a complete,
    decodable media file - not just a file that exists. A truncated/corrupt
    file from a kill mid-write fails this even though `.exists()` and a
    size check would both pass it."""
    check = MediaCheck(path=path)
    if not path.exists() or path.stat().st_size == 0:
        check.error = "missing or empty"
        return check
    check.exists = True

    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration:stream=codec_type",
        "-of", "json", str(path),
    ]
    result = run_ffmpeg(cmd, capture=True)
    if result.returncode != 0:
        check.error = (result.stderr or "ffprobe failed").strip().splitlines()[-1][:200]
        return check

    try:
        data = json.loads(result.stdout or "{}")
    except Exception as e:
        check.error = f"unreadable ffprobe output: {e}"
        return check

    streams = data.get("streams", [])
    types = {s.get("codec_type") for s in streams}
    check.has_audio = "audio" in types
    check.has_video = "video" in types

    try:
        duration = float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    check.duration_sec = duration

    if not streams:
        check.error = "no decodable streams (likely truncated)"
        return check
    if duration <= 0:
        check.error = "zero/unreadable duration (likely truncated)"
        return check

    check.decodable = True
    return check


