"""The one list of every remanga subcommand, assembled from the catalog.

Adding a command means adding one entry to the catalog module for its
category (remanga/commands/catalog/) - it then appears in `remanga --help`,
gets its flags parsed, and shows up in the interactive wizard's menu under
that category with its parameters prompted for according to their own specs.
Nothing else has to be edited anywhere, including this file.

`interactive` is deliberately NOT in this registry - it's the thing that
displays this menu, so listing it inside itself would be circular."""

from __future__ import annotations

from remanga.commands.catalog import CHAPTER_COMMANDS, PROJECT_COMMANDS, SETUP_COMMANDS
from remanga.commands.categories import CATEGORIES, Category
from remanga.commands.spec import Command
from remanga.extensions import load_extensions, place

# Category order is menu order and --help order (see catalog/__init__), with
# every extension's commands placed among the catalog's (remanga.extensions).
COMMAND_REGISTRY: list[Command] = place(
    [*SETUP_COMMANDS, *CHAPTER_COMMANDS, *PROJECT_COMMANDS],
    [placed for extension in load_extensions() if extension.commands for placed in extension.commands()],
    lambda cmd: cmd.name,
)

COMMAND_BY_NAME: dict[str, Command] = {cmd.name: cmd for cmd in COMMAND_REGISTRY}

def commands_by_category() -> dict[Category, list[Command]]:
    """Groups the registry by category, in CATEGORIES order. A command whose
    category isn't in CATEGORIES still gets a group of its own at the end
    rather than disappearing from the wizard - a new category should show up
    the moment a command claims it, described or not."""
    groups: dict[str, list[Command]] = {}
    for cmd in COMMAND_REGISTRY:
        groups.setdefault(cmd.category, []).append(cmd)
    # Each command next to its other forms (Command.family_name) - `mark`,
    # `mark-all`, `view-marks`, then `crop-grid`, `crop-grid-all` - in the
    # order the family first appears in the registry. The catalog is filed
    # by scope (one chapter, whole project), so without this every
    # whole-project form would trail after all the one-chapter ones.
    for name, cmds in groups.items():
        first: dict[str, int] = {}
        for index, cmd in enumerate(cmds):
            first.setdefault(cmd.family_name, index)
        groups[name] = sorted(cmds, key=lambda cmd: first[cmd.family_name])

    known = {category.name: category for category in CATEGORIES}
    ordered: dict[Category, list[Command]] = {}
    for category in CATEGORIES:
        if category.name in groups:
            ordered[category] = groups.pop(category.name)
    for name, cmds in groups.items():
        ordered[known.get(name, Category(name, ""))] = cmds
    return ordered
