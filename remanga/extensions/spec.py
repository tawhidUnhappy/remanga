"""What an extension is: one feature, declared in one place, plugged into
every registry remanga builds its menus and pipeline from.

An extension declares data, and hands over anything heavy as a zero-argument
factory. The registries read extensions while they are themselves still being
imported (commands/registry.py, pipeline/registry.py, settings/sections.py,
paths/projects.py, config/root.py), so a manifest that imported a handler, a
settings screen or a pydantic model at module level would import the very
registry that is loading it. A factory is only called once that registry has
what it needs, and it imports whatever it likes at that point.

This module imports nothing from remanga at runtime, for the same reason:
anything that reads a manifest can import it."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

if TYPE_CHECKING:
    from pydantic import BaseModel

    from remanga.commands.spec import Command
    from remanga.pipeline.spec import Step
    from remanga.settings.section_spec import Section

T = TypeVar("T")


@dataclass(frozen=True)
class Placed(Generic[T]):
    """An item and where it goes: right after the core item named `after`,
    or at the end when `after` is None or names nothing."""

    item: T
    after: str | None = None


@dataclass(frozen=True)
class StatusRow:
    """One line of the `status` report. `render` gets the chapter's status
    dict (core facts plus this extension's `facts`) and returns the value
    shown after the label; the row goes right after the core row `after`."""

    label: str
    render: Callable[[dict[str, Any]], str]
    after: str | None = None


@dataclass(frozen=True)
class SummaryStage:
    """A stage in a chapter's one-line summary ("Crops JSON Ready", ...).
    Stages are tried in order and the first that returns text wins; this one
    is tried right after the core stage `after`."""

    name: str
    describe: Callable[[dict[str, Any]], str | None]
    after: str | None = None


@dataclass(frozen=True)
class StatusHooks:
    """How an extension shows up in a chapter's status. `facts` adds keys to
    the status dict - cheap, disk-only checks, like the core ones."""

    facts: Callable[[str, str], dict[str, Any]] = lambda project, chapter: {}
    rows: Sequence[StatusRow] = ()
    summaries: Sequence[SummaryStage] = ()


@dataclass(frozen=True)
class Extension:
    """One pluggable feature.

    `name` is also its config key: an extension with a `config_model` gets
    `config.extensions.<name>`, saved in config.json and overridable per
    project like any other work setting."""

    name: str
    title: str
    description: str = ""
    commands: Callable[[], Sequence[Placed[Command]]] | None = None
    steps: Callable[[], Sequence[Placed[Step]]] | None = None
    settings: Callable[[], Sequence[Placed[Section]]] | None = None
    config_model: Callable[[], type[BaseModel]] | None = None
    status: Callable[[], StatusHooks] | None = None
    # Project-level generated directories ({manga}/{kind}/chapter_N/) this
    # extension writes - wiped with every other generated artifact.
    generated_kinds: tuple[str, ...] = ()
    # Chapter source-folder entries this extension writes that remanga can't
    # rebuild: kept wherever crops.json is kept.
    source_files: tuple[str, ...] = ()
    # Pipeline steps offered in the checklist but left out of the default
    # order, because each replaces a default step rather than adding one.
    alternative_steps: tuple[str, ...] = ()
    tags: tuple[str, ...] = field(default_factory=tuple)


def place(core: Iterable[T], placed: Iterable[Placed[T]], name_of: Callable[[T], str]) -> list[T]:
    """`core` with every placed item inserted after its anchor, keeping the
    order the extensions gave. Items anchored to another placed item follow
    it, and items whose anchor exists nowhere go at the end."""
    items = list(core)
    anchor_of: dict[int, str] = {}  # id(placed item) -> the anchor it went after
    for entry in placed:
        names = [name_of(item) for item in items]
        if entry.after is not None and entry.after in names:
            index = names.index(entry.after) + 1
            # After anything already placed behind the same anchor, so two
            # extensions anchored to one item keep their own order.
            while index < len(items) and anchor_of.get(id(items[index])) == entry.after:
                index += 1
            items.insert(index, entry.item)
            anchor_of[id(entry.item)] = entry.after
        else:
            items.append(entry.item)
    return items
