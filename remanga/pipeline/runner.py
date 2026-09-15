"""Running a pipeline, and reading which one a project has chosen."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import read_json_or
from remanga.paths import get_pipeline_path
from remanga.pipeline.registry import DEFAULT_STEPS, STEP_BY_NAME
from remanga.settings.project_prefs import remembered_pipeline


def run_pipeline(project: str, chapter: str, config: RemangaConfig, steps: list[str] | None = None) -> None:
    """Runs the named steps, in the given order. `steps` defaults to
    DEFAULT_STEPS (today's exact wizard sequence). An unknown step name is
    warned about and skipped, not fatal - a typo in a saved step list
    shouldn't abort every other step in it."""
    step_names = list(steps) if steps is not None else list(DEFAULT_STEPS)
    for name in step_names:
        step = STEP_BY_NAME.get(name)
        if step is None:
            console.print(f"[bold yellow]⚠ Unknown pipeline step '{name}' - skipping.[/]")
            continue
        step.run(project, chapter, config)


def load_pipeline(project: str) -> list[str]:
    """This project's ordered step list: project.json's "pipeline", else a
    legacy pipeline.json if the project still has one, else DEFAULT_STEPS -
    so a project that has never chosen runs today's exact order, unchanged.

    The steps moved into project.json to sit with everything else a project
    remembers (see remanga.settings.project_prefs); the fallback below is what
    keeps a project written by an older version running until its next save
    moves it across."""
    steps = remembered_pipeline(project)
    if steps:
        return steps
    legacy = read_json_or(get_pipeline_path(project), {})
    steps = legacy.get("steps") if isinstance(legacy, dict) else None
    if isinstance(steps, list) and steps:
        return [str(s) for s in steps]
    return list(DEFAULT_STEPS)
