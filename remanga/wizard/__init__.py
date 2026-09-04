"""The interactive wizard - project/chapter discovery and every command
remanga has, driven by arrow-key menus.

Was one 400-line module mixing the menu loop, the project/chapter pickers,
per-parameter prompting, and both LLM hand-off steps. Split by what each
piece is for:

    app.py           - the menus and the session loop
    projects.py      - picking/creating a project, reading direction
    chapters.py      - picking one chapter, or several
    params.py        - prompting for a command's parameters
    pipeline_edit.py - which steps run, and in what order
    narration.py     - the narration-generation hand-off
    review.py        - the review-round loop
    uploads.py       - what this chapter has that can be uploaded
    handoff.py       - printing an LLM hand-off (shared by both steps)
    checks.py        - the automatic panel/narration sanity check

`run_narration_step` and `run_narration_review_loop` are re-exported because
remanga.pipeline's narration/review steps and the `review` command call them
by that name."""

from __future__ import annotations

from remanga.wizard.app import run_interactive_pipeline
from remanga.wizard.narration import run_narration_step
from remanga.wizard.pipeline_edit import edit_pipeline_steps
from remanga.wizard.review import run_narration_review_loop

__all__ = [
    "edit_pipeline_steps",
    "run_interactive_pipeline",
    "run_narration_review_loop",
    "run_narration_step",
]
