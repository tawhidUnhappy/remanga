"""Shared ffmpeg/ffprobe subprocess invocation so every module stops re-implementing subprocess.run(...)."""

from __future__ import annotations

import subprocess
from typing import List


def run_ffmpeg(args: List[str], check: bool = False, capture: bool = False, show_progress: bool = False) -> subprocess.CompletedProcess:
    """
    Runs an ffmpeg/ffprobe-style command with consistent stdout/stderr handling.
    - capture=True returns text stdout/stderr for inspection; otherwise output is discarded.
    - check=True raises CalledProcessError on non-zero exit (mirrors subprocess.run's check=).
    - show_progress=True (implies capture) streams ffmpeg's own stderr progress line
      (frame=.../fps=.../time=.../speed=..., overwritten in place via \\r, same as running
      ffmpeg directly in a terminal) to this process's stdout AS the encode runs, instead of
      only ever seeing it dumped in one block after the fact (on error) or never at all. Use
      for anything long enough that a silent terminal would look stalled - a real render, not
      the sub-second NVENC capability probes that share this same helper.
    """
    if show_progress:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        output_lines: List[str] = []
        for line in proc.stdout:  # type: ignore[union-attr]
            print(line, end="", flush=True)
            output_lines.append(line)
        returncode = proc.wait()
        result = subprocess.CompletedProcess(args, returncode, stdout="".join(output_lines), stderr="".join(output_lines))
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, args, output=result.stdout, stderr=result.stderr)
        return result
    if capture:
        return subprocess.run(args, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(args, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
