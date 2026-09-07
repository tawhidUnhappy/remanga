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

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple, Union

from remanga.config import RemangaConfig
from remanga.config.tts import engine_spec, voice_field_for
from remanga.console import console, display_path, escape as _esc
from remanga.settings.fields import get_field, set_field
from remanga.settings.files import (
    AUDIO_EXTENSIONS, asset_dir, discover_files, is_valid_file, parent_dir_of, read_reference_text,
    write_reference_text,
)
from remanga.tui import Choice, ask_path, ask_text, confirm, is_cancel, select


@dataclass(frozen=True)
class AssetSpec:
    """One configurable asset.

    dotted        - the config field holding its path (or, for a text asset,
                    the path of the file holding its content). Either a
                    fixed dotted string, or a function of the config for an
                    asset whose home MOVES with another setting - the
                    reference voice lives in whichever engine block is
                    active now (tts.indextts.spk_audio_prompt or
                    tts.audio8.spk_audio_prompt), so this row edits the
                    voice of the engine you are about to run. Resolve it
                    with .field(config), never by reading .dotted.
    kind          - "file" (pick an existing file) or "text" (edit the
                    contents of a small text file in place).
    subdir        - where files of this kind normally live under global/,
                    used to rank discovered candidates.
    enabled_field - optional dotted bool that turns the whole asset off
                    (BGM), so "None" is a real answer rather than an error.
    required_for  - why the pipeline needs it, shown when it's missing."""

    key: str
    # Like `dotted`: a plain string, or a function of the config for a label
    # that has to name what it is currently pointing at. Resolve with
    # .title(config).
    label: Union[str, Callable[[RemangaConfig], str]]
    dotted: Union[str, Callable[[RemangaConfig], str]]
    kind: str = "file"
    subdir: str = ""
    extensions: Sequence[str] = AUDIO_EXTENSIONS
    enabled_field: str = ""
    required_for: str = ""
    used_when: str = ""

    def field(self, config: RemangaConfig) -> str:
        """The dotted config path this asset lives at right now."""
        return self.dotted(config) if callable(self.dotted) else self.dotted

    def title(self, config: RemangaConfig) -> str:
        """This asset's label as it should read right now."""
        return self.label(config) if callable(self.label) else self.label


ASSETS: Tuple[AssetSpec, ...] = (
    # Per ENGINE, not per install: each TTS engine clones from its own
    # reference clip (see config/tts.py), so this row follows tts.engine and
    # names the engine it is editing. Changing engines changes which file
    # this row shows and sets - which is the point, since the clip that
    # sounds best under one model routinely isn't the one that sounds best
    # under the other.
    AssetSpec(
        "voice",
        lambda config: f"Reference voice WAV ({config.tts.spec.display_name})",
        lambda config: config.tts.active_voice_field, subdir="voice",
        required_for="zero-shot speaker cloning - a clean 3-10 second clip of a steady voice",
    ),
    AssetSpec(
        "bgm", "Background music", "audio.bgm_path", subdir="bgm",
        enabled_field="audio.bgm_enabled",
        required_for="the music bed mixed under every recap",
    ),
    AssetSpec(
        "transcript", "TTS reference transcript", "tts.audio8.reference_text_path", kind="text",
        required_for="what Audio8 TTS's own reference clip says, word for word - cloning "
                     "quality depends on it",
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
    raw = str(get_field(config, spec.field(config)) or "")

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
        label=spec.title(config),
        hint=description,
        badge=badge if relevant else "unused",
        detail=spec.required_for if not ok else "",
        value=spec.key,
    )


def candidates_for(config: RemangaConfig, spec: AssetSpec) -> List[Path]:
    return discover_files(
        spec.extensions, preferred_subdir=spec.subdir,
        extra_dirs=parent_dir_of(str(get_field(config, spec.field(config)) or "")),
    )


def edit_asset(config: RemangaConfig, spec: AssetSpec) -> None:
    """Interactively changes one asset - a file picked from what's on disk,
    or the transcript's text typed in place. Saves config.json/the
    transcript file immediately; there is no separate save step anywhere in
    the settings screens."""
    if spec.kind == "text":
        _edit_text_asset(config, spec)
        return

    current = str(get_field(config, spec.field(config)) or "")
    # Created, not just named: "drop your files in global/voice/" is only
    # useful advice if that folder is actually there to drop them into.
    folder = asset_dir(spec.subdir, create=True) if spec.subdir else None
    note = spec.required_for
    if folder is not None:
        note += f"\nlisting {display_path(folder, wrap=False)}/ - put files there to see them here"

    picked = ask_path(
        spec.title(config), current=current, candidates=candidates_for(config, spec),
        note=note, allow_none=bool(spec.enabled_field),
        none_label="None (turn this off)",
    )
    if is_cancel(picked):
        return

    if picked is None:
        set_field(config, spec.enabled_field, False)
        console.print(f"[yellow]{spec.title(config)} disabled.[/]")
        return

    valid = is_valid_file(picked, min_size=1)
    if not valid:
        console.print(f"[bold red]✗ File not found or empty:[/] {_esc(str(picked))}")
        return

    set_field(config, spec.field(config), str(valid), save=False)
    if spec.enabled_field:
        set_field(config, spec.enabled_field, True, save=False)
    config.save()
    console.print(f"[bold green]✓ {spec.title(config)} saved:[/] {display_path(valid)}")


def _edit_text_asset(config: RemangaConfig, spec: AssetSpec) -> None:
    path_str = str(get_field(config, spec.field(config)) or "")
    current = read_reference_text(path_str)
    new_text = ask_text(
        spec.title(config), default=current,
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


def ensure_valid_voice_prompt(
    config: RemangaConfig, interactive: bool = True, *, engine: Optional[str] = None,
) -> str:
    """The reference clip the running engine will clone from, validated.

    `engine` names the engine actually synthesizing, when that isn't the one
    config.json selects - `remanga tts --engine X` swaps engines for a single
    run without redefining later ones, and each engine has its own voice, so
    validating (and, interactively, asking for) the CONFIGURED engine's clip
    there would check one file and hand the worker another. Only the voice
    field is ever written back; `tts.engine` is left exactly as it is, so a
    one-off can't quietly become the project's engine by way of a save
    inside the picker.

    Every message names the engine and its own config field: with a voice
    per engine, "the reference voice is missing" is not actionable on its
    own - the file the other engine uses may well be sitting there perfectly
    valid, and the one being asked for is the one that isn't."""
    active_engine = engine or config.tts.engine
    engine_name = engine_spec(active_engine).display_name
    field = voice_field_for(active_engine)
    # A one-off copy of the voice spec pinned to THIS engine's field and
    # label, so the picker edits and reports the right engine even when the
    # config object it was handed names a different one.
    spec = replace(
        ASSET_BY_KEY["voice"], dotted=field, label=f"Reference voice WAV ({engine_name})",
    )
    raw_path = str(get_field(config, field) or "").strip()
    valid = is_valid_file(raw_path)
    if valid:
        return str(valid.resolve())

    if not interactive:
        raise FileNotFoundError(
            f"Invalid or missing reference voice file for {engine_name}: '{raw_path}'. "
            f"Set a valid WAV file in config.json under '{field}' "
            f"(or run `remanga paths`). Each engine has its own reference voice - "
            f"setting the other engine's does not cover this one."
        )

    console.print(
        f"\n[bold]{engine_name} speaker voice setup[/]\n"
        f"[dim]{spec.required_for}[/]\n"
        f"[dim]This is {engine_name}'s own reference clip "
        f"({field}) - the other engine keeps its own.[/]"
    )
    while True:
        edit_asset(config, spec)
        valid = is_valid_file(get_field(config, field))
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
