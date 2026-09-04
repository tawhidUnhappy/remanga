"""What a remanga subcommand *is*: its name, help text, parameters, the
handler that runs it, and which menu category it belongs to.

One description, two front-ends. remanga/cli.py builds its argparse
subparsers by walking the registry built from these, and the interactive
wizard builds its menus from the same list - so `remanga <cmd> --help` and
the wizard can't offer different flags, different defaults or different
commands to each other, which is exactly what two hand-maintained lists
used to do."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from remanga.config import RemangaConfig


@dataclass
class Param:
    """One argparse argument for a Command.

    `name` doubles as the argparse dest, so it MUST match what argparse
    infers from `flags`' first long option (flags=["--no-rejoin"] ->
    name="no_rejoin"). `type` is "str", "bool" (store_true), or "choice"
    (str + `choices`)."""

    name: str
    flags: List[str]
    type: str = "str"
    required: bool = False
    default: Any = None
    choices: Optional[List[str]] = None
    help: str = ""
    # Short label for the interactive prompt. `help` is written for
    # `--help` output and is often a paragraph; a menu needs a line.
    prompt: str = ""
    # For a "choice" param: what each individual choice means, so the wizard
    # can show a described menu instead of a list of bare words. Keyed by
    # choice value; `choice_help` is the one-line hint on every row,
    # `choice_detail` the longer text shown under the highlighted one. Both
    # are filled from whatever module owns those choices (restart modes from
    # remanga.reset, narration file modes from remanga.narration), so the
    # descriptions live with the behavior rather than being retyped here.
    choice_help: Dict[str, str] = field(default_factory=dict)
    choice_detail: Dict[str, str] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return self.prompt or self.help or self.name


@dataclass(frozen=True)
class SetupAction:
    """One row in a command's setup submenu: a setting that command runs on,
    editable right where you are about to use it.

    `describe` renders the setting's current value as the row's hint - the
    same "a menu that doubles as the status screen" idea remanga.settings.
    sections is built on, so `tts` says which engine and which voice clip it
    would use before you run it. `run` opens whatever screen changes it, and
    `relevant` hides a row that means nothing under the current settings (the
    reference transcript, for an engine that clones from audio alone)."""

    label: str
    describe: Callable[[RemangaConfig], str]
    run: Callable[[RemangaConfig], None]
    detail: str = ""
    relevant: Callable[[RemangaConfig], bool] = lambda config: True


@dataclass
class Command:
    name: str
    help: str
    handler: Callable[[Dict[str, Any], RemangaConfig], None]
    params: List[Param] = field(default_factory=list)
    # Grouping hint for the wizard's menus (see remanga.commands.registry's
    # CATEGORIES). argparse ignores it entirely, so it can never make the
    # CLI and the wizard disagree about anything that matters.
    category: str = "General"
    # One line on what running this actually does to the project, shown
    # under the highlighted row in the wizard. `help` goes to --help.
    detail: str = ""
    # Settings this command runs on. When there are any, the wizard opens a
    # submenu - run the command, or change one of the settings first - rather
    # than going straight into the command's parameters, so "synthesize this
    # chapter" and "which voice/engine synthesizes it" are one stop instead of
    # a command in one menu and a settings screen three menus away. argparse
    # ignores this completely (each setting already has its own screen under
    # `setup-config`), so it can't make the CLI and the wizard disagree about
    # what the *command* does.
    setup: Tuple[SetupAction, ...] = ()


def add_param_to_parser(parser, param: Param) -> None:
    """Adds one Param to an argparse (sub)parser exactly the way the
    hand-written add_argument() calls used to, so --help output stays
    byte-identical."""
    kwargs: Dict[str, Any] = {"help": param.help}
    if param.type == "bool":
        kwargs["action"] = "store_true"
    else:
        if param.choices:
            kwargs["choices"] = param.choices
        kwargs["required"] = param.required
        kwargs["default"] = param.default
    parser.add_argument(*param.flags, **kwargs)


def params_from_namespace(cmd: Command, ns) -> Dict[str, Any]:
    """Pulls this command's own params out of an argparse Namespace (or
    anything with matching attributes) into a plain dict keyed by param
    name."""
    return {p.name: getattr(ns, p.name, p.default) for p in cmd.params}


def project_param(help_: str = "Project name") -> Param:
    return Param("project", ["--project", "-p"], required=True, help=help_, prompt="Project")


def chapter_param(help_: str = "Chapter number") -> Param:
    return Param("chapter", ["--chapter", "-c"], required=True, help=help_, prompt="Chapter")


def force_param(help_: str = "Skip the confirmation prompt") -> Param:
    return Param("force", ["--force", "-f"], type="bool", default=False, help=help_, prompt=help_)
