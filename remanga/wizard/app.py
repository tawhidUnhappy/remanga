"""The interactive wizard: pick a project, then work through it.

Two levels, both generated from the command registry - a category, then a
command inside it - so every command remanga has is reachable here the
moment it's registered, described the same way `--help` describes it, and
prompted for according to its own parameter specs. The main menu also finds
any command by name: type "crop-all" and it's the highlighted row, Enter
runs it - the categories are there for browsing, not a path you have to
walk. A command that declares settings of its own (`Command.setup`) opens
one more level: run it, or change what it runs with. The Pipeline row is
the pipeline's staging screen (see wizard/pipeline_stage.py).

Every menu reopens on what was last picked in it (see wizard/session.py),
and everything is escapable: Esc or ← backs out one level from anywhere,
Ctrl+C while answering a command's questions cancels that command, and
ctrl+q quits from any depth."""

from __future__ import annotations

from typing import Any

from remanga.commands import Command, commands_by_category
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.tui import Choice, is_cancel, select
from remanga.wizard.checks import warn_panel_narration_mismatches
from remanga.wizard.params import collect_params
from remanga.wizard.pipeline_stage import describe_pipeline, open_pipeline_stage
from remanga.wizard.projects import select_or_create_project
from remanga.wizard.session import Session, keep_going

_PIPELINE = "__pipeline__"
_SWITCH_PROJECT = "__switch__"
_RUN = "__run__"
_MAIN = "main"


def _command_row(cmd: Command, *, hint: str | None = None, hidden: bool = False) -> Choice:
    return Choice(label=cmd.name, hint=cmd.summary if hint is None else hint,
                  detail=cmd.detail or cmd.help, value=cmd, hidden=hidden)


def run_command(cmd: Command, session: Session) -> None:
    """Asks for this command's parameters and runs it. Ctrl+C at any of its
    questions - the wizard's or the command's own - cancels it, and a failure
    is reported; either way this returns to the menu it was run from (see
    keep_going). Ctrl+C once it's working stops remanga, as it always has: a
    stopped download or TTS run is left for its own resume logic, and a web
    UI or worker process is released on the way out rather than left holding
    a port or the GPU."""
    with keep_going(cmd.name):
        params = collect_params(cmd, session)
        if params is not None:
            cmd.handler(params, session.config)


def open_command(cmd: Command, session: Session) -> None:
    """Runs a command, by way of its settings menu when it has one."""
    if not cmd.setup:
        run_command(cmd, session)
        return
    # A command with settings of its own: run it, or change one of them
    # first. "Synthesize this chapter" and "which voice synthesizes it" are
    # the same moment - you notice the wrong voice while looking at the
    # command that uses it. Numbered, because it's short and fixed: 1 runs.
    while True:
        rows = [Choice(label=f"Run {cmd.name}", hint=cmd.summary, detail=cmd.detail or cmd.help, value=_RUN)]
        rows += [
            Choice(label=action.label, hint=str(action.describe(session.config)),
                   detail=action.detail, value=action)
            for action in cmd.setup if action.relevant(session.config)
        ]
        scope = f" · saved for {session.project}"
        picked = select(cmd.name, rows, numbered=True, back_label="Back",
                        note=f"{cmd.summary} · or change what it runs with{scope}")
        if is_cancel(picked):
            return
        if picked is _RUN:
            run_command(cmd, session)
        else:
            with keep_going(picked.label):
                picked.run(session.config)


def run_category_menu(category, commands: list[Command], session: Session) -> None:
    """One category's commands. Stays open after running one, on the command
    just run, so several commands in a row (mark, then crop, then write)
    don't mean re-picking the category each time."""
    key = f"category:{category.name}"
    while True:
        picked = select(category.name, [_command_row(cmd) for cmd in commands],
                        note=category.description, back_label="Back", default=session.last.get(key))
        if is_cancel(picked):
            return
        session.last[key] = picked
        open_command(picked, session)


def main_menu(session: Session) -> Any:
    """The categories, the Pipeline row and Switch project - plus every
    command as a hidden row, so typing a command's name finds it from here."""
    from remanga.pipeline import load_pipeline

    groups = commands_by_category()
    rows = [
        Choice(label=category.name, hint=category.description,
               detail=", ".join(cmd.name for cmd in cmds), value=category)
        for category, cmds in groups.items()
    ]
    rows.append(Choice(label="Pipeline", hint=describe_pipeline(load_pipeline(session.project)),
                       detail="set up the steps this project runs and in what order, look at them, "
                              "then run them",
                       value=_PIPELINE))
    rows.append(Choice(label="Switch project", hint=f"currently: {session.project}", value=_SWITCH_PROJECT))
    rows += [
        _command_row(cmd, hint=f"{category.name} · {cmd.summary}", hidden=True)
        for category, cmds in groups.items() for cmd in cmds
    ]

    picked = select(
        f"remanga — {session.project}", rows, default=session.last.get(_MAIN),
        note="type a command's name to jump straight to it",
        # One way out at the top, not two: "Quit" and "Exit remanga" both
        # ended the session.
        back_label="Quit", exit_label=None,
    )
    if is_cancel(picked):
        return None
    if not isinstance(picked, Command):
        session.last[_MAIN] = picked
    if picked in (_PIPELINE, _SWITCH_PROJECT) or isinstance(picked, Command):
        return picked
    return (picked, groups[picked])


def _open_session(machine_config: RemangaConfig, project: str) -> Session:
    # From here on everything runs on this manga's own settings (see
    # RemangaConfig.for_project), and saving a setting writes it back to
    # this project rather than to every project on the machine.
    warn_panel_narration_mismatches(project)
    return Session(machine_config, project)


def run_interactive_pipeline() -> None:
    console.print("[bold]remanga[/] [dim]— interactive recap production[/]")

    machine_config = RemangaConfig.load()
    project = select_or_create_project(machine_config)
    if is_cancel(project):
        return
    session = _open_session(machine_config, project)

    while True:
        # Ctrl+C here, at the top, leaves remanga; anywhere below it only
        # backs out to here (see keep_going).
        action = main_menu(session)
        if action is None:
            return
        if action == _SWITCH_PROJECT:
            with keep_going("Switch project"):
                switched = select_or_create_project(machine_config, switching=True)
                if not is_cancel(switched):
                    session = _open_session(machine_config, switched)
        elif action == _PIPELINE:
            with keep_going("Pipeline"):
                open_pipeline_stage(session.project, session.config)
        elif isinstance(action, Command):
            with keep_going(action.name):
                open_command(action, session)
        else:
            category, commands = action
            with keep_going(category.name):
                run_category_menu(category, commands, session)
