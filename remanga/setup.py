"""Reusable validators that ensure a RemangaConfig has valid voice/BGM settings (prompting
interactively to fix them when they're missing) and the vision-output "what to generate,
what to zip" checklist (configure_vision_outputs). Used both by the CLI/wizard and by the
audio pipeline stages that depend on these settings being valid before they run."""

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


def bundle_state_str(package, enabled: bool, split_enabled: bool) -> str:
    if split_enabled:
        return f"on, split at {package.max_mb:g}MB"
    return "on, unsplit" if enabled else "off"


def _ask_bundle_checklist(label: str, single_hint: str, split_hint: str, enabled: bool, split_enabled: bool) -> tuple[bool, bool]:
    """Each format is a checklist of two independent things to generate, not
    a mode to pick - see PackageConfig's docstring. Both questions are
    always asked, regardless of how the other was answered, so checking or
    unchecking one never silently loses the other's setting."""
    console.print(f"\n[bold]{label}[/]")
    enabled = Confirm.ask(f"  Generate a single file ({single_hint})?", default=enabled)
    split_enabled = Confirm.ask(f"  Generate it split into size-capped parts ({split_hint})?", default=split_enabled)
    return enabled, split_enabled


def configure_vision_outputs(config: RemangaConfig) -> None:
    """The 'what to generate, what to zip' menu: two independent sections,
    matching CropperConfig's `generate`/`package` split -
    1. **Generate** - what visual content to produce at all. Individual
       panel crops (panels/) always exist - that's what cropping a chapter
       means - so the only thing to choose here today is contact sheets.
    2. **Package** - what to zip/PDF up from whatever Section 1 produced,
       for LLM upload (panels_zip, panels_pdf, sheets_zip - see
       PackageConfig) - a checklist, not a mode: e.g. "only the PDF, not
       the zip" is just answering yes to one question and no to the rest,
       not a hidden config.json edit.

    Shared by `remanga setup-config` (step 2/3, part of the full settings
    walkthrough) and the main interactive wizard's own "adjust what gets
    generated/zipped" prompt, so there's one place a user can reach this
    without needing to know setup-config exists separately. Saves
    config.json itself, like every other ensure_valid_*/configure_* helper
    in this module."""
    console.print(
        "\n[bold yellow]🖼️  Section 1: What to Generate[/]\n"
        "[dim]Individual panel crops (panels/) are always produced - that's what cropping a "
        "chapter means. Choose anything extra on top of that:[/]"
    )
    config.cropper.generate.sheets = Confirm.ask(
        "  Generate contact sheet composites (sheets/ - 2x2 labeled grids merged at full "
        "original resolution, for lower LLM vision-token cost)?",
        default=config.cropper.generate.sheets,
    )

    console.print(
        "\n[bold yellow]📦 Section 2: What to Zip/PDF for Upload[/]\n"
        "[dim]Losslessly re-encoded smaller, never touching panels/ itself (still full quality, "
        "still what video rendering reads). Check only what you actually want built.[/]"
    )
    package = config.cropper.package

    package.panels_zip, package.panels_zip_split = _ask_bundle_checklist(
        "panels_zip [dim](single file on by default - individual panels, a safe, no-downside win for LLM upload)[/]",
        "panels_zip/panels_1.zip", "panels_zip/panels_1.zip, panels_2.zip, ...",
        package.panels_zip, package.panels_zip_split,
    )
    package.panels_pdf, package.panels_pdf_split = _ask_bundle_checklist(
        "panels_pdf [dim](off by default - individual panels, one per page)[/]",
        "panels_pdf/panels_1.pdf", "panels_pdf/panels_1.pdf, panels_2.pdf, ...",
        package.panels_pdf, package.panels_pdf_split,
    )
    package.sheets_zip, package.sheets_zip_split = _ask_bundle_checklist(
        "sheets_zip [dim](off by default - full-resolution contact sheet composites, not "
        "individual panels; builds sheets/ automatically even if Section 1 above is off)[/]",
        "sheets_zip/sheets_1.zip", "sheets_zip/sheets_1.zip, sheets_2.zip, ...",
        package.sheets_zip, package.sheets_zip_split,
    )

    if package.panels_zip_split or package.panels_pdf_split or package.sheets_zip_split:
        max_mb_str = Prompt.ask("[bold cyan]Size cap per part, in MB[/]", default=str(package.max_mb))
        try:
            package.max_mb = float(max_mb_str)
        except ValueError:
            console.print(f"[yellow]Not a number, keeping {package.max_mb:g}MB.[/]")

    config.save()
    console.print(
        f"[bold green]✓ Vision output settings saved:[/] "
        f"sheets {'on' if config.cropper.generate.sheets else 'off'} | "
        f"panels_zip {bundle_state_str(package, package.panels_zip, package.panels_zip_split)} | "
        f"panels_pdf {bundle_state_str(package, package.panels_pdf, package.panels_pdf_split)} | "
        f"sheets_zip {bundle_state_str(package, package.sheets_zip, package.sheets_zip_split)}\n"
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
