"""RemangaConfig: the top-level aggregate of every subsystem's config below,
plus config.json load/save. See remanga/config/__init__.py for the flat
import surface every other module actually uses."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from remanga.json_io import read_json, write_json
from remanga.paths import CONFIG_EXAMPLE_PATH, CONFIG_PATH

from .audio import AudioConfig
from .cropper import CropperConfig
from .downloader import DownloaderConfig
from .marker import MarkerConfig
from .ocr import OCRConfig
from .reviewer import ReviewerConfig
from .system import SystemConfig
from .tts import TTSConfig
from .video import VideoConfig
from .writer import WriterConfig


class RemangaConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    cropper: CropperConfig = Field(default_factory=CropperConfig)
    marker: MarkerConfig = Field(default_factory=MarkerConfig)
    reviewer: ReviewerConfig = Field(default_factory=ReviewerConfig)
    writer: WriterConfig = Field(default_factory=WriterConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)

    @classmethod
    def load(cls, config_path: Optional[Path | str] = None) -> "RemangaConfig":
        """Load configuration from JSON file or create with defaults."""
        target_path = Path(config_path) if config_path else CONFIG_PATH
        if not target_path.exists():
            target_path = CONFIG_EXAMPLE_PATH

        if target_path.exists():
            return cls.model_validate(read_json(target_path))
        return cls()

    def save(self, output_path: Path | str = CONFIG_PATH) -> None:
        """Save current configuration to a JSON file."""
        write_json(output_path, self.model_dump())
