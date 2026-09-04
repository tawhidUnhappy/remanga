"""Editing which pipeline steps a project runs, and in what order.

Was a comma-separated list typed from memory and validated against
STEP_REGISTRY; it's an ordered checklist now - check the steps you want, in
the order you want them to run - so an invalid step name or a typo'd order
can't be expressed in the first place."""

from __future__ import annotations

from typing import List

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.json_io import write_json
from remanga.paths import get_pipeline_path
from remanga.settings import configure_vision_outputs, package_summary
from remanga.tui import Choice, confirm, is_cancel, multiselect


def edit_pipeline_steps(project_name: str, config: RemangaConfig) -> None:
    """Redefines projects/<name>/pipeline.json. Deferred import of
    remanga.pipeline (it pulls in the audio/video/webui/downloader/cropper
    modules) keeps that cost paid only when this path is actually taken."""
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
        f"Pipeline for '{project_name}'", rows, ordered=True, allow_empty=False,
        note="the number is the run order - check them in the order you want them to run",
    )
    if is_cancel(picked) or not picked:
        return

    write_json(get_pipeline_path(project_name), {"steps": picked})
    console.print(f"[green]✓ Pipeline saved:[/] {' → '.join(picked)}")

    # Adjusting the pipeline and adjusting what its crop step actually
    # produces are one stop rather than two (the same checklist stays
    # reachable on its own from Settings).
    if "crop" in picked:
        console.print(f"[dim]crop currently also generates:[/] {package_summary(config.cropper.package)}")
        if confirm("Adjust what the crop step generates?", default=False):
            configure_vision_outputs(config)
