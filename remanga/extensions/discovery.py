"""Finding extensions: every package under remanga/extensions/ that has an
`extension.py` defining `EXTENSION`, then anything installed that registers
one under the `remanga.extensions` entry-point group.

A built-in extension that fails to load is a bug in this repo and raises. An
installed one is someone else's code: it is reported and skipped, so a broken
plugin can't stop remanga from starting."""

from __future__ import annotations

import importlib
import pkgutil
import sys
from functools import cache
from importlib.metadata import entry_points

from remanga.extensions.spec import Extension, StatusHooks

ENTRY_POINT_GROUP = "remanga.extensions"
MANIFEST_MODULE = "extension"


def _builtin() -> list[Extension]:
    import remanga.extensions as package

    found = []
    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        if not info.ispkg:
            continue
        module = importlib.import_module(f"{package.__name__}.{info.name}.{MANIFEST_MODULE}")
        found.append(_checked(getattr(module, "EXTENSION", None), module.__name__))
    return found


def _installed() -> list[Extension]:
    found = []
    for point in sorted(entry_points(group=ENTRY_POINT_GROUP), key=lambda p: p.name):
        try:
            found.append(_checked(point.load(), point.value))
        except Exception as error:  # a plugin's failure must not stop remanga
            print(f"remanga: skipped extension '{point.name}' ({point.value}): {error}", file=sys.stderr)
    return found


def _checked(value: object, where: str) -> Extension:
    if not isinstance(value, Extension):
        raise TypeError(f"{where} must define EXTENSION = Extension(...), got {type(value).__name__}")
    return value


@cache
def load_extensions() -> tuple[Extension, ...]:
    """Every extension, built-in ones first, each name once."""
    extensions: dict[str, Extension] = {}
    for extension in [*_builtin(), *_installed()]:
        if extension.name in extensions:
            raise ValueError(f"Two extensions are named '{extension.name}'")
        extensions[extension.name] = extension
    return tuple(extensions.values())


def extension_named(name: str) -> Extension | None:
    return next((extension for extension in load_extensions() if extension.name == name), None)


def extension_generated_kinds() -> tuple[str, ...]:
    """Every extension's project-level generated directory kinds, in order."""
    return tuple(kind for extension in load_extensions() for kind in extension.generated_kinds)


def extension_source_files() -> set[str]:
    """Every extension's chapter source files - kept wherever crops.json is."""
    return {name for extension in load_extensions() for name in extension.source_files}


@cache
def extension_status_hooks() -> tuple[StatusHooks, ...]:
    """Every extension's status hooks, built once - `status` and the chapter
    lists ask for a chapter's status once per row."""
    return tuple(extension.status() for extension in load_extensions() if extension.status is not None)
