"""The llm-crop pipeline step - the Gemini alternative to `mark`."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import has_real_json_content
from remanga.paths import get_chapter_dir
from remanga.pipeline.spec import Step


def run_llm_crop(project: str, chapter: str, config: RemangaConfig) -> None:
    """Like the mark step, a no-op for a chapter whose crops.json already has
    marks in it: re-running a pipeline must not re-import a reply, or offer
    to replace hand-made marks, uninvited. The `llm-crop` command is the way
    to do either on purpose."""
    if has_real_json_content(get_chapter_dir(project, chapter) / "crops.json"):
        return
    from remanga.extensions.llm_crop.handoff import run_llm_crop_step

    console.print("\n[bold]Step — Cropping with Gemini[/]")
    run_llm_crop_step(project, chapter, config)


LLM_CROP_STEP = Step(
    "llm-crop",
    "Crop with Gemini instead of marking: gridded pages to upload, its pasted reply becomes crops.json",
    run_llm_crop, needs=["download"],
)
