"""Reusable validators that ensure a RemangaConfig has valid voice/BGM/vision-format settings,
prompting interactively to fix them when they're missing. Used both by the CLI/wizard and by
the audio pipeline stages that depend on these settings being valid before they run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.prompt import Confirm, Prompt

from remanga.config import RemangaConfig
from remanga.console import console, display_path


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
    current = (config.cropper.primary_archive_format or "").strip().lower()
    if current in ("sheets", "panels"):
        return current

    if not interactive:
        config.cropper.primary_archive_format = "panels"
        return "panels"

    console.print(
        "\n[bold yellow]🖼️  LLM Vision Asset Upload Format[/]\n"
        "Choose how cropped manga artwork is packaged for your LLM:\n"
        "  1. [bold cyan]Individual Panels (panels.zip)[/] — Individual high-resolution cropped panel files (Default)\n"
        "  2. [bold cyan]Contact Sheets (sheets.zip)[/] — 2x2 labeled grid sheets (lowest vision token cost)\n"
    )
    choice = Prompt.ask("[bold cyan]Choose vision packaging format[/]", choices=["1", "2"], default="1").strip()
    config.cropper.primary_archive_format = "sheets" if choice == "2" else "panels"

    config.save()
    console.print(f"[bold green]✓ Vision asset format set to '{config.cropper.primary_archive_format}' ({config.cropper.expected_zip_name}) and saved to config.json![/]\n")
    return config.cropper.primary_archive_format


def bundle_state_str(bundle, enabled: bool, split_enabled: bool) -> str:
    if split_enabled:
        return f"on, split at {bundle.max_mb:g}MB"
    return "on, unsplit" if enabled else "off"


def _ask_bundle_checklist(label: str, single_hint: str, split_hint: str, enabled: bool, split_enabled: bool) -> tuple[bool, bool]:
    """Each format is a checklist of two independent things to generate, not
    a mode to pick - see LLMBundleConfig's docstring. Both questions are
    always asked, regardless of how the other was answered, so checking or
    unchecking one never silently loses the other's setting."""
    console.print(f"\n[bold]{label}[/]")
    enabled = Confirm.ask(f"  Generate a single file ({single_hint})?", default=enabled)
    split_enabled = Confirm.ask(f"  Generate it split into size-capped parts ({split_hint})?", default=split_enabled)
    return enabled, split_enabled


def configure_llm_bundle_formats(config: RemangaConfig) -> None:
    """The 'what should get zipped' menu: an interactive checklist over every
    LLM upload bundle format (panels_zip, panels_pdf, sheets_zip - see
    LLMBundleConfig), so the user can control exactly what gets built - e.g.
    "only the PDF, not the zip" is just answering yes to one question and no
    to the rest, not a hidden config.json edit. Shared by `remanga
    setup-config` (step 3, part of the full settings walkthrough) and the
    main interactive wizard's own "adjust LLM upload bundles" prompt, so
    there's one place a user can reach this without needing to know
    setup-config exists separately. Saves config.json itself, like every
    other ensure_valid_*/configure_* helper in this module."""
    console.print(
        "\n[bold yellow]📦 LLM Upload Bundles[/]\n"
        "[dim]Extra archives just for uploading to an LLM chat interface, losslessly re-encoded "
        "smaller - independent of the primary archive (cropper.primary_archive_enabled), never "
        "replacing it or panels/ (still full quality, still what video rendering reads). Check "
        "only what you actually want built - e.g. just the PDF and nothing else is a valid answer.[/]"
    )
    bundle = config.cropper.llm_bundle

    bundle.panels_zip_enabled, bundle.panels_zip_split_enabled = _ask_bundle_checklist(
        "ZIP bundle [dim](single file on by default - individual panels, a safe, no-downside win for LLM upload)[/]",
        "panels_zip/panels_1.zip", "panels_zip/panels_1.zip, panels_2.zip, ...",
        bundle.panels_zip_enabled, bundle.panels_zip_split_enabled,
    )
    bundle.panels_pdf_enabled, bundle.panels_pdf_split_enabled = _ask_bundle_checklist(
        "PDF bundle [dim](off by default - individual panels, one per page)[/]",
        "panels_pdf/panels_1.pdf", "panels_pdf/panels_1.pdf, panels_2.pdf, ...",
        bundle.panels_pdf_enabled, bundle.panels_pdf_split_enabled,
    )
    bundle.sheets_zip_enabled, bundle.sheets_zip_split_enabled = _ask_bundle_checklist(
        "SHEETS ZIP bundle [dim](off by default - full-resolution 2x2 contact sheet composites, not individual panels)[/]",
        "sheets_zip/sheets_1.zip", "sheets_zip/sheets_1.zip, sheets_2.zip, ...",
        bundle.sheets_zip_enabled, bundle.sheets_zip_split_enabled,
    )

    if bundle.panels_zip_split_enabled or bundle.panels_pdf_split_enabled or bundle.sheets_zip_split_enabled:
        max_mb_str = Prompt.ask("[bold cyan]Size cap per part, in MB[/]", default=str(bundle.max_mb))
        try:
            bundle.max_mb = float(max_mb_str)
        except ValueError:
            console.print(f"[yellow]Not a number, keeping {bundle.max_mb:g}MB.[/]")

    config.save()
    console.print(
        f"[bold green]✓ LLM upload bundles saved:[/] "
        f"ZIP {bundle_state_str(bundle, bundle.panels_zip_enabled, bundle.panels_zip_split_enabled)} | "
        f"PDF {bundle_state_str(bundle, bundle.panels_pdf_enabled, bundle.panels_pdf_split_enabled)} | "
        f"SHEETS ZIP {bundle_state_str(bundle, bundle.sheets_zip_enabled, bundle.sheets_zip_split_enabled)}\n"
    )


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
            console.print(f"[bold green]✓ Reference voice verified and saved to config.json:[/] {display_path(valid)}\n")
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
            console.print(f"[bold green]✓ BGM verified and saved to config.json:[/] {display_path(valid)}\n")
            return str(valid.resolve())
        else:
            console.print(f"[bold red]✗ Audio file not found:[/] {Path(user_input).expanduser()}. Please try again.")
