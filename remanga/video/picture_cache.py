"""Whether a chapter's encoded picture stream (picture.mp4) is still what its
timing, frames and video settings would make - so a change to the sound alone
never re-encodes a frame. Mixed into VideoRenderer (render.py)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.json_io import read_json, read_json_or
from remanga.paths import (
    get_audio_timing_path,
    get_video_frames_dir,
    get_video_picture_path,
)
from remanga.video.encoding import (
    PICTURE_FORMAT_VERSION,
)
from remanga.video.frame_timeline import FrameTimeline, build_frame_timeline


class PictureCacheMixin:
    def frame_timeline(self, project_name: str, chapter_num: str) -> FrameTimeline:
        """This chapter's panels on the configured frame grid (video/frame_timeline.py)."""
        panels = read_json(get_audio_timing_path(project_name, chapter_num)).get("panels", [])
        return build_frame_timeline(panels, self.video_config.fps)

    @staticmethod
    def _picture_fingerprint_path(picture: Path) -> Path:
        return picture.with_name(f"{picture.stem}_fingerprint.json")

    def _picture_fingerprint(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> dict[str, Any]:
        """Everything that decides what picture.mp4 contains: the timing it
        was laid out from (audio_timing.json is only rewritten when its
        content changes - see audio/tts.py), every video setting, the encoder,
        and the encode recipe itself."""
        return {
            "format": PICTURE_FORMAT_VERSION,
            "timing_mtime": get_audio_timing_path(project_name, chapter_num).stat().st_mtime,
            "codec": self.encoder()[1],
            "total_frames": timeline.total_frames,
            # The intro is joined after the picture, so it never makes one stale.
            "video": self.video_config.model_dump(exclude={"intro_enabled", "intro_path"}),
        }

    def _picture_is_fresh(self, project_name: str, chapter_num: str, timeline: FrameTimeline) -> bool:
        picture = get_video_picture_path(project_name, chapter_num)
        if not picture.exists() or picture.stat().st_size <= 1000:
            return False
        recorded = read_json_or(self._picture_fingerprint_path(picture), None)
        if recorded != self._picture_fingerprint(project_name, chapter_num, timeline):
            return False
        # A frame composited since - deleted and rebuilt - is a different
        # picture even under identical settings.
        built = picture.stat().st_mtime
        frames = get_video_frames_dir(project_name, chapter_num).glob("frame_*.png")
        return not any(frame.stat().st_mtime > built for frame in frames)
