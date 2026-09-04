"""What a verification produced: one media file's condition, and one
chapter's overall result. Plain dataclasses with an `ok` property each, so
"is this chapter fine?" is a single expression rather than a chain of
conditions repeated at every call site."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class MediaCheck:
    path: Path
    exists: bool = False
    decodable: bool = False
    duration_sec: Optional[float] = None
    has_audio: bool = False
    has_video: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.exists and self.decodable and (self.duration_sec or 0) > 0


@dataclass
class ChapterVerification:
    chapter_num: str
    narration_entries: int = 0
    audio_clips_found: int = 0
    audio_clips_missing: List[str] = field(default_factory=list)
    master_audio: Optional[MediaCheck] = None
    video: Optional[MediaCheck] = None
    duration_mismatch: str = ""
    panel_narration_mismatch: str = ""

    @property
    def ok(self) -> bool:
        return (
            not self.audio_clips_missing
            and (self.master_audio is None or self.master_audio.ok)
            and (self.video is None or self.video.ok)
            and not self.duration_mismatch
            and not self.panel_narration_mismatch
        )


