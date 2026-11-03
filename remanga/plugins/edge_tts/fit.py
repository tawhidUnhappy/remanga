"""Whether a machine can use Edge voices, and their recommended settings -
asked the first time remanga opens (ui/first_run.py)."""

from __future__ import annotations

from remanga.machine import Machine


def fits(machine: Machine) -> str | None:
    return None if machine.online else "needs the internet (it is Microsoft's online service)"


def recommend(config, machine: Machine) -> None:
    """Guy - the classic recap voice - at the service's own pace."""
    config.tts.edge.voice = "en-US-GuyNeural"
