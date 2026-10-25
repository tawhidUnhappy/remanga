"""Kokoro's recommended settings - asked the first time remanga opens
(ui/first_run.py). It runs on any machine, so it has no `fits`."""

from __future__ import annotations


def recommend(config, machine) -> None:
    """Heart, the one voice hexgrad grades A, at its own pace."""
    config.tts.kokoro.voice, config.tts.kokoro.speed = "af_heart", 1.0
