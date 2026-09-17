"""Shared ffmpeg/ffprobe subprocess invocation so every module stops
re-implementing subprocess.run(...) - including the one place that knows how
to show an ffmpeg encode's progress without letting ffmpeg talk to the
terminal directly."""

from __future__ import annotations

import contextlib
import subprocess
import threading

from remanga import activity
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
    args: list[str],
    check: bool = False,
    capture: bool = False,
    show_progress: bool = False,
    total_seconds: float | None = None,
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
        return subprocess.run(args, check=check, capture_output=True, text=True)
    return subprocess.run(args, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_with_progress(
    args: list[str], check: bool, total_seconds: float | None, description: str,
) -> subprocess.CompletedProcess:
    cmd = [args[0], *_PROGRESS_FLAGS, *args[1:]]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)

    # Drained on its own thread: ffmpeg writes errors here, and a full stderr
    # pipe would block the encode itself - the same deadlock the TTS workers
    # guard against.
    stderr_lines: list[str] = []

    def drain_stderr() -> None:
        # pipe closed under us (ffmpeg exited) - nothing left to drain
        with contextlib.suppress(ValueError, OSError):
            stderr_lines.extend(proc.stderr)

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    total = float(total_seconds) if total_seconds and total_seconds > 0 else None
    length = f" / {fmt_duration(total)}" if total else ""
    with activity.progress(description, total=total) as bar:
        speed = ""
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
                    bar.update(completed=min(seconds, total) if total else seconds,
                               detail=f"{fmt_duration(seconds)}{length} {speed}".strip())
                elif key == "speed" and value not in ("", "N/A"):
                    speed = value
                elif key == "progress" and value == "end" and total:
                    bar.update(completed=total, detail=f"{fmt_duration(total)}{length}")
        except (ValueError, OSError):
            pass  # pipe closed under us - the returncode below is what matters

    returncode = proc.wait()
    stderr_thread.join(timeout=2)
    output = "".join(stderr_lines)

    result = subprocess.CompletedProcess(cmd, returncode, stdout=output, stderr=output)
    if check and returncode != 0:
        raise subprocess.CalledProcessError(returncode, cmd, output=output, stderr=output)
    return result
