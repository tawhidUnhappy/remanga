"""Reusable validators that ensure a RemangaConfig has valid voice/BGM settings (prompting
interactively to fix them when they're missing) and the vision-output "what to generate,
what to zip" checklist (configure_vision_outputs). Used both by the CLI/wizard and by the
audio pipeline stages that depend on these settings being valid before they run."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from rich.prompt import Confirm, Prompt

from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc


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


def _ask_yes_no(label: str, hint: str, current: bool) -> bool:
    console.print(f"\n[bold]{label}[/]")
    return Confirm.ask(f"  Generate this ({hint})?", default=current)


def configure_vision_outputs(config: RemangaConfig) -> None:
    """The 'what to generate, what to zip' menu: one flat checklist - see
    PackageConfig's docstring - of every independent yes/no switch a
    chapter's vision output can have. Nothing here is a mode to pick: e.g.
    "only the PDF, not the zip" is just answering yes to one question and no
    to the rest, not a hidden config.json edit.

    Shared by `remanga setup-config` (step 2/3, part of the full settings
    walkthrough) and the main interactive wizard's own "adjust what gets
    generated/zipped" prompt, so there's one place a user can reach this
    without needing to know setup-config exists separately. Saves
    config.json itself, like every other ensure_valid_*/configure_* helper
    in this module."""
    console.print(
        "\n[bold]What to Generate / Zip for Upload[/]\n"
        "[dim]Individual panel crops (panels/) are always produced - that's what cropping a "
        "chapter means. Everything below is optional, losslessly re-encoded smaller, and never "
        "touches panels/ itself (still full quality, still what video rendering reads). Check "
        "only what you actually want built:[/]"
    )
    package = config.cropper.package

    package.sheets = _ask_yes_no(
        "sheets [dim](on by default - 2x2 labeled grid composites merged at full original "
        "resolution, for lower LLM vision-token cost)[/]",
        "sheets/sheet_1.___, sheet_2.___, ...", package.sheets,
    )
    package.sheets_zip = _ask_yes_no(
        "sheets_zip [dim](off by default - zips those contact sheets; builds sheets/ "
        "automatically even if `sheets` above is off)[/]",
        "sheets_zip/sheets_1.zip", package.sheets_zip,
    )
    package.sheets_folders = _ask_yes_no(
        "sheets_folders [dim](off by default - no compositing at all, just each panel crop "
        "copied as-is into small numbered subfolders)[/]",
        f"sheets_folders/folder_1/ .. folder_N/ ({config.cropper.panels_per_folder} panels each)",
        package.sheets_folders,
    )
    package.pdf = _ask_yes_no(
        "pdf [dim](off by default - individual panels, one per PDF page, single file)[/]",
        "panels_pdf/panels_1.pdf", package.pdf,
    )
    package.pdf_splite = _ask_yes_no(
        "pdf_splite [dim](off by default - that same PDF content split into size-capped raw "
        ".pdf files, not zipped)[/]",
        "panels_pdf/panels_1.pdf, panels_2.pdf, ...", package.pdf_splite,
    )
    package.pdf_zip = _ask_yes_no(
        "pdf_zip [dim](off by default - that same single PDF, wrapped in a zip)[/]",
        "panels_pdf/panels_1.zip", package.pdf_zip,
    )
    package.pdf_zip_splite = _ask_yes_no(
        "pdf_zip_splite [dim](off by default - the PDF split into size-capped parts, each "
        "zipped separately)[/]",
        "panels_pdf/panels_1.zip, panels_2.zip, ...", package.pdf_zip_splite,
    )
    package.panels_zip = _ask_yes_no(
        "panels_zip [dim](off by default - individual panel crops, single file)[/]",
        "panels_zip/panels_1.zip", package.panels_zip,
    )
    package.panels_zip_splites = _ask_yes_no(
        "panels_zip_splites [dim](off by default - that same panels zip, split into "
        "size-capped parts)[/]",
        "panels_zip/panels_1.zip, panels_2.zip, ...", package.panels_zip_splites,
    )

    if package.pdf_splite or package.pdf_zip_splite or package.panels_zip_splites:
        max_mb_str = Prompt.ask("[bold]Size cap per part, in MB[/]", default=str(package.max_mb))
        try:
            package.max_mb = float(max_mb_str)
        except ValueError:
            console.print(f"[yellow]Not a number, keeping {package.max_mb:g}MB.[/]")

    config.save()
    console.print(
        f"[bold green]✓ Vision output settings saved:[/] "
        f"sheets {'on' if package.sheets else 'off'} | "
        f"sheets_zip {'on' if package.sheets_zip else 'off'} | "
        f"sheets_folders {'on' if package.sheets_folders else 'off'} | "
        f"pdf {'on' if package.pdf else 'off'} | "
        f"pdf_splite {'on' if package.pdf_splite else 'off'} | "
        f"pdf_zip {'on' if package.pdf_zip else 'off'} | "
        f"pdf_zip_splite {'on' if package.pdf_zip_splite else 'off'} | "
        f"panels_zip {'on' if package.panels_zip else 'off'} | "
        f"panels_zip_splites {'on' if package.panels_zip_splites else 'off'}\n"
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
        "\n[bold]IndexTTS-2.5 Speaker Voice Setup[/]\n"
        "A clean 3-10 second reference WAV audio file is required for zero-shot speaker cloning.\n"
        f"[dim]Current setting: '{raw_path or 'Not configured'}'[/]"
    )

    while True:
        user_input = Prompt.ask("[bold]Enter absolute or relative path to your reference voice WAV file[/]").strip().strip("'\"")
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


def read_reference_text(path: str) -> str:
    """Reads the audio8-tts-0.1b reference transcript from its own text file
    (tts.audio8.reference_text_path) rather than inline config.json - see
    that field's docstring. Missing/empty file reads as "", same as the old
    inline-string field's own empty default; audio8_worker.py already
    tolerates an empty transcript (degraded cloning quality, not an error),
    so this stays a soft fallback rather than raising."""
    p = Path((path or "").strip()).expanduser()
    if not p.exists() or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


def write_reference_text(path: str, text: str) -> Path:
    """Writes `text` to the audio8 reference-transcript file, creating its
    parent directory (typically global/) if needed. Returns the resolved path."""
    p = Path((path or "").strip()).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((text or "").strip(), encoding="utf-8")
    return p.resolve()


def ensure_valid_bgm(config: RemangaConfig, interactive: bool = True) -> Optional[str]:
    if not config.audio.bgm_enabled:
        return None

    raw_path = config.audio.bgm_path.strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

    if not interactive:
        console.print(f"[yellow]BGM is enabled but file '{_esc(str(raw_path))}' was not found. Proceeding without BGM.[/]")
        return None

    console.print(
        "\n[bold]Background Music (BGM) Setup[/]\n"
        "BGM is enabled in your configuration, but the audio file path is missing or invalid.\n"
    )

    wants_bgm = Confirm.ask("Would you like to configure a background music file now?", default=True)
    if not wants_bgm:
        config.audio.bgm_enabled = False
        config.save()
        console.print("[yellow]BGM disabled for this chapter.[/]\n")
        return None

    while True:
        user_input = Prompt.ask("[bold]Enter path to your BGM audio file (or press Enter to skip)[/]").strip().strip("'\"")
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
