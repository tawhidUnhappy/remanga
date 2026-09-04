"""Reading and writing one config field by name.

Settings screens are data-driven here - a screen is a list of specs, each
naming the config field it edits ("tts.spk_audio_prompt",
"audio.bgm_enabled") rather than closing over a hand-written getter/setter
pair. These two functions are what makes that possible, and they're the
only place in the settings package that walks a dotted path."""

from __future__ import annotations

from typing import Any, Tuple

from remanga.config import RemangaConfig


def _resolve(config: RemangaConfig, dotted: str) -> Tuple[Any, str]:
    *parents, attr = dotted.split(".")
    obj: Any = config
    for name in parents:
        obj = getattr(obj, name)
    return obj, attr


def get_field(config: RemangaConfig, dotted: str) -> Any:
    obj, attr = _resolve(config, dotted)
    return getattr(obj, attr)


def set_field(config: RemangaConfig, dotted: str, value: Any, *, save: bool = True) -> None:
    """Sets a nested config field and (by default) persists config.json
    immediately. Saving per edit rather than at the end of a walkthrough is
    deliberate: every settings screen in remanga is escapable at any point,
    and an answer the user has already given should survive backing out of
    the next question."""
    obj, attr = _resolve(config, dotted)
    setattr(obj, attr, value)
    if save:
        config.save()
