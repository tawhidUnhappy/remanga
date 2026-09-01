"""Shared helper for streaming a subprocess's combined stdout/stderr live to
the console the way a real terminal would.

Naive text-mode line iteration (`for line in proc.stdout`) translates every
`\\r` to `\\n` during Python's universal-newlines handling - so a progress
bar that's meant to redraw over itself in place (ffmpeg's own `-stats` line,
huggingface_hub's tqdm download bars) instead turns into one brand-new
scrollback line per refresh. Both of those redraw multiple times a second,
so over a real multi-minute download or encode that's thousands of
near-duplicate lines flooding the terminal - not the live progress this is
meant to provide. This reads raw bytes and only starts a fresh printed line
on a genuine `\\n`; a `\\r`-terminated update overwrites the previous one,
exactly like running the subprocess directly in a terminal would."""

from __future__ import annotations

import subprocess
from typing import List, Optional, Sequence, Tuple


def stream_subprocess(args: Sequence[str], cwd: Optional[str] = None) -> Tuple[int, str]:
    """Runs `args`, streaming its combined stdout/stderr live to this
    process's own stdout - `\\r`-terminated updates overwrite the previous
    line, a real `\\n` starts a fresh one. Returns (returncode, full
    captured output) once the process exits, for callers that still need
    the text for an error message."""
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, bufsize=0)
    buf = bytearray()
    chunks: List[str] = []
    last_len = 0
    assert proc.stdout is not None
    while True:
        byte = proc.stdout.read(1)
        if not byte:
            break
        if byte in (b"\r", b"\n"):
            text = buf.decode("utf-8", errors="replace")
            buf.clear()
            if byte == b"\n":
                chunks.append(text + "\n")
                # Pad over any leftover tail from a longer previous \r-line
                # before starting a fresh one, then reset the overwrite tracker.
                print("\r" + text + " " * max(0, last_len - len(text)))
                last_len = 0
            else:
                chunks.append(text + "\r")
                print("\r" + text + " " * max(0, last_len - len(text)), end="", flush=True)
                last_len = len(text)
        else:
            buf += byte
    if buf:
        text = buf.decode("utf-8", errors="replace")
        chunks.append(text + "\n")
        print("\r" + text + " " * max(0, last_len - len(text)))
    returncode = proc.wait()
    return returncode, "".join(chunks)
