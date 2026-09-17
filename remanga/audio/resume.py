"""Where a previous synthesis run stopped, and which of its clips not to
trust.

Exports are atomic (see clips.atomic_export), so a kill mid-write can no
longer leave a truncated file sitting at the final path looking finished -
but a clip written by an older run, from before that, still could. Rather
than trust the last couple of clips right at the resume point, they are
regenerated: the two pages either side of a Ctrl+C are exactly where a
corrupt-but-present WAV would hide."""

from __future__ import annotations

from pathlib import Path

# A clip smaller than this is not audio, whatever the filesystem says - a
# zero-length or half-written file from an interrupted export.
MIN_CLIP_BYTES = 1000


def clip_is_complete(audio_dir: Path, page_id: str) -> bool:
    """Whether this page has a finished clip on disk from an earlier run."""
    clip = audio_dir / f"{page_id}.wav"
    return clip.exists() and clip.stat().st_size > MIN_CLIP_BYTES


def clips_to_redo(audio_dir: Path, page_ids: list[str]) -> set:
    """The pages around where the previous run stopped - the first page
    with no complete clip, and the two before it - which are re-synthesized
    rather than resumed. Empty when nothing was left to do, or when nothing
    had been done at all (there is no stopping point to distrust)."""
    resume_at = next((i for i, pid in enumerate(page_ids) if not clip_is_complete(audio_dir, pid)), len(page_ids))
    if not 0 < resume_at < len(page_ids):
        return set()
    return set(page_ids[max(0, resume_at - 2):resume_at + 1])
