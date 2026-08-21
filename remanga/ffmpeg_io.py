"""Shared ffmpeg/ffprobe subprocess invocation so every module stops re-implementing subprocess.run(...)."""

from __future__ import annotations

import subprocess
from typing import List


def run_ffmpeg(args: List[str], check: bool = False, capture: bool = False) -> subprocess.CompletedProcess:
    """
    Runs an ffmpeg/ffprobe-style command with consistent stdout/stderr handling.
    - capture=True returns text stdout/stderr for inspection; otherwise output is discarded.
    - check=True raises CalledProcessError on non-zero exit (mirrors subprocess.run's check=).
    """
    if capture:
        return subprocess.run(args, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(args, check=check, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
