"""Running work behind a task screen.

The work runs in a thread. While it runs:
- everything remanga prints goes to the log file (projects/<name>/logs/),
  and is shown in the scrollable output box as it arrives;
- progress bars report here (remanga.activity) and are drawn by the screen;
- Ctrl+C stops it: KeyboardInterrupt is raised inside the work thread, and
  the programs it is waiting on (ffmpeg, the Chatterbox worker) are stopped so
  it isn't stuck waiting for them.
The screen is dismissed with a TaskOutcome; the caller shows the result."""

from __future__ import annotations

import contextlib
import ctypes
import os
import re
import signal
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.table import Table
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, ProgressBar, RichLog, Static

from remanga import activity
from remanga.console import console
from remanga.ui.widgets import TopBar

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


@dataclass
class Step:
    label: str
    run: Callable[[], Any]


@dataclass
class TaskOutcome:
    ok: bool
    results: list[Any] = field(default_factory=list)
    error: str = ""
    stopped: bool = False


class _LogSink:
    """A file-like target for the shared console: text to the log file, lines
    queued for the screen."""

    def __init__(self, path: Path):
        self._file = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()
        self._pending: list[str] = []

    def note(self, text: str) -> None:
        """For the log only - not shown on screen."""
        self._file.write(text)
        self._file.flush()

    def write(self, text: str) -> int:
        text = _ANSI.sub("", text)
        self._file.write(text)
        with self._lock:
            self._pending.append(text)
        return len(text)

    def take(self) -> str:
        with self._lock:
            text, self._pending = "".join(self._pending), []
        return text

    def flush(self) -> None:
        self._file.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        self._file.close()


class _Reporter(activity.Reporter):
    def __init__(self) -> None:
        self.bar: activity.Bar | None = None

    def started(self, bar: activity.Bar) -> None:
        self.bar = bar

    def finished(self, bar: activity.Bar) -> None:
        if self.bar is bar:
            self.bar = None


class TaskScreen(Screen[TaskOutcome]):
    BINDINGS = [Binding("ctrl+c", "stop", "Stop", priority=True)]

    def __init__(self, path: list[str], title: str, steps: list[Step], log_path: Path) -> None:
        super().__init__()
        self.path, self.title_text, self.steps, self.log_path = path, title, steps, log_path
        self.states = ["pending"] * len(steps)
        self.sink = _LogSink(log_path)
        self.reporter = _Reporter()
        self.thread_id: int | None = None
        self.stopping = False
        self.tick = 0
        self.partial = ""

    def compose(self) -> ComposeResult:
        yield TopBar(self.path, "working…")
        with Vertical(classes="task"):
            yield Label(self.title_text, classes="dialog-title")
            yield Static(id="steps")
            with Horizontal(id="bar-row"):
                yield Label(id="bar-label")
                yield ProgressBar(show_eta=False, id="bar")
                yield Label(id="bar-detail")
            output = RichLog(wrap=True, markup=False, highlight=False, id="output")
            output.border_subtitle = str(self.log_path)
            yield output
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_view()
        self.set_interval(0.1, self.refresh_view)
        self.run_worker(self.work, thread=True, exit_on_error=False)

    def refresh_view(self) -> None:
        self.tick += 1
        grid = Table.grid(padding=(0, 1))
        for label, state in zip(self.steps, self.states, strict=True):
            icon = {"pending": Text("·", style="dim"), "done": Text("✓", style="green"),
                    "failed": Text("✗", style="red"), "skipped": Text("–", style="dim"),
                    "running": Text(_SPINNER[self.tick % len(_SPINNER)], style="bold cyan")}[state]
            grid.add_row(icon, Text(label.label, style="bold" if state == "running" else
                                    ("dim" if state in ("pending", "skipped") else "")))
        self.query_one("#steps", Static).update(grid)

        bar, row = self.reporter.bar, self.query_one("#bar-row")
        row.display = bar is not None
        if bar is not None:
            self.query_one("#bar-label", Label).update(bar.description)
            self.query_one("#bar", ProgressBar).update(total=bar.total, progress=bar.completed)
            count = f"{bar.completed:.0f}/{bar.total:.0f}" if bar.total else ""
            self.query_one("#bar-detail", Label).update(" ".join(x for x in (count, bar.detail) if x))
        text = self.partial + self.sink.take().replace("\r\n", "\n").replace("\r", "\n")
        *lines, self.partial = text.split("\n")
        output = self.query_one("#output", RichLog)
        for line in lines:
            output.write(Text(line))

    def on_resize(self, event: events.Resize) -> None:
        # A short terminal squeezes the output box to nothing, and an empty
        # box still draws scrollbars - hide it instead (it is all in the log).
        needed = 12 + len(self.steps)  # top bar, footer, border, title, steps, progress bar, box borders
        self.query_one("#output").display = event.size.height >= needed

    def work(self) -> None:
        self.thread_id = threading.get_ident()
        self.sink.note(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S}  {self.title_text} ====\n")
        old_file = console.file
        console.file = self.sink
        activity.set_reporter(self.reporter)
        outcome = TaskOutcome(ok=True)
        try:
            for index, step in enumerate(self.steps):
                self.states[index] = "running"
                self.sink.note(f"-- {step.label}\n")
                outcome.results.append(step.run())
                self.states[index] = "done"
        except KeyboardInterrupt:
            outcome = TaskOutcome(ok=False, results=outcome.results, error="Stopped.", stopped=True)
            self.sink.write("Stopped by Ctrl+C\n")
        except Exception as error:  # the result screen shows it; the log keeps the rest
            outcome = TaskOutcome(ok=False, results=outcome.results, error=str(error))
            self.sink.write(f"ERROR: {error}\n")
        finally:
            self.thread_id = None
            activity.set_reporter(None)
            console.file = old_file
            self.sink.close()
        if not outcome.ok:
            self.states = ["failed" if s == "running" else "skipped" if s == "pending" else s for s in self.states]
        with contextlib.suppress(Exception):  # the app is already gone
            self.app.call_from_thread(self.dismiss, outcome)

    def action_stop(self) -> None:
        thread_id = self.thread_id
        if thread_id is None or self.stopping:
            return
        self.stopping = True
        self.query_one(TopBar).set_info("stopping…")
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_ulong(thread_id), ctypes.py_object(KeyboardInterrupt))
        _stop_child_processes()


def _stop_child_processes() -> None:
    """Stops the programs the work is waiting on, so the stop takes effect now
    rather than when they finish."""
    if sys.platform == "win32":
        return
    try:
        found = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True, check=False)
    except OSError:
        return
    for pid in found.stdout.split():
        with contextlib.suppress(OSError, ValueError):
            os.kill(int(pid), signal.SIGTERM)
