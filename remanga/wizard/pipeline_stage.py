"""The pipeline, staged: what this project will run, shown before it runs.

Assembling a pipeline and starting one used to be the same keypress.
Picking the steps opened the ordered checklist, and the moment it closed the
answer was gone: from the main menu it vanished into project.json with a
one-line confirmation, and from `run` it went straight into downloading a
chapter. The list you had just built was never once put in front of you as a
list - which is the one moment worth seeing it, because "download, mark,
crop, package, narration, review, tts, mix, render" is a plan, not a
setting, and the difference between the plan you meant and the plan you
ticked is only visible when it's written out in order.

So the checklist hands back here instead. This screen states the pipeline -
numbered, in order, each step saying what it does - and running it is a
separate row you choose on purpose. Editing the steps re-opens the same
checklist and comes back here, so "change it and look again" is a loop
rather than a walk back through two menus.

Nothing here is a second source of truth: the steps are still
`load_pipeline(project)` (project.json's "pipeline"), still saved by the one
checklist in pipeline_edit.py, and the run itself is still
`run_pipeline` - this screen only decides *when* that happens."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from remanga.config import RemangaConfig, init_config_file
from remanga.console import console, display_path, escape as _esc, print_path
from remanga.paths import CONFIG_PATH
from remanga.tui import Choice, confirm, is_cancel, select
from remanga.wizard.chapters import select_chapter
from remanga.wizard.pipeline_edit import choose_pipeline_steps

_RUN = "__run__"
_EDIT = "__edit__"
_INIT_CONFIG = "__init_config__"


@dataclass
class RunRequest:
    """What the staging screen returns when the user chooses to run: the
    chapter, and the pipeline as it stood at that moment.

    A value rather than a call, because the two callers run it in different
    places - the main menu's Pipeline row runs it right here, while `run`'s
    handler is the one thing that has always started a pipeline and stays
    the one thing that does."""

    chapter: str
    steps: list[str]


def describe_pipeline(steps: list[str]) -> str:
    """The pipeline on one line, for a menu hint."""
    return " → ".join(steps) if steps else "no steps chosen yet"


def print_staged_pipeline(project: str, steps: list[str], *, chapter: str | None = None) -> None:
    """Writes the staged pipeline out in full, above the menu.

    In full, and every time the screen opens: a run order is a sequence, and
    a sequence squeezed onto one hint line as "download → mark → crop → ..."
    is exactly where a step in the wrong place hides. Each line here is the
    position, the step name, and what that step actually does - the same
    description the checklist showed while it was being ticked, so the plan
    reads the same way in the place you build it and the place you approve
    it."""
    from remanga.pipeline import STEP_REGISTRY

    known = {step.name: step for step in STEP_REGISTRY}
    target = f" · chapter {_esc(chapter)}" if chapter else ""
    # highlight=False throughout: Rich's automatic highlighter reads
    # "step(s)" as a function call and a bare "1." as a number, and paints
    # both - which turns a plain plan into a coloured one that looks like it
    # is telling you something it isn't.
    console.print(
        f"\n[bold]Pipeline for '{_esc(project)}'[/] "
        f"[dim]— {len(steps)} step(s), in this order{target}[/]",
        highlight=False,
    )
    width = max((len(name) for name in steps), default=0)
    for position, name in enumerate(steps, start=1):
        step = known.get(name)
        # An unknown name is a step this version no longer has (a project.json
        # written by a newer/older remanga). run_pipeline skips it with a
        # warning rather than aborting, so it's shown here the same way -
        # visible and marked, not silently dropped from the plan on screen.
        detail = step.description if step else "unknown step - it will be skipped"
        label = _esc(name).ljust(width)
        shown = label if step else f"[yellow]{label}[/]"
        console.print(f"  [dim]{position}.[/] {shown}  [dim]{_esc(detail)}[/]", highlight=False)
    console.print()


def init_config_json() -> None:
    """The Init config.json row.

    A fresh clone has no config.json - RemangaConfig.load() falls back to
    config.example.json, so remanga runs fine but this machine has no file
    of its own until something writes one. This writes it, on purpose,
    before a pipeline starts leaning on it.

    On a machine that already has one it becomes a refresh, which is why it
    asks first: re-writing through the current models keeps every answer
    already in the file and fills in the fields a newer version added, but
    "rewrite my configuration" is not something to do to someone silently on
    the way past."""
    existed = CONFIG_PATH.exists()
    if existed and not confirm(
        "Rewrite config.json from the current defaults?",
        default=False,
        note=f"{display_path(CONFIG_PATH, wrap=False)} · keeps every answer already in it and fills "
             "in any setting this version added",
    ):
        return
    written = init_config_file(overwrite=True)
    console.print(
        f"[green]✓ config.json {'refreshed' if existed else 'created'}.[/]"
    )
    print_path(f"  {display_path(written, wrap=False)}")


def stage_pipeline(project: str, config: RemangaConfig, *, chapter: str | None = None,
                   title: str = "") -> RunRequest | None:
    """The staging screen. Returns what to run, or None if the user backed
    out without running.

    `chapter` is passed in by `run`, which has already asked for one; the
    main menu's Pipeline row leaves it out and this screen asks only if and
    when the run is actually wanted - picking the steps for later shouldn't
    have to name a chapter first."""
    from remanga.pipeline import load_pipeline

    while True:
        steps = load_pipeline(project)
        print_staged_pipeline(project, steps, chapter=chapter)

        rows = [
            Choice(label="Run the pipeline", value=_RUN,
                   hint=f"chapter {chapter}" if chapter else "asks which chapter",
                   detail=f"runs these {len(steps)} step(s) in order: {describe_pipeline(steps)}"),
            Choice(label="Choose steps", value=_EDIT, hint=describe_pipeline(steps),
                   detail="the ordered checklist - what runs, and in what order. Saved for this "
                          "project as soon as you confirm it"),
            Choice(label="Init config.json", value=_INIT_CONFIG,
                   badge="" if CONFIG_PATH.exists() else "missing",
                   hint=("this machine's settings file"
                         if CONFIG_PATH.exists() else "this machine doesn't have one yet"),
                   detail="creates config.json from the defaults, or refreshes an existing one "
                          "with any setting a newer version added (it asks first)"),
        ]
        picked = select(
            title or f"Pipeline — {project}", rows, numbered=True, back_label="Back",
            note="the steps above are saved for this project · nothing runs until you say Run",
        )
        if is_cancel(picked):
            return None
        if picked == _EDIT:
            choose_pipeline_steps(project, title=f"Steps for '{project}'")
            continue
        if picked == _INIT_CONFIG:
            init_config_json()
            continue

        target = chapter or select_chapter(project, title="Chapter to run it on")
        if is_cancel(target):
            continue
        # Re-read rather than reusing `steps`: editing the checklist is one
        # of the things that can have happened since it was loaded.
        return RunRequest(chapter=str(target), steps=load_pipeline(project))


def open_pipeline_stage(project: str, config: RemangaConfig) -> Any:
    """The main menu's Pipeline row: stage it, and run it from here when
    that's what's wanted. Loops back to the staging screen afterwards, the
    same way a category menu stays open after running a command - a pipeline
    that stopped at `mark` is usually followed by another one."""
    from remanga.pipeline import run_pipeline

    while True:
        request = stage_pipeline(project, config)
        if request is None:
            return None
        try:
            run_pipeline(project, request.chapter, config, request.steps)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as e:
            console.print(f"[bold red]Pipeline failed:[/] {e}")
