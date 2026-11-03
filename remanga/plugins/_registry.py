"""One registry per kind of plug-in, and the lazy references plug-ins point
at their code with.

A plug-in is registered as a small, frozen description (see _kinds.py) whose
code is named by REFERENCE - "remanga.plugins.kokoro.synth:KokoroSynthesizer"
- not imported. That keeps every plug-in's own `__init__` free of anything
heavy, which is what lets config/tts.py ask for the engines while
remanga.config is still being imported, and keeps start-up from paying for
torch-sized imports nobody asked for."""

from __future__ import annotations

import importlib
from typing import Any

KINDS = ("tts", "tool", "layout", "source", "job")

_registry: dict[str, dict[str, Any]] = {kind: {} for kind in KINDS}
# Where each plug-in came from, for `remanga plugins` ("built-in",
# "plugins/foo.py", "entry point bar").
_origin: dict[tuple[str, str], str] = {}
_current_origin = ["built-in"]


def register(kind: str, item: Any) -> Any:
    """Adds `item` (anything with a `name`) under `kind`. A later plug-in with
    the same name replaces an earlier one - which is how a drop-in plug-in
    overrides a built-in. Returns the item, so it reads well as an
    assignment."""
    if kind not in _registry:
        raise ValueError(f"No plug-in kind '{kind}' - the kinds are {', '.join(KINDS)}")
    _registry[kind][item.name] = item
    _origin[(kind, item.name)] = _current_origin[0]
    return item


def items(kind: str) -> list[Any]:
    """Every plug-in of `kind`, in their `order` (then name) - the first one
    is the default wherever a kind has one."""
    from remanga.plugins._loader import load

    load()
    return sorted(_registry[kind].values(), key=lambda item: (getattr(item, "order", 100), item.name))


def names(kind: str) -> tuple[str, ...]:
    return tuple(item.name for item in items(kind))


def find(kind: str, name: str | None) -> Any | None:
    """The plug-in of `kind` called `name`, or None."""
    items(kind)
    return _registry[kind].get((name or "").strip().lower()) or _registry[kind].get(name or "")


def get(kind: str, name: str | None) -> Any:
    """The plug-in called `name`, falling back to the kind's first one - a
    hand-edited config.json naming something that isn't installed should
    degrade to the default, not crash a screen."""
    found = find(kind, name)
    if found is not None:
        return found
    every = items(kind)
    if not every:
        raise LookupError(f"No '{kind}' plug-in is installed")
    return every[0]


def origin(kind: str, name: str) -> str:
    return _origin.get((kind, name), "?")


def resolve(ref: Any) -> Any:
    """The object a reference names ("package.module:attr"); anything that
    isn't a string is already the object and comes back as it is."""
    if not isinstance(ref, str):
        return ref
    module, _, attr = ref.partition(":")
    target: Any = importlib.import_module(module)
    for part in filter(None, attr.split(".")):
        target = getattr(target, part)
    return target


def call(ref: Any, *args: Any, **kwargs: Any) -> Any:
    return resolve(ref)(*args, **kwargs)
