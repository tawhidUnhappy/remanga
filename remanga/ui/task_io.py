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
import time
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


# How long a program asked to stop gets to stop on its own before it is
# killed outright.
STOP_GRACE_SECONDS = 3.0


def _children() -> list[int]:
    try:
        found = subprocess.run(["pgrep", "-P", str(os.getpid())], capture_output=True, text=True, check=False)
    except OSError:
        return []
    return [int(pid) for pid in found.stdout.split() if pid.isdigit()]


def _signal(pids: list[int], sig: signal.Signals) -> None:
    for pid in pids:
        with contextlib.suppress(OSError):
            os.kill(pid, sig)


def stop_child_processes() -> None:
    """Stops the programs the work is waiting on, so the stop takes effect now
    rather than when they finish: asked politely, then killed if they are
    still there after STOP_GRACE_SECONDS.

    The kill is not optional. ffmpeg catches SIGTERM to finish its file
    cleanly, and encoding a chapter (concat of PNG frames into h264_nvenc,
    with the sound as a second output) it never does: every thread waits on
    another, nothing is written, and it sits there for good. The work thread
    is blocked reading ffmpeg's progress, so the stop never lands either and
    the screen stays on "stopping…" with the GPU still busy. Nothing a kill
    interrupts looks finished afterwards - the encode writes to `.part` files
    and takes are written atomically - so it costs nothing to be sure.

    Runs the wait on a thread of its own: this is called from the UI."""
    if sys.platform == "win32":
        return
    pids = _children()
    _signal(pids, signal.SIGTERM)

    def kill_survivors() -> None:
        deadline = time.monotonic() + STOP_GRACE_SECONDS
        while time.monotonic() < deadline:
            # Only the ones asked to stop: a child started after the stop
            # (a cleanup step's) is not this function's to kill.
            alive = [pid for pid in pids if pid in _children()]
            if not alive:
                return
            time.sleep(0.2)
        _signal([pid for pid in pids if pid in _children()], signal.SIGKILL)

    if pids:
        threading.Thread(target=kill_survivors, name="stop-children", daemon=True).start()
