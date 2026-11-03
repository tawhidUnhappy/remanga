"""Finding the plug-ins - three places, in this order, so a later one can
replace an earlier one of the same name:

1. built-in: every package in remanga/plugins/ whose name does not start
   with "_" (this folder's own machinery does);
2. drop-in: every `*.py` file or package in the repo's top-level `plugins/`
   folder - a plug-in of your own, no install step;
3. installed: every entry point in the `remanga.plugins` group, for a
   plug-in shipped as its own Python package.

Importing a plug-in is what registers it (it calls `register`). A built-in
that fails to import is a bug and raises; a drop-in or installed one that
fails is reported and skipped, so one broken plug-in cannot stop remanga."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys
from importlib.metadata import entry_points
from pathlib import Path

from remanga.plugins import _registry

ENTRY_POINT_GROUP = "remanga.plugins"
DROP_IN_DIR = Path(__file__).resolve().parents[2] / "plugins"

_state = {"loaded": False}
_failed: list[tuple[str, str]] = []


def _with_origin(origin: str, load_one) -> None:
    _registry._current_origin[0] = origin
    try:
        load_one()
    finally:
        _registry._current_origin[0] = "built-in"


def _builtins() -> None:
    import remanga.plugins as package

    for info in sorted(pkgutil.iter_modules(package.__path__), key=lambda i: i.name):
        if not info.name.startswith("_"):
            importlib.import_module(f"remanga.plugins.{info.name}")


def _drop_in(path: Path) -> None:
    name = f"remanga_plugin_{path.stem}"
    target = path / "__init__.py" if path.is_dir() else path
    spec = importlib.util.spec_from_file_location(
        name, target, submodule_search_locations=[str(path)] if path.is_dir() else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


def _report(where: str, error: Exception) -> None:
    _failed.append((where, f"{type(error).__name__}: {error}"))
    print(f"remanga: plug-in {where} was skipped - {type(error).__name__}: {error}", file=sys.stderr)


def load() -> None:
    """Imports every plug-in, once. Safe to call from anywhere: the flag is
    set before anything is imported, so a plug-in asking for a registry
    while it loads gets what is registered so far instead of recursing."""
    if _state["loaded"]:
        return
    _state["loaded"] = True
    _builtins()
    if DROP_IN_DIR.is_dir():
        for path in sorted(DROP_IN_DIR.iterdir()):
            is_module = path.suffix == ".py" or (path.is_dir() and (path / "__init__.py").is_file())
            if is_module and not path.name.startswith(("_", ".")):
                try:
                    _with_origin(f"plugins/{path.name}", lambda p=path: _drop_in(p))
                except Exception as error:
                    _report(f"plugins/{path.name}", error)
    for point in entry_points(group=ENTRY_POINT_GROUP):
        try:
            _with_origin(f"entry point {point.name}", point.load)
        except Exception as error:
            _report(f"entry point {point.name}", error)


def failures() -> list[tuple[str, str]]:
    """The plug-ins that could not load, and why."""
    load()
    return list(_failed)
