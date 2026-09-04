"""The one shape every interactive menu in remanga is built from.

Menus elsewhere used to be printed by hand - a `console.print` loop per
screen, each inventing its own numbering, its own "(current)" marker, its
own dim-hint formatting - which is why no two of them looked or behaved
alike. Everything now builds a list of `Choice` objects instead and hands it
to `select`/`multiselect`, so a menu's *content* is the only thing a caller
writes; layout, highlighting, filtering, scrolling and key handling are the
same everywhere by construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, List, Optional, Sequence


@dataclass
class Choice:
    """One selectable row.

    label    - the row's own text (plain text, never Rich markup: it usually
               carries user data like a project name or a filename, and a
               literal '[' in one of those would otherwise be parsed as the
               start of a style tag - see remanga.console.display_path).
    hint     - short dim text on the same line, e.g. what a command does.
    detail   - longer text shown under the row only while it's highlighted,
               for the fine print that would make every row unreadable if
               shown on all of them at once.
    badge    - tiny status flag rendered before the label ("on"/"off"/
               "current"/"missing"), for menus that show state as well as
               offering a choice.
    value    - what select() returns for this row; defaults to the label.
    disabled - shown, greyed out, and skipped by the cursor: use it to keep
               an option visible with a reason attached rather than making
               it silently vanish.
    """

    label: str
    hint: str = ""
    detail: str = ""
    badge: str = ""
    value: Any = None
    disabled: bool = False
    checked: bool = False

    def __post_init__(self) -> None:
        if self.value is None:
            self.value = self.label


def to_choices(items: Iterable[Any], *, label: Optional[Callable[[Any], str]] = None,
               hint: Optional[Callable[[Any], str]] = None) -> List[Choice]:
    """Turns any iterable into Choices, keeping the original objects as the
    values so the caller gets its own object back from select() rather than
    a string it then has to look up again."""
    out: List[Choice] = []
    for item in items:
        if isinstance(item, Choice):
            out.append(item)
            continue
        out.append(Choice(
            label=label(item) if label else str(item),
            hint=hint(item) if hint else "",
            value=item,
        ))
    return out


def index_of_value(choices: Sequence[Choice], value: Any, fallback: int = 0) -> int:
    """Where `value` sits in `choices`, for pre-highlighting whatever is
    already configured/selected - the "you are here" that makes Enter alone
    a safe answer to every menu."""
    for i, choice in enumerate(choices):
        if choice.value == value:
            return i
    return fallback


@dataclass
class Toggle:
    """A named on/off setting, for the checklist screens that edit config
    (see remanga.settings.vision). Kept separate from Choice because the
    thing being chosen there is the *state* of every row at once, not one
    row out of many."""

    name: str
    label: str
    hint: str = ""
    detail: str = ""
    enabled: bool = False
    tags: List[str] = field(default_factory=list)
