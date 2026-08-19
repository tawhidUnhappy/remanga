from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.table import Table

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
    background_style: str = "blur"  # 'blur' (CapCut-style fast bokeh blur) or 'solid' (black canvas)
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

    def run_setup_wizard(self) -> "RemangaConfig":
        """
        Interactive step-by-step configuration wizard.
        Guides the user through Voice reference, BGM, YouTube quality/resolution, canvas blur, and rendering.
        """
        console.print(Panel(
            "[bold cyan]⚙️  remanga Production Settings Setup Wizard[/]\n"
            "[dim]Configure vocal reference, background music, video resolution, and canvas background style.[/]",
            border_style="cyan"
        ))

        # 1. Reference Vocal Audio (Voice Cloning)
        console.print("\n[bold yellow]1. Reference Speaker Voice (IndexTTS-2.5 Cloning)[/]")
        console.print("[dim]Provide a clean 3-10 second WAV file of the target voice.[/]")
        curr_voice = self.tts.spk_audio_prompt
        if curr_voice and Path(curr_voice).expanduser().exists():
            console.print(f"Current Voice: [green]{curr_voice}[/]")
            if Confirm.ask("Keep current reference voice?", default=True):
                pass
            else:
                self.ensure_valid_voice_prompt(interactive=True)
        else:
            self.ensure_valid_voice_prompt(interactive=True)

        # 2. Voice Language Selection
        console.print("\n[bold yellow]2. Voice Language[/]")
        lang_table = Table(border_style="blue", show_header=True)
        lang_table.add_column("#", style="bold yellow", width=4)
        lang_table.add_column("Language", style="bold white")
        lang_table.add_column("Code", style="cyan")

        languages = [
            ("1", "English", "EN"),
            ("2", "Japanese", "JA"),
            ("3", "Chinese (Mandarin)", "ZH"),
            ("4", "Spanish", "ES"),
            ("5", "Arabic", "AR"),
        ]
        for num, name, code in languages:
            lang_table.add_row(num, name, code)
        console.print(lang_table)

        curr_lang = self.tts.lang.upper()
        default_lang_num = next((num for num, _, code in languages if code == curr_lang), "1")
        lang_choice = Prompt.ask("[bold cyan]Select narration language[/]", default=default_lang_num).strip()
        matched_lang = next((code for num, _, code in languages if num == lang_choice or code.lower() == lang_choice.lower()), "EN")
        self.tts.lang = matched_lang
        console.print(f"[green]✓ Language set to:[/] {matched_lang}")

        # 3. Background Music (BGM)
        console.print("\n[bold yellow]3. Background Music (BGM)[/]")
        enable_bgm = Confirm.ask("Enable background music track for recaps?", default=self.audio.bgm_enabled)
        self.audio.bgm_enabled = enable_bgm
        if enable_bgm:
            while True:
                curr_bgm = self.audio.bgm_path or ""
                bgm_input = Prompt.ask("[bold cyan]Enter path to BGM audio file (MP3/WAV/AAC)[/]", default=curr_bgm).strip().strip("'\"")
                if bgm_input:
                    p = Path(bgm_input).expanduser()
                    if p.exists() and p.is_file():
                        self.audio.bgm_path = str(p.resolve())
                        console.print(f"[green]✓ BGM path saved:[/] {self.audio.bgm_path}")
                        break
                    else:
                        console.print(f"[red]File not found:[/] {p}. Please enter a valid file path.")
                else:
                    self.audio.bgm_enabled = False
                    console.print("[yellow]No path entered. BGM disabled.[/]")
                    break

            if self.audio.bgm_enabled:
                vol_str = Prompt.ask("[bold cyan]BGM Volume Gain in dB (recommended -22 to -18 dB)[/]", default=str(self.audio.bgm_volume_db))
                try:
                    self.audio.bgm_volume_db = float(vol_str)
                except ValueError:
                    self.audio.bgm_volume_db = -22.0

        # 4. YouTube Quality / Video Resolution Presets
        console.print("\n[bold yellow]4. YouTube Quality & Video Resolution[/]")
        res_table = Table(title="Available Resolution Presets", border_style="blue")
        res_table.add_column("#", style="bold yellow", width=4)
        res_table.add_column("Preset Quality", style="bold white")
        res_table.add_column("Resolution", style="cyan")
        res_table.add_column("Description", style="dim")

        resolutions = [
            ("1", "1080p Full HD", "1920x1080", "Standard YouTube 1080p broadcast [Recommended]", 1920, 1080),
            ("2", "1440p 2K QHD", "2560x1440", "High clarity & higher YouTube VP9/AV1 bitrate allocation", 2560, 1440),
            ("3", "2160p 4K UHD", "3840x2160", "Maximum ultra HD clarity & master render quality", 3840, 2160),
            ("4", "720p HD", "1280x720", "Ultra-fast rendering / lightweight preview quality", 1280, 720),
            ("5", "Custom", "Custom", "Specify custom width and height", 0, 0),
        ]

        for num, title, res, desc, _, _ in resolutions:
            res_table.add_row(num, title, res, desc)
        console.print(res_table)

        curr_res_str = f"{self.video.width}x{self.video.height}"
        default_res_num = next((num for num, _, res, _, _, _ in resolutions if res == curr_res_str), "1")

        res_choice = Prompt.ask("[bold cyan]Choose video resolution preset[/]", default=default_res_num).strip()
        selected_preset = next((item for item in resolutions if item[0] == res_choice), resolutions[0])

        if selected_preset[0] == "5":
            w = int(Prompt.ask("Enter width in pixels", default="1920"))
            h = int(Prompt.ask("Enter height in pixels", default="1080"))
            self.video.width = w
            self.video.height = h
        else:
            _, _, _, _, w, h = selected_preset
            self.video.width = w
            self.video.height = h

        console.print(f"[green]✓ Resolution configured:[/] {self.video.width}x{self.video.height}")

        # 5. Canvas Background Style (CapCut Blur vs Solid Black)
        console.print("\n[bold yellow]5. Canvas Background Style[/]")
        bg_table = Table(border_style="blue")
        bg_table.add_column("#", style="bold yellow", width=4)
        bg_table.add_column("Background Style", style="bold white")
        bg_table.add_column("Description", style="dim")

        bg_styles = [
            ("1", "CapCut-Style Fast Bokeh Canvas Blur", "Dynamic blurred background of the current panel (<1.5ms) [Recommended]"),
            ("2", "Solid Black Canvas", "Traditional solid black background (#000000)"),
        ]
        for num, title, desc in bg_styles:
            bg_table.add_row(num, title, desc)
        console.print(bg_table)

        default_bg_num = "1" if self.video.background_style == "blur" else "2"
        bg_choice = Prompt.ask("[bold cyan]Choose background style[/]", default=default_bg_num).strip()
        if bg_choice == "2":
            self.video.background_style = "solid"
            console.print("[green]✓ Background set to:[/] Solid Black (#000000)")
        else:
            self.video.background_style = "blur"
            console.print("[green]✓ Background set to:[/] CapCut-Style Fast Bokeh Canvas Blur")

        # 6. Hardware Acceleration
        console.print("\n[bold yellow]6. Hardware Acceleration[/]")
        self.system.prefer_gpu = Confirm.ask("Prefer NVIDIA GPU Hardware Acceleration (NVENC)?", default=self.system.prefer_gpu)

        # Save Configuration
        self.save()

        summary_table = Table(title="[bold green]✓ Updated Production Settings (config.json)[/]", border_style="green")
        summary_table.add_column("Setting", style="bold white")
        summary_table.add_column("Value", style="cyan")

        summary_table.add_row("Resolution", f"{self.video.width}x{self.video.height} @ {self.video.fps}fps")
        summary_table.add_row("Background Style", f"{self.video.background_style.title()} (Bokeh Canvas Blur)" if self.video.background_style == "blur" else "Solid Black")
        summary_table.add_row("Narration Language", self.tts.lang.upper())
        summary_table.add_row("Reference Speaker Voice", str(Path(self.tts.spk_audio_prompt).name) if self.tts.spk_audio_prompt else "[red]Not configured[/]")
        summary_table.add_row("Background Music (BGM)", f"Enabled ({Path(self.audio.bgm_path).name}, {self.audio.bgm_volume_db}dB)" if self.audio.bgm_enabled else "Disabled")
        summary_table.add_row("GPU Codec", f"{self.system.gpu_codec} (Fallback: {self.system.fallback_codec})")

        console.print(summary_table)
        console.print("[bold green]All settings successfully saved to config.json![/]\n")
        return self

    def ensure_valid_voice_prompt(self, interactive: bool = True) -> str:
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


def get_projects_dir() -> Path:
    p = Path("projects")
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_project_dir(project_name: str) -> Path:
    clean_proj = str(project_name).strip().replace("/", "_").replace("\\", "_")
    return get_projects_dir() / clean_proj


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


def list_projects() -> List[Dict[str, Any]]:
    root = get_projects_dir()
    results = []
    if not root.exists():
        return results

    for p in sorted(root.iterdir()):
        if p.is_dir():
            meta = load_project_metadata(p.name)
            chapters_dir = p / "chapters"
            chapters = []
            if chapters_dir.exists():
                for c in sorted(chapters_dir.iterdir()):
                    if c.is_dir() and c.name.startswith("chapter_"):
                        ch_num = c.name.replace("chapter_", "")
                        chapters.append(ch_num)
            results.append({
                "name": p.name,
                "path": p,
                "manga_url": meta.get("manga_url", ""),
                "manga_id": meta.get("manga_id", ""),
                "last_chapter": meta.get("last_chapter", ""),
                "chapters": chapters,
            })
    return results


def get_chapter_status(project_name: str, chapter_num: str) -> Dict[str, Any]:
    chap_dir = get_chapter_dir(project_name, chapter_num)
    pages_dir = chap_dir / "pages"
    panels_dir = chap_dir / "panels"
    sheets_dir = chap_dir / "sheets"
    audio_dir = chap_dir / "audio"

    pages_count = len(list(pages_dir.glob("page_*.*"))) if pages_dir.exists() else 0
    pages_zip_exist = (chap_dir / "pages.zip").exists()
    crops_file = chap_dir / "crops.json"
    crops_exist = crops_file.exists() and crops_file.stat().st_size > 10

    panels_count = len(list(panels_dir.glob("panel_*.*"))) if panels_dir.exists() else 0
    sheets_count = len(list(sheets_dir.glob("sheet_*.*"))) if sheets_dir.exists() else 0
    sheets_zip_exist = (chap_dir / "sheets.zip").exists()

    narration_file = chap_dir / "narration.json"
    narration_exist = narration_file.exists() and narration_file.stat().st_size > 10
    total_narration_entries = 0
    if narration_exist:
        try:
            with open(narration_file, "r", encoding="utf-8") as f:
                n_data = json.load(f)
                total_narration_entries = len(n_data.get("narration", []))
        except Exception:
            pass

    audio_clips_count = len(list(audio_dir.glob("panel_*.wav"))) if audio_dir.exists() else 0
    timing_exist = (chap_dir / "audio_timing.json").exists()
    master_audio_exist = (chap_dir / "master_audio.wav").exists()

    final_video_path = chap_dir / f"{project_name}_ch{chapter_num}_recap.mp4"
    video_exist = final_video_path.exists() and final_video_path.stat().st_size > 1000

    if video_exist:
        summary = "Recap Ready"
    elif master_audio_exist:
        summary = "Audio Ready (Pending Render)"
    elif total_narration_entries > 0 and audio_clips_count >= total_narration_entries:
        summary = "TTS Ready (Pending Mix)"
    elif total_narration_entries > 0 and audio_clips_count > 0:
        summary = f"TTS In-Progress ({audio_clips_count}/{total_narration_entries})"
    elif narration_exist:
        summary = "Narration Script Ready"
    elif sheets_zip_exist or panels_count > 0:
        summary = f"Cropped ({panels_count} panels)"
    elif crops_exist:
        summary = "Crops JSON Ready"
    elif pages_count > 0:
        summary = f"Pages Ready ({pages_count} pages)"
    else:
        summary = "Not Started"

    return {
        "project": project_name,
        "chapter": str(chapter_num),
        "chap_dir": chap_dir,
        "pages_count": pages_count,
        "pages_zip_exist": pages_zip_exist,
        "crops_exist": crops_exist,
        "panels_count": panels_count,
        "sheets_count": sheets_count,
        "sheets_zip_exist": sheets_zip_exist,
        "narration_exist": narration_exist,
        "total_narration_entries": total_narration_entries,
        "audio_clips_count": audio_clips_count,
        "timing_exist": timing_exist,
        "master_audio_exist": master_audio_exist,
        "video_exist": video_exist,
        "video_path": final_video_path,
        "summary": summary,
    }