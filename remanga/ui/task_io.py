"""What a task screen needs around the work it runs: the log the work's console
output goes to (and the last lines the screen shows), the progress bars it
reports, and stopping the child processes a stopped task leaves behind."""

from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

from remanga import activity

_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class LogSink:
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


class Reporter(activity.Reporter):
    def __init__(self) -> None:
        self.bar: activity.Bar | None = None

    def started(self, bar: activity.Bar) -> None:
        self.bar = bar

    def finished(self, bar: activity.Bar) -> None:
        if self.bar is bar:
            self.bar = None


def stop_child_processes() -> None:
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
