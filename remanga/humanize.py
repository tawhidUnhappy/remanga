"""Turning numbers into something a human reads at a glance.

Small on purpose, and shared, so a duration reads the same everywhere."""

from __future__ import annotations


def fmt_duration(seconds: float) -> str:
    """Seconds as "1h02m03s" / "2m03s" - hours only when there are any."""
    seconds = round(seconds)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s" if hours else f"{minutes}m{secs:02d}s"


def fmt_size(size: int) -> str:
    """Bytes as "812 KB" / "45.5 MB" / "1.2 GB"."""
    for unit, scale in (("GB", 1 << 30), ("MB", 1 << 20)):
        if size >= scale:
            return f"{size / scale:.1f} {unit}"
    return f"{max(1, round(size / 1024))} KB" if size else "0 KB"
