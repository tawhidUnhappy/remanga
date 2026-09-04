"""Choosing which pipeline steps a project runs, and in what order.

Was a comma-separated list typed from memory and validated against
STEP_REGISTRY; it's an ordered checklist now - check the steps you want, in
the order you want them to run - so an invalid step name or a typo'd order
can't be expressed in the first place.

Saving the step list is all this does - and it is the only thing that saves
one: `run`'s "steps to run" checklist is this same function, so choosing the
steps for a run and defining the project's pipeline are one act with one
stored list behind them, in the one file a project keeps its answers in,
rather than a file of its own plus a remembered last-run list that drift
apart. A one-off subset that shouldn't stick is what
`--steps` on the CLI is for.

This used to also offer "adjust what the crop step generates?" on the way
out, which had outlived itself twice over:
cropping stopped packaging anything when `package` became its own step, and
the formats themselves are picked per chapter by `package` (remembered per
project) with their config.json defaults living in Settings → Vision outputs.
Three doors to one checklist, one of them naming the wrong step."""

from __future__ import annotations

from typing import List, Optional

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.project_prefs import remember_pipeline
from remanga.tui import Choice, is_cancel, multiselect


def choose_pipeline_steps(project_name: str, *, title: str, note: str = "") -> Optional[List[str]]:
    """The ordered checklist, opened on this project's current pipeline and
    saved to the project's own metadata (project.json's "pipeline", alongside
    everything else that project remembers). Returns the chosen steps, or None
    if the user backed out.

    One function for both places that ask: the main menu's Pipeline row, and
    `run`, where picking the steps for this run *is* choosing the pipeline -
    there's one list per project, not a saved one plus a remembered one that
    can disagree about what "the pipeline" means.

    Deferred import of remanga.pipeline (it pulls in the audio/video/webui/
    downloader/cropper modules) keeps that cost paid only when this path is
    actually taken."""
    from remanga.pipeline import STEP_REGISTRY, load_pipeline

    current = load_pipeline(project_name)
    rows = [
        Choice(label=step.name, hint=step.description, value=step.name,
               detail=("needs: " + ", ".join(step.needs)) if step.needs else "",
               checked=step.name in current)
        for step in STEP_REGISTRY
    ]
    # Steps already in the pipeline come first, in their saved order, so the
    # numbering shown on screen opens as the order that's actually saved.
    rows.sort(key=lambda row: current.index(row.value) if row.value in current else len(current))

    picked: List[str] = multiselect(
        title, rows, ordered=True, allow_empty=False,
        note=note or "the number is the run order - check them in the order you want them to run",
    )
    if is_cancel(picked) or not picked:
        return None

    # Only when it actually changed: an unchanged confirm shouldn't rewrite
    # the file, and shouldn't report a save that changed nothing.
    if picked != current:
        remember_pipeline(project_name, picked)
        console.print(f"[green]✓ Pipeline saved:[/] {' → '.join(picked)}")
    return picked


def edit_pipeline_steps(project_name: str, config: RemangaConfig) -> None:
    """The main menu's Pipeline row. `config` is unused - kept so this stays
    callable as (project, config) like every other wizard screen."""
    choose_pipeline_steps(project_name, title=f"Pipeline for '{project_name}'")
