"""Asking for a command's parameters - by looking them up rather than
asking, wherever the answer is already on disk.

Every parameter is prompted from its own Param spec (type, choices,
default, help), so a new command's flags become wizard questions for free.
On top of that, the handful of parameters whose answer is *discoverable*
get a purpose-built prompt instead of a blank text box:

    chapter/chapters - the chapters this project actually has, with status
    keep             - the files this chapter actually has right now
    steps            - the pipeline steps, as an ordered checklist
    voice/bgm        - the audio files already sitting in global/
    mode             - the restart presets, each with what it keeps
    url              - not asked at all once project.json has a source

That last one is the rule the rest follow: if remanga can find the answer,
it shouldn't be a question."""

from __future__ import annotations

from typing import Any, Dict, Optional

from remanga.commands import Command, DEFAULT_WIPE_KEEP, Param
from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.reset import RESTART_MODE_BY_NAME, wipeable_entries
from remanga.settings import AUDIO_EXTENSIONS, discover_files
from remanga.tui import CANCEL, Choice, ask_path, ask_text, confirm, is_cancel, multiselect, select
from remanga.wizard.chapters import select_chapter, select_chapters


def collect_params(cmd: Command, project: str, config: RemangaConfig) -> Optional[Dict[str, Any]]:
    """Every parameter this command needs, in order. Returns None if the
    user backed out of any of them - backing out of a question means "don't
    run this command", not "run it with a blank answer"."""
    values: Dict[str, Any] = {}
    for param in cmd.params:
        if param.name == "project":
            values["project"] = project
            continue
        answer = prompt_param(param, project=project, config=config, values=values)
        if is_cancel(answer):
            return None
        values[param.name] = answer
    return values


def prompt_param(param: Param, *, project: str, config: RemangaConfig,
                 values: Dict[str, Any]) -> Any:
    special = _SPECIAL.get(param.name)
    if special is not None:
        return special(param, project, config, values)
    if param.type == "bool":
        return confirm(param.label, default=bool(param.default))
    if param.type == "choice":
        return _prompt_choice(param)
    return _prompt_free_text(param)


# --- discoverable parameters ----------------------------------------------


def _prompt_chapter(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    return select_chapter(project, title=param.label)


def _prompt_chapters(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    picked = select_chapters(project, title=param.label)
    if is_cancel(picked):
        return CANCEL
    # An empty selection means "every chapter" for the optional --chapters
    # flags, which is exactly what None means to their handlers. The one
    # required chapters param (wipe-chapters) can't take that answer, so it
    # asks again rather than silently wiping everything.
    if not picked:
        if param.required:
            console.print("[yellow]Select at least one chapter.[/]")
            return _prompt_chapters(param, project, config, values)
        return None
    return ",".join(picked)


def _prompt_keep(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    """The wipe keep-list, as a checklist of what this chapter actually has
    right now - so nobody has to remember whether it's "panels" or
    "panels/", or which generated directories exist for this chapter at
    all. Checked = survives; everything unchecked is what gets deleted."""
    chapter = values.get("chapter")
    if chapter is None:
        return _prompt_free_text(param)

    entries = wipeable_entries(project, chapter)
    if not entries:
        console.print(f"[dim]Nothing exists yet for chapter {chapter} - nothing to wipe.[/]")
        return "none"

    rows = [
        Choice(
            label=entry.name,
            hint=("directory" if entry.is_dir() else "file") + (
                " · kept by default" if entry.name in DEFAULT_WIPE_KEEP else ""),
            detail=display_path(entry, wrap=False),
            value=entry.name,
            checked=entry.name in DEFAULT_WIPE_KEEP,
        )
        for entry in entries
    ]
    picked = multiselect(
        param.label, rows,
        note=f"checked survives · everything unchecked is deleted from chapter {chapter}",
    )
    if is_cancel(picked):
        return CANCEL
    return ",".join(picked) if picked else "none"


def _prompt_steps(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    """The pipeline steps for a one-off run, pre-checked with this project's
    saved pipeline and ordered by how they're checked. Confirming it
    unchanged returns None, which means "use the saved pipeline.json" -
    the same thing leaving --steps off does."""
    from remanga.pipeline import STEP_REGISTRY, load_pipeline

    saved = load_pipeline(project)
    rows = [
        Choice(label=step.name, hint=step.description, value=step.name, checked=step.name in saved)
        for step in STEP_REGISTRY
    ]
    rows.sort(key=lambda row: saved.index(row.value) if row.value in saved else len(saved))

    picked = multiselect(
        param.label, rows, ordered=True, allow_empty=False,
        note=f"this project's pipeline: {', '.join(saved)}",
    )
    if is_cancel(picked):
        return CANCEL
    return None if picked == saved else ",".join(picked)


def _prompt_audio_override(subdir: str, current_value: str):
    """Builds a prompter for an optional 'use this audio file instead of the
    configured one, just this once' parameter (tts --voice, mix --bgm)."""

    def prompt(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
        configured = current_value(config)
        picked = ask_path(
            param.label, current="", candidates=discover_files(AUDIO_EXTENSIONS, preferred_subdir=subdir),
            note=f"leave as-is to use the configured file: {configured or '(none)'}",
            allow_none=True, none_label="Use the configured file",
        )
        return picked

    return prompt


def _prompt_url(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    """The manga source. Asked only when the project doesn't have one saved -
    the downloader falls back to project.json's manga_url/manga_id whenever
    this is None, so re-typing the same URL for every chapter of the same
    manga was pure ceremony."""
    from remanga.paths import load_project_metadata

    meta = load_project_metadata(project)
    saved = meta.get("manga_url") or meta.get("manga_id")
    if saved:
        title = meta.get("manga_title")
        console.print(f"[dim]Manga source: {title + ' — ' if title else ''}{saved}[/]")
        return None
    return ask_text(param.label, note="a MangaDex URL, a UUID, or just the title to search for") or None


def _prompt_mode(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    """A restart preset, each row saying what survives it - the difference
    between the four modes IS what they keep, which a bare list of names
    can't convey."""
    rows = []
    for name in param.choices or []:
        mode = RESTART_MODE_BY_NAME.get(name)
        rows.append(Choice(
            label=mode.label if mode else name,
            hint=mode.summary if mode else "",
            detail=f"keeps: {mode.keeps}" if mode else "",
            value=name,
        ))
    return select(param.label, rows, default=param.default)


_SPECIAL = {
    "chapter": _prompt_chapter,
    "chapters": _prompt_chapters,
    "keep": _prompt_keep,
    "steps": _prompt_steps,
    "url": _prompt_url,
    "mode": _prompt_mode,
    "voice": _prompt_audio_override("voice", lambda c: c.tts.spk_audio_prompt),
    "bgm": _prompt_audio_override("bgm", lambda c: c.audio.bgm_path if c.audio.bgm_enabled else ""),
}


# --- generic parameters ----------------------------------------------------


def _prompt_choice(param: Param) -> Any:
    rows = [Choice(label=value, value=value) for value in (param.choices or [])]
    return select(param.label, rows, default=param.default)


def _prompt_free_text(param: Param) -> Any:
    raw = ask_text(
        param.label + ("" if param.required else " (optional)"),
        default="" if param.default is None else str(param.default),
        allow_empty=not param.required,
    )
    return raw or None
