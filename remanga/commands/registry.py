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

# Category order is menu order and --help order (see catalog/__init__).
COMMAND_REGISTRY: list[Command] = [*SETUP_COMMANDS, *CHAPTER_COMMANDS, *PROJECT_COMMANDS]

COMMAND_BY_NAME: dict[str, Command] = {cmd.name: cmd for cmd in COMMAND_REGISTRY}

def commands_by_category() -> dict[Category, list[Command]]:
    """Groups the registry by category, in CATEGORIES order. A command whose
    category isn't in CATEGORIES still gets a group of its own at the end
    rather than disappearing from the wizard - a new category should show up
    the moment a command claims it, described or not."""
    groups: dict[str, list[Command]] = {}
    for cmd in COMMAND_REGISTRY:
        groups.setdefault(cmd.category, []).append(cmd)

    known = {category.name: category for category in CATEGORIES}
    ordered: dict[Category, list[Command]] = {}
    for category in CATEGORIES:
        if category.name in groups:
            ordered[category] = groups.pop(category.name)
    for name, cmds in groups.items():
        ordered[known.get(name, Category(name, ""))] = cmds
    return ordered
