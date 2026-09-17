"""Configuration: one settings model per subsystem, and RemangaConfig (root.py)
holding them all with config.json load/save and per-project overrides."""

from __future__ import annotations

from .audio import AudioConfig
from .downloader import DownloaderConfig
from .pdf import PdfConfig
from .root import RemangaConfig
from .system import SystemConfig
from .tts import TTSConfig
from .video import VideoConfig

__all__ = [
    "AudioConfig",
    "DownloaderConfig",
    "PdfConfig",
    "RemangaConfig",
    "SystemConfig",
    "TTSConfig",
    "VideoConfig",
]
