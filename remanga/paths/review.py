"""Narration-review-round files: narration_review.json (the live/current
round) and its per-round archive - see remanga/webui/reviewer_*.py, which
write these."""

from __future__ import annotations

from pathlib import Path

from .projects import get_chapter_dir


def get_narration_review_path(project_name: str, chapter_num: str) -> Path:
    """The current review round's output, in the chapter's source folder
    right next to narration.json - written by the Narration Reviewer web UI
    (remanga/webui/reviewer_*.py), read by the user to hand to the LLM for a
    fix pass. Blanked (not deleted) once its round has been submitted, same
    convention as narration.json's own placeholder (json_io.has_real_json_content)."""
    return get_chapter_dir(project_name, chapter_num) / "narration_review.json"


def get_narration_review_history_dir(project_name: str, chapter_num: str, create: bool = True) -> Path:
    """Every past round's narration_review.json gets archived here as
    round_<n>.json before the live file is blanked for the next round - so a
    chapter's whole review history survives even though only the latest
    round is ever the "live" narration_review.json."""
    d = get_chapter_dir(project_name, chapter_num) / "narration_reviews"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d
