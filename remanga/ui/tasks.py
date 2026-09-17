"""Running work behind a task view.

The work runs in the main thread, as it does on the command line, so Ctrl+C
stops it the usual way. While it runs:
- everything remanga prints goes to the chapter's log file, not the screen
  (the last few lines are shown dimmed under the steps);
- progress bars report to the task view (remanga.activity);
- a background thread redraws the view and watches for Ctrl+C, which the
  session's raw key mode would otherwise swallow.
Then the view is replaced by a result: what was made and what to do next, or
what went wrong - with the log one key away."""

from __future__ import annotations

import _thread
import re
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from remanga import activity
from remanga.console import console
from remanga.tui import keys
from remanga.ui import views

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


class _LogSink:
    """A file-like target for the shared console: plain text lines to the log,
    the last few kept for the screen."""

    def __init__(self, path: Path):
        self._file = path.open("a", encoding="utf-8")
        self.recent: deque[str] = deque(maxlen=4)
        self._partial = ""

    def note(self, text: str) -> None:
        """A line for the log only - not shown on screen."""
        self._file.write(text)

    def write(self, text: str) -> int:
        text = _ANSI.sub("", text)
        self._file.write(text)
        self._partial += text
        *lines, self._partial = self._partial.split("\n")
        self.recent.extend(line.rstrip() for line in lines if line.strip())
        return len(text)

    def flush(self) -> None:
        self._file.flush()

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        self._file.close()


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


class _Reporter(activity.Reporter):
    def __init__(self) -> None:
        self.bar: activity.Bar | None = None

    def started(self, bar: activity.Bar) -> None:
        self.bar = bar

    def finished(self, bar: activity.Bar) -> None:
        if self.bar is bar:
            self.bar = None


def run_task(ui, path: list[str], title: str, steps: list[Step], log_path: Path) -> TaskOutcome:
    views_steps = [views.StepView(step.label) for step in steps]
    sink = _LogSink(log_path)
    sink.note(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S}  {title} ====\n")
    reporter = _Reporter()
    done = threading.Event()
    old_file = console.file

    def view():
        bar = reporter.bar
        bar_state = (bar.description, bar.total, bar.completed, bar.detail) if bar else None
        body = views.task_view(title, views_steps, bar_state, list(sink.recent))
        hints = [("Ctrl+C", "stop")]
        return views.frame(path, "working…", views.dialog(title, body, width=96), hints)

    def refresh() -> None:
        while not done.is_set():
            try:
                ui.draw(view())
                if ui.key_waiting(0.12) and ui.key() == keys.CTRL_C:
                    _thread.interrupt_main()
            except Exception:
                time.sleep(0.12)

    console.file = sink
    activity.set_reporter(reporter)
    painter = threading.Thread(target=refresh, daemon=True)
    painter.start()
    outcome = TaskOutcome(ok=True)
    try:
        for index, step in enumerate(steps):
            views_steps[index].state = "running"
            sink.note(f"-- {step.label}\n")
            outcome.results.append(step.run())
            views_steps[index].state = "done"
    except KeyboardInterrupt:
        outcome = TaskOutcome(ok=False, results=outcome.results, error="Stopped.", stopped=True)
        _mark_failed(views_steps)
        sink.write("Stopped by Ctrl+C\n")
    except Exception as error:  # the result screen shows it; the log keeps the rest
        outcome = TaskOutcome(ok=False, results=outcome.results, error=str(error))
        _mark_failed(views_steps)
        sink.write(f"ERROR: {error}\n")
    finally:
        done.set()
        painter.join(timeout=1)
        activity.set_reporter(None)
        console.file = old_file
        sink.close()
    return outcome


def _mark_failed(steps: list[views.StepView]) -> None:
    for step in steps:
        if step.state == "running":
            step.state = "failed"
        elif step.state == "pending":
            step.state = "skipped"
