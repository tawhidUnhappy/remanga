from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from rich.console import Console
from rich.prompt import Prompt, Confirm

console = Console()


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
    temperature: float = 0.7
    top_p: float = 0.85
    sample_rate: int = 22050
    emotion_vectors: Dict[str, List[float]] = Field(
        default_factory=lambda: {
            "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.8],
            "hype": [0.7, 0.3, 0.0, 0.0, 0.0, 0.4, 0.0, 0.0],
            "tense": [0.0, 0.2, 0.1, 0.6, 0.0, 0.5, 0.0, 0.1],
            "serious": [0.0, 0.1, 0.2, 0.0, 0.0, 0.1, 0.6, 0.3],
            "shock": [0.0, 0.1, 0.0, 0.4, 0.0, 0.9, 0.0, 0.0],
            "emotional": [0.1, 0.0, 0.7, 0.1, 0.0, 0.2, 0.2, 0.1],
            "mysterious": [0.0, 0.0, 0.1, 0.3, 0.0, 0.3, 0.5, 0.2],
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

    def ensure_valid_voice_prompt(self, interactive: bool = True) -> str:
        """
        Validates the configured reference voice WAV path.
        If missing or invalid, prompts the user via terminal in a loop until a valid path is given,
        then automatically saves it to config.json.
        """
        raw_path = self.tts.spk_audio_prompt.strip()
        if raw_path:
            p = Path(raw_path).expanduser()
            if p.exists() and p.is_file() and p.stat().st_size > 0:
                return str(p.resolve())

        if not interactive:
            raise FileNotFoundError(
                f"Invalid or missing reference voice file: '{raw_path}'. "
                f"Please set a valid WAV file in config.json under 'tts.spk_audio_prompt'."
            )

        console.print(
            "\n[bold yellow]🎙️  IndexTTS-2.5 Speaker Voice Setup[/]\n"
            "A clean 3-10 second reference WAV audio file is required for zero-shot speaker cloning.\n"
            f"[dim]Current setting: '{raw_path or 'Not configured'}'[/]"
        )

        while True:
            user_input = Prompt.ask("[bold cyan]Enter absolute or relative path to your reference voice WAV file[/]").strip().strip("'\"")
            if not user_input:
                console.print("[red]Path cannot be empty. Please enter a valid path.[/]")
                continue

            test_path = Path(user_input).expanduser()
            if test_path.exists() and test_path.is_file() and test_path.stat().st_size > 0:
                self.tts.spk_audio_prompt = str(test_path)
                self.save()
                console.print(f"[bold green]✓ Reference voice verified and saved to config.json:[/] {test_path.resolve()}\n")
                return str(test_path.resolve())
            else:
                console.print(f"[bold red]✗ File not found or empty:[/] {test_path}. Please try again.")

    def ensure_valid_bgm(self, interactive: bool = True) -> Optional[str]:
        """
        Validates background music configuration.
        If enabled but path is invalid, interactively prompts for path or allows disabling BGM.
        """
        if not self.audio.bgm_enabled:
            return None

        raw_path = self.audio.bgm_path.strip()
        if raw_path:
            p = Path(raw_path).expanduser()
            if p.exists() and p.is_file():
                return str(p.resolve())

        if not interactive:
            console.print(f"[yellow]BGM is enabled but file '{raw_path}' was not found. Proceeding without BGM.[/]")
            return None

        console.print(
            "\n[bold yellow]🎵 Background Music (BGM) Setup[/]\n"
            "BGM is enabled in your configuration, but the audio file path is missing or invalid.\n"
        )

        wants_bgm = Confirm.ask("Would you like to configure a background music file now?", default=True)
        if not wants_bgm:
            self.audio.bgm_enabled = False
            self.save()
            console.print("[yellow]BGM disabled for this chapter.[/]\n")
            return None

        while True:
            user_input = Prompt.ask("[bold cyan]Enter path to your BGM audio file (or press Enter to skip)[/]").strip().strip("'\"")
            if not user_input:
                self.audio.bgm_enabled = False
                self.save()
                console.print("[yellow]Skipping BGM. BGM disabled in config.json.[/]\n")
                return None

            test_path = Path(user_input).expanduser()
            if test_path.exists() and test_path.is_file():
                self.audio.bgm_path = str(test_path)
                self.audio.bgm_enabled = True
                self.save()
                console.print(f"[bold green]✓ BGM verified and saved to config.json:[/] {test_path.resolve()}\n")
                return str(test_path.resolve())
            else:
                console.print(f"[bold red]✗ Audio file not found:[/] {test_path}. Please try again.")


def get_project_dir(project_name: str) -> Path:
    clean_proj = str(project_name).strip().replace("/", "_").replace("\\", "_")
    return Path("projects") / clean_proj


def get_chapter_dir(project_name: str, chapter_num: str) -> Path:
    clean_chap = str(chapter_num).strip().replace("/", "_").replace("\\", "_")
    return get_project_dir(project_name) / "chapters" / f"chapter_{clean_chap}"


def get_project_metadata_path(project_name: str) -> Path:
    return get_project_dir(project_name) / "project.json"


def load_project_metadata(project_name: str) -> Dict[str, Any]:
    meta_path = get_project_metadata_path(project_name)
    if meta_path.exists():
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_project_metadata(project_name: str, data: Dict[str, Any]) -> None:
    meta_path = get_project_metadata_path(project_name)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    existing = load_project_metadata(project_name)
    existing.update(data)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2)