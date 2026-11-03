"""The first time remanga opens: which narrator engine to use, out of the
ones this machine can run (each engine's `fits`, against machine.detect()),
the best of them first - and the one picked gets its recommended settings
(each engine's `recommend`). Asked again on the next start if it is left
with Esc; Settings -> Narrator engine changes it afterwards."""

from __future__ import annotations

import asyncio

from remanga import plugins
from remanga.config import RemangaConfig
from remanga.machine import Machine, detect
from remanga.ui.dialogs import Choice


def engine_options(machine: Machine) -> tuple[list[tuple[str, str, str]], list[str]]:
    """(label, hint, name) for each engine this machine runs, best first, and
    a line for each it can't, saying why."""
    runnable, unavailable = [], []
    for engine in sorted(plugins.items("tts"), key=lambda e: -e.quality):
        problem = plugins.call(engine.fits, machine) if engine.fits else None
        if problem:
            unavailable.append(f"{engine.display_name}: {problem}")
        else:
            runnable.append(engine)
    options = [(f"{engine.display_name}{'  (recommended)' if i == 0 else ''}", engine.summary, engine.name)
               for i, engine in enumerate(runnable)]
    return options, unavailable


def apply_engine(config: RemangaConfig, name: str, machine: Machine) -> None:
    """`name` as the narrator, with its recommended settings."""
    engine = plugins.get("tts", name)
    config.tts.engine = name
    if engine.recommend:
        plugins.call(engine.recommend, config, machine)
    config.menus.engine_chosen = True


async def choose_engine(app, config: RemangaConfig) -> None:
    machine = await asyncio.to_thread(detect)   # the internet check can take seconds
    options, unavailable = engine_options(machine)
    note = f"This machine: {machine.describe()}."
    if unavailable:
        note += " Not offered here: " + "; ".join(unavailable) + "."
    note += (" The one you pick gets its recommended voice and settings; Settings -> Narrator engine "
             "changes it any time. Its model downloads the first time it narrates.")
    picked = await app.push_screen_wait(Choice("Which narrator?", options, note=note))
    if picked:
        apply_engine(config, picked, machine)
        config.save()
        app.notify(f"Narrator: {plugins.get('tts', picked).display_name}, with its recommended settings.",
                   timeout=6)
