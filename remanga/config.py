from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class SystemConfig(BaseModel):
    prefer_gpu: bool = True
    gpu_codec: str = "h264_nvenc"
    fallback_codec: str = "libx264"
    threads: int = 4
    log_level: str = "INFO"


class DownloaderConfig(BaseModel):
    language: str = "en"
    image_quality: str = "data"  # 'data' (high quality) or 'data-saver'
    max_retries: int = 3
    retry_delay_seconds: int = 2


class CropperConfig(BaseModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"


class TTSConfig(BaseModel):
    engine: str = "edge-tts"
    voice: str = "en-US-ChristopherNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    volume: str = "+0%"


class AudioConfig(BaseModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    pause_between_panels_ms: int = 300
    bgm_enabled: bool = False
    bgm_path: str = "assets/bgm/default_recap.mp3"
    bgm_volume_db: float = -22.0
    enable_loudnorm: bool = True


class VideoConfig(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    background_color: str = "#000000"
    panel_padding_percent: int = 3
    render_subtitles: bool = True
    font_name: str = "DejaVuSans-Bold"
    font_size: int = 48
    subtitle_color: str = "&H00FFFFFF"
    subtitle_outline_color: str = "&H00000000"
    subtitle_outline_width: int = 3
    subtitle_bottom_margin: int = 60


class RemangaConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    downloader: DownloaderConfig = Field(default_factory=DownloaderConfig)
    cropper: CropperConfig = Field(default_factory=CropperConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    video: VideoConfig = Field(default_factory=VideoConfig)

    @classmethod
    def load(cls, config_path: Optional[Path | str] = None) -> "RemangaConfig":
        """Load configuration from JSON file or create with defaults."""
        target_path = Path(config_path) if config_path else Path("config.json")
        if not target_path.exists():
            target_path = Path("config.example.json")

        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        return cls()

    def save(self, output_path: Path | str = "config.json") -> None:
        """Save current configuration to a JSON file."""
        target_path = Path(output_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(self.model_dump(), f, indent=2)


def get_chapter_dir(project_name: str, chapter_num: str) -> Path:
    """Return standard workspace directory path for a specific chapter."""
    clean_chap = str(chapter_num).strip().replace("/", "_").replace("\\", "_")
    return Path("projects") / project_name / "chapters" / f"chapter_{clean_chap}"