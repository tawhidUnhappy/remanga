"""Turning numbers into something a human reads at a glance.

Small on purpose, and shared: a duration formatted one way in the full-recap
summary and another way in a render log is the kind of inconsistency nobody
files a bug about and everybody notices."""

from __future__ import annotations


def fmt_duration(seconds: float) -> str:
    """Seconds as "1h02m03s" / "2m03s" - hours only when there are any."""
    seconds = int(round(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    return f"{hours}h{minutes:02d}m{secs:02d}s" if hours else f"{minutes}m{secs:02d}s"
