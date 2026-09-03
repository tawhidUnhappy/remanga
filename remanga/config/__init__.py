"""Configuration: was one 400-line config.py holding every subsystem's
Pydantic settings model back to back; split into one file per subsystem
(system/downloader/cropper/tts/audio/video/marker/reviewer) plus root.py for
the RemangaConfig aggregate + config.json load/save, since each subsystem's
model is independent of every other one and only ever changes for its own
reasons. This module re-exports the full flat surface every other file in
the codebase already imports from `remanga.config` - `from remanga.config
import X` keeps working unchanged for every X below; nothing outside this
package needs to know it's a package now."""

from __future__ import annotations

from .audio import AudioConfig
from .cropper import CropperConfig, PackageConfig
from .downloader import DownloaderConfig
from .marker import MarkerConfig, ShortcutsConfig
from .ocr import OCRConfig
from .reviewer import ReviewerConfig
from .root import RemangaConfig
from .system import SystemConfig
from .tts import TTS_ENGINES, Audio8Config, TTSConfig
from .video import VideoConfig
from .writer import WriterConfig

__all__ = [
    "AudioConfig",
    "Audio8Config",
    "CropperConfig",
    "DownloaderConfig",
    "MarkerConfig",
    "OCRConfig",
    "PackageConfig",
    "RemangaConfig",
    "ReviewerConfig",
    "ShortcutsConfig",
    "SystemConfig",
    "TTSConfig",
    "TTS_ENGINES",
    "VideoConfig",
    "WriterConfig",
]
