"""Narration presets: a whole narration sound in one JSON file, picked in
Settings as "Narration preset".

Each file in presets/ is one preset (the file name, without .json, is its
id). A preset fixes the settings it names - engine, voice, speed, take
length, the voice chain, loudness - and leaves every setting it doesn't name
to its own row. While one is picked, the rows it fixes are shown but locked
(ui/screens/settings.py); "No preset" hands every row back. A new sound is a
new file, not new code. presets/README.md lists the keys.

The preset is applied whenever the config is loaded (RemangaConfig), so
whatever config.json says, the picked preset wins - for every chapter."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, ValidationError

from remanga import plugins
from remanga.console import console, escape as _esc
from remanga.json_io import read_json
from remanga.paths import REPO_ROOT

if TYPE_CHECKING:
    from remanga.config.root import RemangaConfig

PRESETS_DIR = REPO_ROOT / "presets"

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
    limiter: bool | None = None
    # A target in LUFS, or "off" for no loudness pass.
    loudness_lufs: float | Literal["off"] | None = None

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
        if self.limiter is not None:
            keys.add("audio.voice_limiter")
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
        if self.limiter is not None:
            audio.voice_limiter = self.limiter
        if self.loudness_lufs == "off":
            audio.enable_loudnorm = False
        elif self.loudness_lufs is not None:
            audio.enable_loudnorm, audio.loudness_target_lufs = True, self.loudness_lufs


# Parsed files by (path, mtime): the config loads often, and a broken file
# should be reported once, not on every load.
_cache: dict[tuple[Path, float], NarrationPreset | None] = {}


def _read(path: Path) -> NarrationPreset | None:
    key = (path, path.stat().st_mtime)
    if key not in _cache:
        try:
            _cache[key] = NarrationPreset.model_validate(read_json(path))
        except (ValidationError, ValueError, OSError) as e:
            console.print(f"[yellow]Skipping narration preset {_esc(path.name)}: {_esc(str(e))}[/]")
            _cache[key] = None
    return _cache[key]


def load_presets(folder: Path = PRESETS_DIR) -> dict[str, NarrationPreset]:
    """Every readable preset, by id (file name without .json), in name order."""
    found = {path.stem: _read(path) for path in sorted(folder.glob("*.json"))} if folder.is_dir() else {}
    return {key: preset for key, preset in found.items() if preset is not None}


def preset_named(name: str) -> NarrationPreset | None:
    """The preset with this id, or None for "" (no preset) or a missing file."""
    return load_presets().get(name) if name else None
