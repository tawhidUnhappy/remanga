"""The shared assets remanga points at - now just the background-music file.

The reference voice WAV and its transcript used to live here too, back when
the TTS engine cloned a narrator from a clip. Kokoro ships fixed voices, so
the narrator is a NAME chosen from a list rather than a file discovered on
disk - see remanga/settings/engine.py's voice picker and
remanga/config/kokoro_voices.py. Nothing about "find me an audio file"
applies to it any more, which is why it is not an AssetSpec.

These used to be described three times over - once in the settings
walkthrough, once in `remanga paths`, and once more in each ensure_valid_*
validator - with three different sets of wording, three different prompts,
and no shared idea of what "configured" meant. Here each one is a single
`AssetSpec` naming the config field it lives in and where its files
normally sit, and every screen (the settings menu, `remanga paths`, and the
validators the audio pipeline calls before it runs) renders and edits that
same list."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import DEFAULT_VOICE, KOKORO_VOICES, VOICE_BY_NAME
from remanga.config.tts import engine_spec, voice_field_for
from remanga.console import console, display_path, escape as _esc
from remanga.settings.fields import get_field, set_field
from remanga.settings.files import (
    AUDIO_EXTENSIONS,
    asset_dir,
    discover_files,
    is_valid_file,
    parent_dir_of,
)
from remanga.tui import Choice, ask_path, confirm, is_cancel, select


@dataclass(frozen=True)
class AssetSpec:
    """One configurable asset.

    dotted        - the config field holding its path (or, for a text asset,
                    the path of the file holding its content). Either a
                    fixed dotted string, or a function of the config for an
                    asset whose home MOVES with another setting. Resolve it
                    with .field(config), never by reading .dotted.
    subdir        - where files of this kind normally live under global/,
                    used to rank discovered candidates.
    enabled_field - optional dotted bool that turns the whole asset off
                    (BGM), so "None" is a real answer rather than an error.
    required_for  - why the pipeline needs it, shown when it's missing."""

    key: str
    # Like `dotted`: a plain string, or a function of the config for a label
    # that has to name what it is currently pointing at. Resolve with
    # .title(config).
    label: str | Callable[[RemangaConfig], str]
    dotted: str | Callable[[RemangaConfig], str]
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


ASSETS: tuple[AssetSpec, ...] = (
    AssetSpec(
        "bgm", "Background music", "audio.bgm_path", subdir="bgm",
        enabled_field="audio.bgm_enabled",
        required_for="the music bed mixed under every recap",
    ),
)

ASSET_BY_KEY = {spec.key: spec for spec in ASSETS}


def asset_relevant(config: RemangaConfig, spec: AssetSpec) -> bool:
    """Whether this asset matters for the *current* engine. Kept as a hook
    (screens call it for every row) even though nothing is engine-specific
    today - the transcript row that used it retired with Audio8 TTS."""
    return True


def asset_status(config: RemangaConfig, spec: AssetSpec) -> tuple[bool, str, str]:
    """(ok, badge, description) for one asset, as every screen shows it."""
    raw = str(get_field(config, spec.field(config)) or "")

    if spec.enabled_field and not get_field(config, spec.enabled_field):
        return True, "off", "disabled"

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


def candidates_for(config: RemangaConfig, spec: AssetSpec) -> list[Path]:
    return discover_files(
        spec.extensions, preferred_subdir=spec.subdir,
        extra_dirs=parent_dir_of(str(get_field(config, spec.field(config)) or "")),
    )


def edit_asset(config: RemangaConfig, spec: AssetSpec) -> None:
    """Interactively changes one asset - a file picked from what's on disk.
    Saves config.json immediately; there is no separate save step anywhere
    in the settings screens."""
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


def ensure_valid_voice(
    config: RemangaConfig, interactive: bool = True, *, engine: str | None = None,
) -> str:
    """The voice the running engine will narrate in, validated.

    Kokoro does not clone, so this validates a NAME against the engine's own
    catalogue rather than checking a file exists. An unknown name is a real
    failure worth stopping for: Kokoro's own loader would try to fetch it
    from the Hub and fail mid-chapter, and `voice_spec` falling back to the
    default would otherwise narrate a whole chapter in a voice nobody asked
    for, silently.

    `engine` names the engine actually synthesizing, when that isn't the one
    config.json selects - `remanga tts --engine X` swaps engines for a
    single run without redefining later ones. Only the voice field is ever
    written back; `tts.engine` is left exactly as it is, so a one-off can't
    quietly become the project's engine by way of a save inside the picker."""
    active_engine = engine or config.tts.engine
    engine_name = engine_spec(active_engine).display_name
    field = voice_field_for(active_engine)
    raw = str(get_field(config, field) or "").strip()

    if raw in VOICE_BY_NAME:
        return raw

    problem = f"{engine_name} has no voice set" if not raw else \
        f"'{_esc(raw)}' is not one of {engine_name}'s voices"

    if not interactive:
        raise ValueError(
            f"{problem}. Set one in config.json under '{field}' (or run `remanga paths`). "
            f"Valid voices: {', '.join(v.name for v in KOKORO_VOICES)}."
        )

    console.print(f"\n[bold]{engine_name} voice setup[/]\n[yellow]{problem}.[/]")
    while True:
        pick_voice(config, engine=active_engine)
        chosen = str(get_field(config, field) or "").strip()
        if chosen in VOICE_BY_NAME:
            return chosen
        console.print("[bold red]A valid voice is required to synthesize narration.[/]")


def voice_choices(current: str) -> list[Choice]:
    """Every Kokoro voice as a menu row, best-graded first (the catalogue is
    already in that order). The grade is shown because the spread is wide -
    Kokoro publishes voices graded from A down to F, and picking blind is
    how a chapter ends up narrated in one of the bad ones."""
    return [
        Choice(
            label=voice.label, hint=voice.name,
            detail=f"grade {voice.grade} · {voice.accent}",
            value=voice.name, badge="current" if voice.name == current else "",
        )
        for voice in KOKORO_VOICES
    ]


def pick_voice(config: RemangaConfig, *, engine: str | None = None) -> None:
    """Interactively chooses the narrator's voice and saves it immediately."""
    field = voice_field_for(engine or config.tts.engine)
    current = str(get_field(config, field) or "")
    picked = select(
        "Narrator voice", voice_choices(current), default=current or DEFAULT_VOICE,
        note="Kokoro's own voices - no reference clip; grades are Kokoro's published ones",
    )
    if is_cancel(picked):
        return
    set_field(config, field, picked)
    voice = VOICE_BY_NAME[picked]
    console.print(f"[bold green]✓ Narrator voice:[/] {voice.label} [dim]({voice.name}, grade {voice.grade})[/]")


def ensure_valid_bgm(config: RemangaConfig, interactive: bool = True) -> str | None:
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
