"""Pluggable features.

A feature that adds commands, pipeline steps, settings, config, status rows or
generated files lives in a package of its own under this directory, with an
`extension.py` that declares all of it as one `Extension` (see spec.py). Drop
the package in and every menu, the pipeline checklist, the settings screen,
`status`, `restart` and `wipe` pick it up; take it out and they forget it.
Nothing outside the package names it. Extensions installed as separate
packages can register one under the `remanga.extensions` entry-point group.

This package's own import stays light on purpose - the registries import it
while they are still loading themselves (see spec.py)."""

from __future__ import annotations

from remanga.extensions.discovery import (
    extension_generated_kinds,
    extension_named,
    extension_source_files,
    load_extensions,
)
from remanga.extensions.spec import Extension, Placed, StatusHooks, StatusRow, SummaryStage, place

__all__ = [
    "Extension",
    "Placed",
    "StatusHooks",
    "StatusRow",
    "SummaryStage",
    "extension_generated_kinds",
    "extension_named",
    "extension_source_files",
    "load_extensions",
    "place",
]
