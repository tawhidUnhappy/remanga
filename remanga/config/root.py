"""RemangaConfig: every subsystem's settings, loaded from and saved to
config.json.

One set of settings for every project (user request, 2026-10-01: per-project
overrides confused - a project quietly kept its own voice or music while the
Settings screen showed the defaults). Older project.json files may still
carry a "settings" block; nothing reads it any more."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, model_validator

from remanga.config.base import ConfigModel
from remanga.json_io import read_json, write_json
from remanga.paths import (
    CONFIG_EXAMPLE_PATH,
    CONFIG_PATH,
)

from .audio import AudioConfig
from .cropper import CropperConfig
from .downloader import DownloaderConfig
from .marker import MarkerConfig, ShortcutsConfig
from .menus import MenusConfig
from .pdf import PdfConfig
from .presets import DEFAULT_PRESET, preset_named
from .reviewer import ReviewerConfig
from .subtitles import SubtitlesConfig
from .system import SystemConfig
from .tts import TTSConfig
from .video import VideoConfig
from .writer import WriterConfig


class RemangaConfig(ConfigModel):
    # The narration preset in use: a file in presets/ by name (config/presets.py),
    # or "" for none - every narration setting then comes from its own row.
    narration_preset: str = DEFAULT_PRESET
    system: SystemConfig = Field(default_factory=SystemConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    pdf: PdfConfig = Field(default_factory=PdfConfig)
    cropper: CropperConfig = Field(default_factory=CropperConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    shortcuts: ShortcutsConfig = Field(default_factory=ShortcutsConfig)
    reviewer: ReviewerConfig = Field(default_factory=ReviewerConfig)
    writer: WriterConfig = Field(default_factory=WriterConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    subtitles: SubtitlesConfig = Field(default_factory=SubtitlesConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)
    menus: MenusConfig = Field(default_factory=MenusConfig)

    @model_validator(mode="after")
    def _apply_preset(self) -> RemangaConfig:
        """The picked preset over whatever config.json holds, on every load."""
        self.apply_preset()
        return self

    def apply_preset(self) -> None:
        preset = preset_named(self.narration_preset)
        if preset is not None:
            preset.apply(self)

    @classmethod
    def load(cls, config_path: Path | str | None = None) -> RemangaConfig:
        """Load configuration from JSON file or create with defaults."""
        target_path = Path(config_path) if config_path else CONFIG_PATH
        if not target_path.exists():
            target_path = CONFIG_EXAMPLE_PATH

        if target_path.exists():
            return cls.model_validate(read_json(target_path))
        return cls()

    def save(self, output_path: Path | str = CONFIG_PATH) -> None:
        """Writes the configuration to config.json."""
        write_json(output_path, self.model_dump())
