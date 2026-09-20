"""Configuration: one settings model per subsystem, and RemangaConfig (root.py)
holding them all with config.json load/save and per-project overrides."""

from __future__ import annotations

from .audio import AudioConfig
from .cropper import CropperConfig
from .downloader import DownloaderConfig
from .marker import MarkerConfig, ShortcutsConfig
from .pdf import PdfConfig
from .reviewer import ReviewerConfig
from .root import RemangaConfig
from .subtitles import SubtitlesConfig
from .system import SystemConfig
from .tts import TTSConfig
from .video import VideoConfig
from .writer import WriterConfig

__all__ = [
    "AudioConfig",
    "CropperConfig",
    "DownloaderConfig",
    "MarkerConfig",
    "PdfConfig",
    "RemangaConfig",
    "ReviewerConfig",
    "ShortcutsConfig",
    "SubtitlesConfig",
    "SystemConfig",
    "TTSConfig",
    "VideoConfig",
    "WriterConfig",
]
