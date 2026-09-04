"""The shared assets remanga points at: the reference voice WAV, the
background-music file, and the TTS reference transcript.

All three used to be described three times over - once in the settings
walkthrough, once in `remanga paths`, and once more in each ensure_valid_*
validator - with three different sets of wording, three different prompts,
and no shared idea of what "configured" meant. Here each one is a single
`AssetSpec` naming the config field it lives in and where its files
normally sit, and every screen (the settings menu, `remanga paths`, and the
validators the audio pipeline calls before it runs) renders and edits that
same list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from remanga.config import RemangaConfig
from remanga.console import console, display_path, escape as _esc
from remanga.settings.fields import get_field, set_field
from remanga.settings.files import (
    AUDIO_EXTENSIONS, discover_files, is_valid_file, parent_dir_of, read_reference_text,
    write_reference_text,
)
from remanga.tui import Choice, ask_path, ask_text, confirm, is_cancel, select


@dataclass(frozen=True)
class AssetSpec:
    """One configurable asset.

    dotted        - the config field holding its path (or, for a text asset,
                    the path of the file holding its content).
    kind          - "file" (pick an existing file) or "text" (edit the
                    contents of a small text file in place).
    subdir        - where files of this kind normally live under global/,
                    used to rank discovered candidates.
    enabled_field - optional dotted bool that turns the whole asset off
                    (BGM), so "None" is a real answer rather than an error.
    required_for  - why the pipeline needs it, shown when it's missing."""

    key: str
    label: str
    dotted: str
    kind: str = "file"
    subdir: str = ""
    extensions: Sequence[str] = AUDIO_EXTENSIONS
    enabled_field: str = ""
    required_for: str = ""
    used_when: str = ""


ASSETS: Tuple[AssetSpec, ...] = (
    AssetSpec(
        "voice", "Reference voice WAV", "tts.spk_audio_prompt", subdir="voice",
        required_for="zero-shot speaker cloning - a clean 3-10 second clip of a steady voice",
    ),
    AssetSpec(
        "bgm", "Background music", "audio.bgm_path", subdir="bgm",
        enabled_field="audio.bgm_enabled",
        required_for="the music bed mixed under every recap",
    ),
    AssetSpec(
        "transcript", "TTS reference transcript", "tts.audio8.reference_text_path", kind="text",
        required_for="what the reference clip says, word for word - cloning quality depends on it",
        used_when="engine needs a transcript",
    ),
)

ASSET_BY_KEY = {spec.key: spec for spec in ASSETS}


def asset_relevant(config: RemangaConfig, spec: AssetSpec) -> bool:
    """Whether this asset matters for the *current* engine. The transcript
    is meaningless under an engine that clones from audio alone, so it's
    shown greyed out with the reason rather than silently listed as
    something to configure."""
    if spec.key == "transcript":
        return config.tts.spec.needs_reference_text
    return True


def asset_status(config: RemangaConfig, spec: AssetSpec) -> Tuple[bool, str, str]:
    """(ok, badge, description) for one asset, as every screen shows it."""
    raw = str(get_field(config, spec.dotted) or "")

    if spec.enabled_field and not get_field(config, spec.enabled_field):
        return True, "off", "disabled"

    if spec.kind == "text":
        text = read_reference_text(raw)
        if not text:
            return False, "empty", f"{raw or '(not set)'} - no text yet"
        preview = text if len(text) <= 60 else text[:57] + "..."
        return True, "set", f"{preview}  ({len(text)} chars)"

    valid = is_valid_file(raw)
    if valid:
        return True, "ok", display_path(valid, wrap=False)
    return False, "missing", raw or "(not set)"


def asset_choice(config: RemangaConfig, spec: AssetSpec) -> Choice:
    ok, badge, description = asset_status(config, spec)
    relevant = asset_relevant(config, spec)
    return Choice(
        label=spec.label,
        hint=description,
        badge=badge if relevant else "unused",
        detail=spec.required_for if not ok else "",
        value=spec.key,
    )


def candidates_for(config: RemangaConfig, spec: AssetSpec) -> List[Path]:
    return discover_files(
        spec.extensions, preferred_subdir=spec.subdir,
        extra_dirs=parent_dir_of(str(get_field(config, spec.dotted) or "")),
    )


def edit_asset(config: RemangaConfig, spec: AssetSpec) -> None:
    """Interactively changes one asset - a file picked from what's on disk,
    or the transcript's text typed in place. Saves config.json/the
    transcript file immediately; there is no separate save step anywhere in
    the settings screens."""
    if spec.kind == "text":
        _edit_text_asset(config, spec)
        return

    current = str(get_field(config, spec.dotted) or "")
    picked = ask_path(
        f"{spec.label}", current=current, candidates=candidates_for(config, spec),
        note=spec.required_for, allow_none=bool(spec.enabled_field),
        none_label="None (turn this off)",
    )
    if is_cancel(picked):
        return

    if picked is None:
        set_field(config, spec.enabled_field, False)
        console.print(f"[yellow]{spec.label} disabled.[/]")
        return

    valid = is_valid_file(picked, min_size=1)
    if not valid:
        console.print(f"[bold red]✗ File not found or empty:[/] {_esc(str(picked))}")
        return

    set_field(config, spec.dotted, str(valid), save=False)
    if spec.enabled_field:
        set_field(config, spec.enabled_field, True, save=False)
    config.save()
    console.print(f"[bold green]✓ {spec.label} saved:[/] {display_path(valid)}")


def _edit_text_asset(config: RemangaConfig, spec: AssetSpec) -> None:
    path_str = str(get_field(config, spec.dotted) or "")
    current = read_reference_text(path_str)
    new_text = ask_text(
        spec.label, default=current,
        note=f"{spec.required_for}\nSaved to: {display_path(Path(path_str), wrap=False)}",
    )
    saved = write_reference_text(path_str, new_text)
    console.print(f"[bold green]✓ Saved:[/] {display_path(saved)}")


def run_asset_menu(config: RemangaConfig, *, title: str = "Assets") -> None:
    """The shared asset screen: every asset with its live status, pick one to
    change it, repeat until Back. This is both `remanga paths` and the
    settings menu's Assets section - one implementation, so the two can't
    drift."""
    while True:
        rows = [asset_choice(config, spec) for spec in ASSETS]
        picked = select(title, rows, note="changes save immediately", back_label="Back")
        if is_cancel(picked):
            return
        edit_asset(config, ASSET_BY_KEY[picked])


# ---------------------------------------------------------------------------
# Validators the pipeline calls before it runs. Same behavior as before:
# interactive=False never prompts, so a non-interactive `full-recap` or
# `remix` run fails (voice) or degrades (BGM) instead of blocking on input.
# ---------------------------------------------------------------------------


def ensure_valid_voice_prompt(config: RemangaConfig, interactive: bool = True) -> str:
    spec = ASSET_BY_KEY["voice"]
    raw_path = str(config.tts.spk_audio_prompt or "").strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

    if not interactive:
        raise FileNotFoundError(
            f"Invalid or missing reference voice file: '{raw_path}'. "
            f"Set a valid WAV file in config.json under 'tts.spk_audio_prompt' "
            f"(or run `remanga paths`)."
        )

    console.print(
        f"\n[bold]{config.tts.spec.display_name} speaker voice setup[/]\n"
        f"[dim]{spec.required_for}[/]"
    )
    while True:
        edit_asset(config, spec)
        valid = is_valid_file(config.tts.spk_audio_prompt)
        if valid:
            return str(valid.resolve())
        console.print("[bold red]A valid reference voice file is required to synthesize narration.[/]")


def ensure_valid_bgm(config: RemangaConfig, interactive: bool = True) -> Optional[str]:
    if not config.audio.bgm_enabled:
        return None

    raw_path = str(config.audio.bgm_path or "").strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

    if not interactive:
        console.print(
            f"[yellow]BGM is enabled but '{_esc(raw_path)}' was not found. Proceeding without BGM.[/]"
        )
        return None

    console.print(
        "\n[bold]Background music setup[/]\n"
        f"[dim]BGM is enabled in config.json, but '{_esc(raw_path or '(not set)')}' isn't a usable file.[/]"
    )
    if not confirm("Configure a background music file now?", default=True):
        set_field(config, "audio.bgm_enabled", False)
        console.print("[yellow]BGM disabled in config.json.[/]\n")
        return None

    edit_asset(config, ASSET_BY_KEY["bgm"])
    valid = is_valid_file(config.audio.bgm_path)
    if valid and config.audio.bgm_enabled:
        return str(valid.resolve())
    return None
