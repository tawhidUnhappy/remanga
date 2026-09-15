"""The narrator's voice, which - unlike background music (assets.py) - is a
different kind of thing per engine. Kokoro's is a NAME chosen from its own
catalogue (config/kokoro_voices.py); Chatterbox's is a recording it clones,
picked from the files in global/voice/. `ensure_valid_voice` and `pick_voice`
below ask the engine's spec which of the two it takes
(`TTSEngineSpec.clones_voice`) rather than branching on its name.

ensure_valid_voice is what the pipeline calls before synthesis:
interactive=False never prompts, so a non-interactive `full-recap` or `remix`
run fails instead of blocking on input."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import DEFAULT_VOICE, KOKORO_VOICES, VOICE_BY_NAME
from remanga.config.tts import TTSEngineSpec, engine_spec, voice_field_for
from remanga.console import console, display_path, escape as _esc
from remanga.settings.fields import get_field, set_field
from remanga.settings.files import asset_dir, discover_files, is_valid_file, parent_dir_of
from remanga.tui import Choice, ask_path, is_cancel, select

# What a recording to clone may be. Narrower than AUDIO_EXTENSIONS on purpose:
# the Chatterbox worker decodes the clip with librosa rather than ffmpeg, and
# these are the formats its soundfile backend reads natively.
CLONE_EXTENSIONS = (".wav", ".flac", ".mp3", ".ogg")
# Chatterbox Turbo asserts on a reference clip of this length or less.
MIN_CLONE_SECONDS = 5.0


def clip_problem(raw: str) -> str | None:
    """Why the file at `raw` can't be cloned from, or None when it can.

    Checked here, before a run, rather than left to the worker: Turbo
    asserts on a clip that is too short, and that would only surface at the
    first panel, after the model had been loaded."""
    # Imported here: remanga.verify pulls in far more than this check needs.
    from remanga.verify.probe import probe_media

    clip = is_valid_file(raw, min_size=1)
    if clip is None:
        return f"the recording '{_esc(raw)}' was not found"
    if clip.suffix.lower() not in CLONE_EXTENSIONS:
        return f"'{_esc(clip.name)}' is not one of {', '.join(CLONE_EXTENSIONS)}"
    probe = probe_media(clip)
    if not probe.decodable or not probe.has_audio:
        return f"'{_esc(clip.name)}' could not be read as audio ({_esc(probe.error or 'no audio stream')})"
    if probe.duration_sec <= MIN_CLONE_SECONDS:
        return (f"'{_esc(clip.name)}' is {probe.duration_sec:.1f}s long - "
                f"a recording to clone has to be longer than {MIN_CLONE_SECONDS:g} seconds")
    return None


def _voice_problem(spec: TTSEngineSpec, raw: str) -> str | None:
    """Why `raw` can't be this engine's voice, or None when it can - a name
    checked against Kokoro's catalogue, or a recording checked on disk."""
    if not raw:
        return f"{spec.display_name} has no voice set"
    if spec.clones_voice:
        return clip_problem(raw)
    if raw not in VOICE_BY_NAME:
        return f"'{_esc(raw)}' is not one of {spec.display_name}'s voices"
    return None


def ensure_valid_voice(
    config: RemangaConfig, interactive: bool = True, *, engine: str | None = None,
) -> str:
    """The voice the running engine will narrate in, validated.

    For Kokoro that means a NAME in its catalogue. An unknown name is a real
    failure worth stopping for: Kokoro's own loader would try to fetch it
    from the Hub and fail mid-chapter, and `voice_spec` falling back to the
    default would otherwise narrate a whole chapter in a voice nobody asked
    for, silently. For Chatterbox it means a recording that exists, decodes,
    and is long enough to clone from (see clip_problem).

    `engine` names the engine actually synthesizing, when that isn't the one
    config.json selects - `remanga tts --engine X` swaps engines for a
    single run without redefining later ones. Only the voice field is ever
    written back; `tts.engine` is left exactly as it is, so a one-off can't
    quietly become the project's engine by way of a save inside the picker."""
    active_engine = engine or config.tts.engine
    spec = engine_spec(active_engine)
    field = voice_field_for(active_engine)
    raw = str(get_field(config, field) or "").strip()

    problem = _voice_problem(spec, raw)
    if problem is None:
        return raw

    if not interactive:
        if spec.clones_voice:
            fix = (f"Set '{field}' in config.json to a recording of the voice to clone "
                   f"({', '.join(CLONE_EXTENSIONS)}, over {MIN_CLONE_SECONDS:g} seconds), "
                   f"or pick one with `remanga setup-config`.")
        else:
            fix = (f"Set one in config.json under '{field}' (or pick one with `remanga setup-config`). "
                   f"Valid voices: {', '.join(v.name for v in KOKORO_VOICES)}.")
        raise ValueError(f"{problem}. {fix}")

    console.print(f"\n[bold]{spec.display_name} voice setup[/]\n[yellow]{problem}.[/]")
    while True:
        pick_voice(config, engine=active_engine)
        chosen = str(get_field(config, field) or "").strip()
        if _voice_problem(spec, chosen) is None:
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


def _pick_recording(config: RemangaConfig, engine: str) -> None:
    """Chooses the recording a cloning engine narrates in, from the files
    already in global/voice/ (and beside the current one). Validated before
    it is saved, so a clip too short or unreadable to clone from is refused
    here rather than at the first panel of a run."""
    spec = engine_spec(engine)
    field = voice_field_for(engine)
    current = str(get_field(config, field) or "")
    folder = asset_dir("voice", create=True)

    picked = ask_path(
        "Recording to clone", current=current,
        candidates=discover_files(CLONE_EXTENSIONS, preferred_subdir="voice",
                                  extra_dirs=parent_dir_of(current)),
        note=(f"{spec.display_name} clones whoever is speaking: one voice, no music, longer than "
              f"{MIN_CLONE_SECONDS:g} seconds - the first 10-15 seconds matter most\n"
              f"listing {display_path(folder, wrap=False)}/ - put recordings there to see them here"),
    )
    if is_cancel(picked) or picked is None:
        return

    problem = clip_problem(str(picked))
    if problem:
        console.print(f"[bold red]✗ {problem}[/]")
        return
    set_field(config, field, str(picked))
    console.print(f"[bold green]✓ Narrator voice:[/] clone of {display_path(Path(str(picked)))}")


def pick_voice(config: RemangaConfig, *, engine: str | None = None) -> None:
    """Interactively chooses the narrator's voice and saves it immediately -
    a name from Kokoro's catalogue, or a recording for Chatterbox to clone."""
    active_engine = engine or config.tts.engine
    if engine_spec(active_engine).clones_voice:
        _pick_recording(config, active_engine)
        return

    field = voice_field_for(active_engine)
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
