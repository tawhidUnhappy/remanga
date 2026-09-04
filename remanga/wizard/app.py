"""The interactive wizard: pick a project, then work through it.

Two levels, both generated from the command registry - a category, then a
command inside it - so every command remanga has is reachable here the
moment it's registered, described the same way `--help` describes it, and
prompted for according to its own parameter specs. A command that declares
settings of its own (`Command.setup`, currently `tts`) opens one more level:
run it, or change the engine/voice/language it would run with. There are no fixed
"modes": chaining work (mark, then crop, then write) is picking commands one
after another, and the pipeline runner is itself just a command.

Everything here is escapable. Esc (or the Back row) backs out one level from
anywhere, including out of a half-answered command, which then doesn't
run."""

from __future__ import annotations

from typing import Any, List

from remanga.commands import Command, SetupAction, commands_by_category
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.tui import Choice, is_cancel, select
from remanga.wizard.checks import warn_panel_narration_mismatches
from remanga.wizard.params import collect_params
from remanga.wizard.pipeline_edit import edit_pipeline_steps
from remanga.wizard.projects import select_or_create_project

_PIPELINE = "__pipeline__"
_SWITCH_PROJECT = "__switch__"
_RUN = "__run__"
_HINT_LIMIT = 72


def _short(text: str) -> str:
    """First sentence of a help string, for a one-line menu hint. The full
    text still shows as the highlighted row's detail."""
    first = text.split(" - ")[0].split(". ")[0].strip()
    return first if len(first) <= _HINT_LIMIT else first[:_HINT_LIMIT - 1] + "…"


def _command_rows(commands: List[Command]) -> List[Choice]:
    return [
        Choice(label=cmd.name, hint=_short(cmd.help), detail=cmd.detail or cmd.help, value=cmd)
        for cmd in commands
    ]


def _pipeline_hint(project: str) -> str:
    from remanga.pipeline import load_pipeline

    return " → ".join(load_pipeline(project))


def run_command(cmd: Command, project: str, config: RemangaConfig) -> None:
    """Prompts for this command's parameters and runs it. A failure is
    reported and returns to the menu - one command failing (a network blip
    mid-download, a chapter that isn't cropped yet) shouldn't end the
    session and lose the project/chapter context with it."""
    params = collect_params(cmd, project, config)
    if params is None:
        return
    try:
        cmd.handler(params, config)
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as e:
        console.print(f"[bold red]{cmd.name} failed:[/] {e}")


def run_command_menu(cmd: Command, project: str, config: RemangaConfig) -> None:
    """A command that has settings of its own (`Command.setup`): run it, or
    change one of those settings first.

    The point is that "synthesize this chapter" and "which voice and engine
    synthesize it" are the same moment - you notice the wrong voice while
    looking at the command that uses it, not while walking through
    `setup-config`. Every row shows what that setting is right now, and opens
    the same screen the settings menu opens; nothing is answered twice.

    Numbered, because it's short and fixed: 1 runs the command, the rest are
    its settings."""
    while True:
        actions = [action for action in cmd.setup if action.relevant(config)]
        rows = [Choice(label=f"Run {cmd.name}", hint=_short(cmd.help),
                       detail=cmd.detail or cmd.help, value=_RUN)]
        rows += [
            Choice(label=action.label, hint=str(action.describe(config)),
                   detail=action.detail, value=action)
            for action in actions
        ]
        scope = f" · saved for {config.project}" if config.project else ""
        picked = select(
            cmd.name, rows, numbered=True, back_label="Back",
            note=f"{_short(cmd.help)} · or change what it runs with{scope}",
        )
        if is_cancel(picked):
            return
        if picked is _RUN:
            run_command(cmd, project, config)
        else:
            picked.run(config)


def run_category_menu(category, commands: List[Command], project: str, config: RemangaConfig) -> None:
    """One category's commands. Stays open after running one, so several
    commands from the same category (mark, then crop, then write) don't mean
    re-picking the category each time."""
    while True:
        picked = select(
            f"{category.name}", _command_rows(commands),
            note=category.description, back_label="Back",
        )
        if is_cancel(picked):
            return
        if picked.setup:
            run_command_menu(picked, project, config)
        else:
            run_command(picked, project, config)


def main_menu(project: str, config: RemangaConfig) -> Any:
    groups = commands_by_category()
    rows = [
        Choice(label=category.name, hint=category.description,
               detail=", ".join(cmd.name for cmd in cmds), value=category)
        for category, cmds in groups.items()
    ]
    rows.append(Choice(label="Pipeline", hint=_pipeline_hint(project),
                       detail="which steps `run` executes for this project, and in what order",
                       value=_PIPELINE))
    rows.append(Choice(label="Switch project", hint=f"currently: {project}", value=_SWITCH_PROJECT))

    picked = select(f"remanga — {project}", rows, back_label="Quit")
    if is_cancel(picked):
        return None
    if picked in (_PIPELINE, _SWITCH_PROJECT):
        return picked
    return (picked, groups[picked])


def run_interactive_pipeline() -> None:
    console.print("[bold]remanga[/] [dim]— interactive recap production[/]")

    machine_config = RemangaConfig.load()
    project = select_or_create_project(machine_config)
    if is_cancel(project):
        return
    # From here on the session runs on this manga's own settings (see
    # RemangaConfig.for_project): every command, every menu and every settings
    # screen sees what this project uses, and saving one writes it back to
    # this project rather than to every project on the machine.
    config = machine_config.for_project(project)
    warn_panel_narration_mismatches(project)

    while True:
        action = main_menu(project, config)
        if action is None:
            return
        if action == _SWITCH_PROJECT:
            switched = select_or_create_project(machine_config)
            if not is_cancel(switched):
                project = switched
                config = machine_config.for_project(project)
                warn_panel_narration_mismatches(project)
            continue
        if action == _PIPELINE:
            edit_pipeline_steps(project, config)
            continue
        category, commands = action
        run_category_menu(category, commands, project, config)
