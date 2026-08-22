"""Reusable validators that ensure a RemangaConfig has valid voice/BGM/vision-format settings,
prompting interactively to fix them when they're missing. Used both by the CLI/wizard and by
the audio pipeline stages that depend on these settings being valid before they run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt

from remanga.config import RemangaConfig

console = Console()


def is_valid_file(raw_path: str, min_size: int = 0) -> Optional[Path]:
    """Returns the resolved Path if `raw_path` points at an existing, non-empty-enough file, else None."""
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return None
    p = Path(raw_path).expanduser()
    if p.exists() and p.is_file() and p.stat().st_size >= min_size:
        return p
    return None


def ensure_valid_vision_asset_preference(config: RemangaConfig, interactive: bool = True) -> str:
    """Ensures the vision package format ('sheets' vs 'panels') is configured and saved."""
    current = (config.cropper.vision_asset_type or "").strip().lower()
    if current in ("sheets", "panels"):
        return current

    if not interactive:
        config.cropper.vision_asset_type = "sheets"
        return "sheets"

    console.print(
        "\n[bold yellow]🖼️  LLM Vision Asset Upload Format[/]\n"
        "Choose how cropped manga artwork is packaged for your LLM:\n"
        "  1. [bold cyan]Contact Sheets (sheets.zip)[/] — 2x2 labeled grid sheets (Recommended, lowest vision token cost)\n"
        "  2. [bold cyan]Individual Panels (panels.zip)[/] — Individual high-resolution cropped panel files\n"
    )
    choice = Prompt.ask("[bold cyan]Choose vision packaging format[/]", choices=["1", "2"], default="1").strip()
    config.cropper.vision_asset_type = "panels" if choice == "2" else "sheets"

    config.save()
    console.print(f"[bold green]✓ Vision asset format set to '{config.cropper.vision_asset_type}' ({config.cropper.expected_zip_name}) and saved to config.json![/]\n")
    return config.cropper.vision_asset_type


def ensure_valid_voice_prompt(config: RemangaConfig, interactive: bool = True) -> str:
    raw_path = config.tts.spk_audio_prompt.strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

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
        valid = is_valid_file(user_input, min_size=1)
        if valid:
            config.tts.spk_audio_prompt = str(valid)
            config.save()
            console.print(f"[bold green]✓ Reference voice verified and saved to config.json:[/] {valid.resolve()}\n")
            return str(valid.resolve())
        elif not user_input:
            console.print("[red]Path cannot be empty. Please enter a valid path.[/]")
        else:
            console.print(f"[bold red]✗ File not found or empty:[/] {Path(user_input).expanduser()}. Please try again.")


def ensure_valid_bgm(config: RemangaConfig, interactive: bool = True) -> Optional[str]:
    if not config.audio.bgm_enabled:
        return None

    raw_path = config.audio.bgm_path.strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

    if not interactive:
        console.print(f"[yellow]BGM is enabled but file '{raw_path}' was not found. Proceeding without BGM.[/]")
        return None

    console.print(
        "\n[bold yellow]🎵 Background Music (BGM) Setup[/]\n"
        "BGM is enabled in your configuration, but the audio file path is missing or invalid.\n"
    )

    wants_bgm = Confirm.ask("Would you like to configure a background music file now?", default=True)
    if not wants_bgm:
        config.audio.bgm_enabled = False
        config.save()
        console.print("[yellow]BGM disabled for this chapter.[/]\n")
        return None

    while True:
        user_input = Prompt.ask("[bold cyan]Enter path to your BGM audio file (or press Enter to skip)[/]").strip().strip("'\"")
        if not user_input:
            config.audio.bgm_enabled = False
            config.save()
            console.print("[yellow]Skipping BGM. BGM disabled in config.json.[/]\n")
            return None

        valid = is_valid_file(user_input)
        if valid:
            config.audio.bgm_path = str(valid)
            config.audio.bgm_enabled = True
            config.save()
            console.print(f"[bold green]✓ BGM verified and saved to config.json:[/] {valid.resolve()}\n")
            return str(valid.resolve())
        else:
            console.print(f"[bold red]✗ Audio file not found:[/] {Path(user_input).expanduser()}. Please try again.")
