"""Writing a page clip to disk safely."""

from __future__ import annotations

from pathlib import Path

from pydub import AudioSegment


def atomic_export(segment: AudioSegment, final_path: Path) -> None:
    """Exports to a temp file alongside `final_path`, then atomically renames
    it into place, so a process killed mid-export (Ctrl+C, OOM-kill, crash)
    never leaves a truncated file sitting at `final_path` looking finished -
    a resume check only ever sees either the complete previous file or
    nothing there at all."""
    tmp_path = final_path.with_name(final_path.name + ".tmp")
    segment.export(tmp_path, format="wav")
    tmp_path.replace(final_path)
