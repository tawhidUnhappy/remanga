"""The command catalog, one module per wizard category.

Adding a command is still a single edit in a single place - it just lives in
the file for its category rather than at the right offset of one 400-line
list. Which file is not a judgement call: it is the category the command
already declares, and the categories are the ones the wizard menu shows.

The ordering here is the order commands appear in `--help` and in the menu,
so these three lists are concatenated in category order, exactly as the one
combined list used to be written out."""

from __future__ import annotations

from remanga.commands.catalog.chapter import CHAPTER_COMMANDS
from remanga.commands.catalog.project import PROJECT_COMMANDS
from remanga.commands.catalog.setup import SETUP_COMMANDS

__all__ = ["CHAPTER_COMMANDS", "PROJECT_COMMANDS", "SETUP_COMMANDS"]
