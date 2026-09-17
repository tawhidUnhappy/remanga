"""Where each page's picture starts and stops, in whole frames.

A recap is a slideshow: nothing moves between cuts, so all a frame does is
say which picture is up, and the frame rate only sets how finely a cut can
be placed. That is what makes a low rate safe - provided every cut lands
somewhere nobody can tell. There is such a place: every page's slot ends
with the pause between pages (audio.pause_between_pages_ms, 350ms by default)
before the next line starts. So each cut is snapped onto the LAST frame
boundary inside that silence, and a new picture always appears just before
its line - never partway through the previous one.

With a 350ms pause, any rate above ~3fps has a boundary inside every pause.
Measured at 5fps, a real 71-picture chapter put 70 of its 70 cuts inside the
pause, each picture leading its voice by 0-175ms; at the 24fps default a
frame is 42ms, so the same cuts land inside the same silence with room to
spare. A pause shorter than one frame falls back to the nearest boundary -
never worse than rounding.

Integer milliseconds throughout, so a chapter's frame count is exact rather
than a float sum that drifts by a frame over a long chapter."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class FrameSlot:
    page_id: str
    first_frame: int
    frame_count: int


@dataclass(frozen=True)
class FrameTimeline:
    fps: int
    slots: tuple[FrameSlot, ...]
    total_frames: int

    @property
    def duration_sec(self) -> float:
        """How long the picture runs. Whole frames, so it is never shorter
        than the narration it was laid out from, and at most one frame
        longer."""
        return self.total_frames / self.fps

    def keyframe_times(self) -> str:
        """-force_key_frames' time list: a keyframe on the first frame of
        every page after the first (frame 0 always is one). A quarter-frame
        early, because ffmpeg keys the first frame AT OR AFTER each time, and
        a time exactly on a boundary can round to either side of it."""
        return ",".join(f"{(slot.first_frame - 0.25) / self.fps:.4f}" for slot in self.slots[1:])

    def write_concat_list(self, path: Path, frames_dir: Path) -> None:
        """The concat-demuxer script playing each page's frame for exactly
        its slot. The last file is listed again with no duration, the usual
        concat idiom for stills - the demuxer stretches that trailing entry,
        which is why the encode caps the stream at total_frames (see
        video/encoding.py)."""
        lines: list[str] = []
        for slot in self.slots:
            lines += [f"file '{concat_quote(frames_dir / f'frame_{slot.page_id}.png')}'",
                      f"duration {slot.frame_count / self.fps:.6f}"]
        if self.slots:
            lines.append(f"file '{concat_quote(frames_dir / f'frame_{self.slots[-1].page_id}.png')}'")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def concat_quote(path: Path) -> str:
    """A path for inside the concat script's single quotes, where a literal
    quote has to end the string, be escaped, and start it again - a manga
    title with an apostrophe in it would otherwise break the script."""
    return str(path.resolve()).replace("'", "'\\''")


def _ms(page: dict[str, Any], name: str) -> int | None:
    """`{name}_ms`, else `{name}_sec` in milliseconds, else None."""
    if page.get(f"{name}_ms") is not None:
        return int(page[f"{name}_ms"])
    if page.get(f"{name}_sec") is not None:
        return round(float(page[f"{name}_sec"]) * 1000)
    return None


def build_frame_timeline(pages: list[dict[str, Any]], fps: int) -> FrameTimeline:
    """audio_timing.json's pages laid out on an `fps` frame grid."""
    if fps < 1:
        raise ValueError(f"video.fps must be at least 1, got {fps}")

    # (page_id, slot start, end of its voice) - the voice runs from the
    # slot's start for duration_ms, and the rest of the slot is its pause.
    spans: list[tuple[str, int, int]] = []
    position = 0
    for page in pages:
        slot = _ms(page, "total_slot") or 0
        voice = _ms(page, "duration")
        spans.append((page["page_id"], position, position + min(slot, slot if voice is None else voice)))
        position += slot
    if not spans:
        return FrameTimeline(fps=fps, slots=(), total_frames=0)

    cuts = [0]
    for (_, _, previous_voice_end), (_, start, _) in pairwise(spans):
        latest = start * fps // 1000                   # last boundary at or before this line starts
        earliest = -(-previous_voice_end * fps // 1000)  # first boundary at or after the last line ends
        cut = latest if earliest <= latest else (start * fps + 500) // 1000
        cuts.append(max(cut, cuts[-1] + 1))  # every page keeps at least one frame

    total_frames = max(-(-position * fps // 1000), cuts[-1] + 1)
    ends = [*cuts[1:], total_frames]
    slots = tuple(
        FrameSlot(page_id=page_id, first_frame=first, frame_count=end - first)
        for (page_id, _, _), first, end in zip(spans, cuts, ends, strict=True)
    )
    return FrameTimeline(fps=fps, slots=slots, total_frames=total_frames)
