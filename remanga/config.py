from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional
from pydantic import BaseModel, Field

from remanga.json_io import read_json, write_json


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
    request_delay_seconds: float = 0.35
    create_zip: bool = True


class CropperConfig(BaseModel):
    margin_padding_pixels: int = 8
    auto_contrast_clean: bool = False
    save_format: str = "PNG"
    vision_asset_type: str = "sheets"  # 'sheets' (2x2 contact sheets) or 'panels' (individual panel crops)
    create_sheets: bool = True
    panels_per_sheet: int = 4
    create_zip: bool = True
    zip_filename: str = "sheets.zip"


class TTSConfig(BaseModel):
    engine: str = "indextts-2.5"
    hf_repo_id: str = "IndexTeam/IndexTTS-2.5"
    model_dir: str = "checkpoints/indextts_2.5"
    cfg_path: str = "checkpoints/indextts_2.5/config.yaml"
    spk_audio_prompt: str = ""
    lang: str = "EN"
    use_bf16: bool = True
    speed: float = 1.0
    temperature: float = 0.2  # Low temperature prevents stochastic pitch inflections
    top_p: float = 0.7        # Tight nucleus sampling keeps vocal prosody stable
    sample_rate: int = 22050
    emotion_vectors: Dict[str, List[float]] = Field(
        default_factory=lambda: {
            "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "hype": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "tense": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "serious": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "shock": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "emotional": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "mysterious": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        }
    )


class AudioConfig(BaseModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    pause_between_panels_ms: int = 300
    bgm_enabled: bool = False
    bgm_path: str = ""
    bgm_volume_db: float = -22.0
    enable_loudnorm: bool = True


class VideoConfig(BaseModel):
    width: int = 1920
    height: int = 1080
    fps: int = 30
    background_style: str = "blur"  # 'blur' (Fast bokeh blur) or 'solid' (black canvas)
    blur_brightness: float = 0.42   # Dimming multiplier for canvas blur (0.35 to 0.55 recommended)
    background_color: str = "#000000"
    panel_padding_percent: int = 4
    auto_adaptive_padding: bool = True
    panel_border_width: int = 2
    panel_border_color: str = "#222222"


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
            return cls.model_validate(read_json(target_path))
        return cls()

    def save(self, output_path: Path | str = "config.json") -> None:
        """Save current configuration to a JSON file."""
        write_json(output_path, self.model_dump())
