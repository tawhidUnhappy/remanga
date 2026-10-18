"""Narration presets: a whole narration sound in one JSON file, picked in
Settings as "Narration preset".

Each JSON file is one preset (the file name, without .json, is its id).
The ones that ship with remanga are in presets/ (tracked by git); the ones a
user saves from Settings ("Save as preset") go to global/presets/, which git
never tracks, so a pull never touches them and they are never pushed.

A preset fixes the settings it names - engine, voice, speed, take length,
the voice chain, loudness - and leaves every setting it doesn't name to its
own row. While one is picked, the rows it fixes are shown but locked
(ui/screens/settings.py); "No preset" hands every row back. A new sound is a
new file, not new code. presets/README.md lists the keys.

The preset is applied whenever the config is loaded (RemangaConfig), so
whatever config.json says, the picked preset wins - for every chapter."""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, PrivateAttr, ValidationError

from remanga import plugins
from remanga.console import console, escape as _esc
from remanga.json_io import read_json, write_json
from remanga.paths import GLOBAL_DIR, REPO_ROOT

if TYPE_CHECKING:
    from remanga.config.root import RemangaConfig

# The presets remanga ships, and the ones saved from Settings (gitignored).
PRESETS_DIR = REPO_ROOT / "presets"
CUSTOM_PRESETS_DIR = GLOBAL_DIR / "presets"

# Picked until someone picks otherwise: presets/youtube-narrator.json.
DEFAULT_PRESET = "youtube-narrator"

# Bigger than any chapter - the same as ui/screens/settings_sound.py:WHOLE_CHAPTER.
WHOLE_CHAPTER_MINUTES = 999.0


class NarrationPreset(BaseModel):
    """One presets/*.json file. Every setting is optional: a key left out is
    a setting the preset leaves to its row."""

    # A misspelt key is an error, not a setting silently left alone.
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str = ""
    engine: str | None = None
    voice: str | None = None
    speed: float | None = None
    # Minutes per take, "whole_chapter" or "per_panel".
    take_length: float | Literal["whole_chapter", "per_panel"] | None = None
    compressor: Literal["off", "gentle", "medium", "strong"] | None = None
    bass_boost_db: float | None = None
    presence_db: float | None = None
    limiter: bool | None = None
    # The longest pause inside a take, in ms (0 = natural), and the silence
    # between panels.
    max_gap_ms: int | None = None
    panel_pause_ms: int | None = None
    # A target in LUFS, or "off" for no loudness pass.
    loudness_lufs: float | Literal["off"] | None = None
    # True for a preset saved from Settings (global/presets/), not one that ships.
    _custom: bool = PrivateAttr(default=False)

    @property
    def custom(self) -> bool:
        return self._custom

    def take_minutes(self) -> float | None:
        if self.take_length is None:
            return None
        return {"whole_chapter": WHOLE_CHAPTER_MINUTES, "per_panel": 0.0}.get(self.take_length,
                                                                              self.take_length)

    def engine_for(self, config: RemangaConfig) -> str:
        return self.engine or config.tts.engine

    def fixed_keys(self, config: RemangaConfig) -> set[str]:
        """The config fields (dotted, as settings rows name them) this preset
        sets - what the settings screen locks."""
        engine = self.engine_for(config)
        keys = {"tts.engine"} if self.engine else set()
        if self.voice is not None:
            keys.add(f"tts.{engine}.voice")
        if self.speed is not None:
            keys.add(f"tts.{engine}.speed")
        if self.take_length is not None:
            keys |= {"audio.batch_narration", "audio.batch_target_minutes"}
        if self.compressor is not None:
            keys.add("audio.voice_compressor")
        if self.bass_boost_db is not None:
            keys.add("audio.voice_bass_boost_db")
        if self.presence_db is not None:
            keys.add("audio.voice_presence_db")
        if self.limiter is not None:
            keys.add("audio.voice_limiter")
        if self.max_gap_ms is not None:
            keys.add("audio.max_gap_ms")
        if self.panel_pause_ms is not None:
            keys.add("audio.pause_between_panels_ms")
        if self.loudness_lufs is not None:
            keys |= {"audio.enable_loudnorm", "audio.loudness_target_lufs"}
        return keys

    def apply(self, config: RemangaConfig) -> None:
        """Sets everything this preset names on `config`."""
        if self.engine:
            if self.engine in plugins.names("tts"):
                config.tts.engine = self.engine
            else:
                console.print(f"[yellow]Preset '{_esc(self.name)}' names an engine remanga doesn't have "
                              f"('{_esc(self.engine)}') - keeping {_esc(config.tts.engine)}.[/]")
        block = config.tts.engine_block
        for key in ("voice", "speed"):
            value = getattr(self, key)
            if value is not None and key in type(block).model_fields:
                setattr(block, key, value)
        minutes = self.take_minutes()
        if minutes is not None:
            config.audio.batch_narration = minutes > 0
            if minutes > 0:
                config.audio.batch_target_minutes = minutes
        audio = config.audio
        if self.compressor is not None:
            audio.voice_compressor = self.compressor
        if self.bass_boost_db is not None:
            audio.voice_bass_boost_db = self.bass_boost_db
        if self.presence_db is not None:
            audio.voice_presence_db = self.presence_db
        if self.limiter is not None:
            audio.voice_limiter = self.limiter
        if self.max_gap_ms is not None:
            audio.max_gap_ms = self.max_gap_ms
        if self.panel_pause_ms is not None:
            audio.pause_between_panels_ms = self.panel_pause_ms
        if self.loudness_lufs == "off":
            audio.enable_loudnorm = False
        elif self.loudness_lufs is not None:
            audio.enable_loudnorm, audio.loudness_target_lufs = True, self.loudness_lufs


# Parsed files by (path, mtime): the config loads often, and a broken file
# should be reported once, not on every load.
_cache: dict[tuple[Path, float], NarrationPreset | None] = {}


def _read(path: Path, custom: bool = False) -> NarrationPreset | None:
    key = (path, path.stat().st_mtime)
    if key not in _cache:
        try:
            preset = NarrationPreset.model_validate(read_json(path))
            preset._custom = custom
            _cache[key] = preset
        except (ValidationError, ValueError, OSError) as e:
            console.print(f"[yellow]Skipping narration preset {_esc(str(path))}: {_esc(str(e))}[/]")
            _cache[key] = None
    return _cache[key]


def _folder(folder: Path, custom: bool) -> dict[str, NarrationPreset | None]:
    # The default first, then by name - so the list opens on the preset most people want.
    paths = sorted(folder.glob("*.json"), key=lambda path: (path.stem != DEFAULT_PRESET, path.stem))
    return {path.stem: _read(path, custom) for path in paths} if folder.is_dir() else {}


def load_presets() -> dict[str, NarrationPreset]:
    """Every readable preset by id: the ones remanga ships, then the saved
    ones. A saved preset can't take a shipped one's id (save_custom refuses),
    and one put there by hand is skipped rather than allowed to replace it."""
    found = _folder(PRESETS_DIR, custom=False)
    for key, preset in _folder(CUSTOM_PRESETS_DIR, custom=True).items():
        if key in found:
            console.print(f"[yellow]Skipping {_esc(str(CUSTOM_PRESETS_DIR / key))}.json: a preset that "
                          f"ships with remanga already has that name.[/]")
        else:
            found[key] = preset
    return {key: preset for key, preset in found.items() if preset is not None}


def preset_named(name: str) -> NarrationPreset | None:
    """The preset with this id, or None for "" (no preset) or a missing file."""
    return load_presets().get(name) if name else None


def preset_id(name: str) -> str:
    """The file name a preset called `name` is saved under."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def name_problem(name: str) -> str | None:
    """Why a preset can't be saved under this name, or None if it can. A
    saved preset with the same name is fine - saving replaces it."""
    key = preset_id(name)
    if not key:
        return "Use some letters or numbers."
    if (PRESETS_DIR / f"{key}.json").exists():
        return "A preset that ships with remanga has that name - pick another."
    return None


def current_settings(config: RemangaConfig, name: str, description: str = "") -> NarrationPreset:
    """Every setting a preset can hold, as `config` has it now."""
    block, audio = config.tts.engine_block, config.audio
    take = audio.batch_target_minutes if audio.batch_narration else "per_panel"
    return NarrationPreset(
        name=name, description=description, engine=config.tts.engine,
        voice=getattr(block, "voice", None) if "voice" in type(block).model_fields else None,
        speed=getattr(block, "speed", None) if "speed" in type(block).model_fields else None,
        take_length="whole_chapter" if take != "per_panel" and take >= WHOLE_CHAPTER_MINUTES else take,
        compressor=audio.voice_compressor if audio.voice_compressor in ("off", "gentle", "medium", "strong")
        else "off",
        bass_boost_db=audio.voice_bass_boost_db, presence_db=audio.voice_presence_db, limiter=audio.voice_limiter,
        max_gap_ms=audio.max_gap_ms, panel_pause_ms=audio.pause_between_panels_ms,
        loudness_lufs=audio.loudness_target_lufs if audio.enable_loudnorm else "off")


def save_custom(preset: NarrationPreset) -> str:
    """Writes `preset` to global/presets/ and returns its id."""
    problem = name_problem(preset.name)
    if problem:
        raise ValueError(problem)
    key = preset_id(preset.name)
    CUSTOM_PRESETS_DIR.mkdir(parents=True, exist_ok=True)
    write_json(CUSTOM_PRESETS_DIR / f"{key}.json", preset.model_dump(exclude_none=True))
    return key
