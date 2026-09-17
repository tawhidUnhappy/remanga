"""Progress for long work, told to whoever is showing it.

The work code (downloading, narrating, composing frames, encoding) reports
through `progress(...)` and never draws anything itself. On the command line
that becomes a Rich progress bar; inside the full-screen menus (remanga/ui/)
the UI installs a reporter and draws the bar in its own task view - two Rich
live displays fighting over one terminal is what made the old menus leave a
mess behind."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

from remanga.console import console


@dataclass
class Bar:
    """One piece of work in progress. Updated from the work's thread, read by
    whoever draws it."""

    description: str
    total: float | None = None
    completed: float = 0.0
    detail: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def advance(self, amount: float = 1.0) -> None:
        with self._lock:
            self.completed += amount
        _notify(self)

    def update(self, *, completed: float | None = None, total: float | None = None, detail: str | None = None) -> None:
        with self._lock:
            if completed is not None:
                self.completed = completed
            if total is not None:
                self.total = total
            if detail is not None:
                self.detail = detail
        _notify(self)


class Reporter:
    """What a display implements. `started`/`finished` bracket one Bar;
    `changed` is called on every update."""

    def started(self, bar: Bar) -> None: ...
    def changed(self, bar: Bar) -> None: ...
    def finished(self, bar: Bar) -> None: ...


_reporter: Reporter | None = None


def set_reporter(reporter: Reporter | None) -> None:
    global _reporter
    _reporter = reporter


def _notify(bar: Bar) -> None:
    if _reporter is not None:
        _reporter.changed(bar)


@contextmanager
def progress(description: str, total: float | None = None, completed: float = 0.0,
             unit: str = "") -> Iterator[Bar]:
    """A progress bar for the block. `total=None` is indeterminate. `unit`
    labels the count on the command line ("pages")."""
    bar = Bar(description, total, completed)
    if _reporter is not None:
        _reporter.started(bar)
        try:
            yield bar
        finally:
            _reporter.finished(bar)
        return

    columns = [TextColumn("[progress.description]{task.description}"), BarColumn()]
    if total is not None:
        count = f"{{task.completed:.0f}}/{{task.total:.0f}} {unit}"
        columns.append(TextColumn(count) if unit else MofNCompleteColumn())
    columns += [TextColumn("[dim]{task.fields[detail]}"), TimeElapsedColumn()]
    # refresh_per_second=4: a bar redrawing faster than its data changes only
    # fills the terminal's buffer (a locked screen stops draining it).
    with Progress(*columns, console=console, refresh_per_second=4) as rich_progress:
        task = rich_progress.add_task(f"[yellow]{description}", total=total, completed=completed, detail="")

        class _Cli(Reporter):
            def changed(self, b: Bar) -> None:
                rich_progress.update(task, completed=b.completed, total=b.total, detail=b.detail)

        previous = _reporter
        set_reporter(_Cli())
        try:
            yield bar
        finally:
            set_reporter(previous)
