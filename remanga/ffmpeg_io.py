"""Shared ffmpeg/ffprobe subprocess invocation so every module stops re-implementing subprocess.run(...)."""

from __future__ import annotations

import subprocess
from typing import List

from remanga.proc_io import stream_subprocess


def run_ffmpeg(args: List[str], check: bool = False, capture: bool = False, show_progress: bool = False) -> subprocess.CompletedProcess:
    """
    Runs an ffmpeg/ffprobe-style command with consistent stdout/stderr handling.
    - capture=True returns text stdout/stderr for inspection; otherwise output is discarded.
    - check=True raises CalledProcessError on non-zero exit (mirrors subprocess.run's check=).
    - show_progress=True (implies capture) streams ffmpeg's own stderr progress line
      (frame=.../fps=.../time=.../speed=...) live via remanga.proc_io.stream_subprocess,
      which overwrites that one line in place exactly like running ffmpeg directly in a
      terminal does - not one new scrollback line per refresh (ffmpeg redraws that line
      roughly twice a second, so a naive per-\\n reader would flood the terminal with
      thousands of near-duplicate lines over a real encode). Use for anything long
      enough that a silent terminal would look stalled - a real render, not the
      sub-second NVENC capability probes that share this same helper.
    """
    if show_progress:
        returncode, output = stream_subprocess(args)
        result = subprocess.CompletedProcess(args, returncode, stdout=output, stderr=output)
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, args, output=result.stdout, stderr=result.stderr)
        return result
    if capture:
        return subprocess.run(args, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(args, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
