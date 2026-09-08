"""The wizard's top-level menu groups.

Their own module rather than a block inside the command catalog: every
catalog file names these categories, and the catalog files are what change
when a command is added. Keeping the groups here means adding a command
never touches the file that defines what the groups *are*."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    """A wizard menu group. Ordered as listed - roughly the order a project
    moves through them - and described, so the top-level menu says what
    each group is for instead of listing three bare nouns."""

    name: str
    description: str


CATEGORIES: tuple[Category, ...] = (
    Category("Setup", "settings, shared assets, and model weights"),
    Category("Chapter Production", "one chapter, from download to rendered video"),
    Category("Project-wide", "whole-project compile, status, verify, and cleanup"),
)
