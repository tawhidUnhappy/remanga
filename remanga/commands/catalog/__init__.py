"""The command catalog, filed by scope: setup, one chapter, the whole project.

Adding a command is a single edit in a single place - one entry in the file
for its scope. Which menu group it shows under is its own `category` (the
workflow stage - remanga/commands/categories.py), with its whole-project
form listed right after it there (Command.family_name).

Within a category, the order here is the order commands appear in `--help`
and in the menu, so these three lists are concatenated setup, chapter,
project."""

from __future__ import annotations

from remanga.commands.catalog.chapter import CHAPTER_COMMANDS
from remanga.commands.catalog.project import PROJECT_COMMANDS
from remanga.commands.catalog.setup import SETUP_COMMANDS

__all__ = ["CHAPTER_COMMANDS", "PROJECT_COMMANDS", "SETUP_COMMANDS"]
