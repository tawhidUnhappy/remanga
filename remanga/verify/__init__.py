"""Integrity verification: strictly checks that every audio/video artifact a
chapter (or a whole project) claims to have is actually complete and
decodable, not just present on disk with a plausible size.

The two spots that can genuinely be left corrupt by a kill at the wrong
instant are the ones this checks hardest: audio/mix.py's master_audio.wav
and video/render.py's final MP4 (ffmpeg writes both in place, with no
atomic temp+rename). Per-panel TTS clips are NOT re-probed one by one:
audio/tts.py's atomic_export guarantees those are either complete or
entirely absent, so a corrupt-but-present clip cannot happen - only a
missing one can, and that's a fast existence check.

    models.py - the result dataclasses
    panels.py - the cheap panels/narration cross-check
    probe.py  - the ffprobe decodability check
    runner.py - verifying a chapter / a project
    report.py - printing results, with the fix for each failure
"""

from __future__ import annotations

from remanga.verify.models import ChapterVerification, MediaCheck
from remanga.verify.panels import check_panel_narration_mismatch, project_panel_narration_mismatches
from remanga.verify.probe import probe_media
from remanga.verify.runner import verify_chapter, verify_project

__all__ = [
    "ChapterVerification",
    "MediaCheck",
    "check_panel_narration_mismatch",
    "probe_media",
    "project_panel_narration_mismatches",
    "verify_chapter",
    "verify_project",
]
