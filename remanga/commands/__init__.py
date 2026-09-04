"""Every remanga subcommand - what it's called, what it takes, and what it
runs - shared by the argparse CLI and the interactive wizard.

Was one 600-line module holding the dataclasses, twenty handler functions
and the registry itself back to back. Split by role:

    spec.py      - what a Command/Param is, and the argparse glue
    selection.py - parsing chapter selections and wipe keep-lists
    handlers/    - the handlers themselves, grouped the way the wizard
                   groups them (setup / chapter / project / cleanup)
    registry.py  - the ordered list of commands, and their categories

Every name the rest of the codebase imported from the old module is
re-exported here, so `from remanga.commands import COMMAND_REGISTRY` and
friends keep working unchanged."""

from __future__ import annotations

from remanga.commands.registry import (
    CATEGORIES, COMMAND_BY_NAME, COMMAND_REGISTRY, Category, commands_by_category,
)
from remanga.commands.selection import (
    DEFAULT_WIPE_KEEP, parse_chapter_selection, resolve_wipe_keep, split_chapters,
)
from remanga.commands.spec import (
    Command, Param, SetupAction, add_param_to_parser, chapter_param, force_param,
    params_from_namespace, project_param,
)

__all__ = [
    "CATEGORIES",
    "COMMAND_BY_NAME",
    "COMMAND_REGISTRY",
    "Category",
    "Command",
    "DEFAULT_WIPE_KEEP",
    "Param",
    "SetupAction",
    "add_param_to_parser",
    "chapter_param",
    "commands_by_category",
    "force_param",
    "params_from_namespace",
    "parse_chapter_selection",
    "project_param",
    "resolve_wipe_keep",
    "split_chapters",
]
