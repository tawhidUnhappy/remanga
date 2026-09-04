"""Shared ffmpeg/ffprobe subprocess invocation so every module stops
re-implementing subprocess.run(...) - including the one place that knows how
to show an ffmpeg encode's progress without letting ffmpeg talk to the
terminal directly."""

from __future__ import annotations

import subprocess
import threading
from typing import List, Optional

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from remanga.console import console
from remanga.humanize import fmt_duration

# Injected in front of every progress-tracked run. Together these stop ffmpeg
# writing to the terminal at all, and have it emit machine-readable progress
# instead:
#   -hide_banner   drops the version + 40-line ./configure dump ffmpeg prints
#                  on startup - information nobody has ever needed mid-render.
#   -nostats       drops its own "frame=... fps=... speed=..." status line,
#                  which redraws twice a second and, in any terminal that
#                  doesn't honor \r the way ffmpeg assumes, lands in the
#                  scrollback as thousands of near-identical lines.
#   -loglevel error  keeps warnings like "100 buffers queued in out_#0:0"
#                  (benign muxer queue depth) out of the output while still
#                  capturing anything that actually failed.
#   -progress pipe:1  emits key=value progress blocks on stdout, which is what
#                  drives the bar below - a real percentage instead of a wall
#                  of text.
_PROGRESS_FLAGS = ("-hide_banner", "-nostats", "-loglevel", "error", "-progress", "pipe:1")


def run_ffmpeg(
    args: List[str],
    check: bool = False,
    capture: bool = False,
    show_progress: bool = False,
    total_seconds: Optional[float] = None,
    description: str = "Encoding",
) -> subprocess.CompletedProcess:
    """
    Runs an ffmpeg/ffprobe-style command with consistent stdout/stderr handling.
    - capture=True returns text stdout/stderr for inspection; otherwise output is discarded.
    - check=True raises CalledProcessError on non-zero exit (mirrors subprocess.run's check=).
    - show_progress=True renders a live progress bar for a long encode, fed by
      ffmpeg's own `-progress` stream (see _PROGRESS_FLAGS). Pass
      `total_seconds` - the duration of the media being written - for a real
      percentage; without it the bar runs indeterminate, still showing how
      much has been encoded and how fast. stderr is captured either way, so a
      failure still has its reason to print.
    """
    if show_progress:
        return _run_with_progress(args, check, total_seconds, description)
    if capture:
        return subprocess.run(args, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(args, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_with_progress(
    args: List[str], check: bool, total_seconds: Optional[float], description: str,
) -> subprocess.CompletedProcess:
    cmd = [args[0], *_PROGRESS_FLAGS, *args[1:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    # Drained on its own thread: ffmpeg writes errors here, and a full stderr
    # pipe would block the encode itself - the same deadlock the TTS workers
    # guard against.
    stderr_lines: List[str] = []

    def drain_stderr() -> None:
        try:
            for line in proc.stderr:
                stderr_lines.append(line)
        except (ValueError, OSError):
            pass

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    total = float(total_seconds) if total_seconds and total_seconds > 0 else None
    columns = [TextColumn("[progress.description]{task.description}"), BarColumn()]
    if total:
        columns.append(TextColumn("{task.fields[position]} / {task.fields[length]}"))
    else:
        columns.append(TextColumn("{task.fields[position]} encoded"))
    columns += [TextColumn("{task.fields[speed]}"), TimeElapsedColumn()]

    # refresh_per_second=4: ffmpeg reports about twice a second, and a bar
    # redrawing faster than its data changes just writes to the terminal for
    # no reason (see the same note in downloader/mangadex.py).
    with Progress(*columns, console=console, refresh_per_second=4) as progress:
        task = progress.add_task(
            f"[yellow]{description}...", total=total,
            position=fmt_duration(0), length=fmt_duration(total or 0), speed="",
        )
        try:
            for line in proc.stdout:
                key, _, value = line.strip().partition("=")
                value = value.strip()
                if key in ("out_time_us", "out_time_ms"):
                    # out_time_ms is microseconds in every ffmpeg build that
                    # ships it, despite the name - both keys are treated the
                    # same on purpose.
                    try:
                        seconds = int(value) / 1_000_000
                    except ValueError:
                        continue
                    progress.update(task, completed=min(seconds, total) if total else None,
                                    position=fmt_duration(seconds))
                elif key == "speed" and value not in ("", "N/A"):
                    progress.update(task, speed=f"[dim]{value}[/]")
                elif key == "progress" and value == "end":
                    if total:
                        progress.update(task, completed=total, position=fmt_duration(total))
        except (ValueError, OSError):
            pass  # pipe closed under us - the returncode below is what matters

    returncode = proc.wait()
    stderr_thread.join(timeout=2)
    output = "".join(stderr_lines)

    result = subprocess.CompletedProcess(cmd, returncode, stdout=output, stderr=output)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=output, stderr=output)
    return result
