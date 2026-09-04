"""Asking for a command's parameters - by looking them up rather than
asking, wherever the answer is already on disk.

Every parameter is prompted from its own Param spec (type, choices,
default, help), so a new command's flags become wizard questions for free.
On top of that, the handful of parameters whose answer is *discoverable*
get a purpose-built prompt instead of a blank text box:

    chapter/chapters - the chapters this project actually has, with status
    keep             - the files this chapter actually has right now
    formats          - the packaging formats, as a checklist
    steps            - the pipeline steps, as an ordered checklist
    engine           - the TTS engines, each described, current pre-picked
    url              - not asked at all once project.json has a source
    engine/voice/bgm - not asked at all: what's configured is stated and
                       used (all three are set once and kept for months)

`keep` and `formats` additionally open pre-checked with whatever this
project chose last time (remembered in project.json - see
settings/project_prefs.py), so answering them once per project is enough.

That last one is the rule the rest follow: if remanga can find the answer,
it shouldn't be a question."""

from __future__ import annotations

from typing import Any, Dict, Optional

from remanga.commands import Command, Param, resolve_wipe_keep
from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.reset import wipeable_entries
from remanga.settings.project_prefs import (
    active_package_formats, remembered_package_formats, remembered_wipe_keep,
)
from remanga.settings.vision import package_choices
from remanga.tui import CANCEL, Choice, ask_text, confirm, is_cancel, multiselect, select
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

    # Pre-checked with this project's remembered keep-list when it has one,
    # so the second chapter's wipe is Enter rather than the same nine
    # decisions again.
    remembered = remembered_wipe_keep(project)
    keep_now = resolve_wipe_keep(None, project)
    source = "kept last time" if remembered is not None else "kept by default"

    # One row per NAME, not per path: wipe keeps by name (see
    # reset.wipe_chapter), and every generated directory for this chapter is
    # literally called "chapter_<n>" - so panels_zip/chapter_1 and
    # audio/chapter_1 are one decision, not two. Showing them as separate
    # rows would imply you could keep one and drop the other.
    grouped: Dict[str, list] = {}
    for entry in entries:
        grouped.setdefault(entry.name, []).append(entry)

    rows = []
    for name, paths in grouped.items():
        kind = "directory" if paths[0].is_dir() else "file"
        where = ", ".join(sorted(p.parent.name for p in paths)) if len(paths) > 1 or paths[0].parent.name != f"chapter_{chapter}" else ""
        hint = kind + (f" · in {where}" if where else "") + (f" · {source}" if name in keep_now else "")
        rows.append(Choice(
            label=name,
            hint=hint,
            detail=" · ".join(display_path(p, wrap=False) for p in paths),
            value=name,
            checked=name in keep_now,
        ))
    picked = multiselect(
        param.label, rows,
        note=(f"checked survives · everything unchecked is deleted from chapter {chapter}"
              " · this choice is remembered for the project"),
    )
    if is_cancel(picked):
        return CANCEL
    return ",".join(picked) if picked else "none"


def _prompt_formats(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
    """Which upload formats to build, as a checklist - the same one the
    settings screen uses, opened on what this project builds right now
    (its remembered choice, else config.json's switches). Whatever comes
    back is remembered by the handler, so the next chapter doesn't ask."""
    active = set(active_package_formats(config, project))
    rows = package_choices(config)
    for row in rows:
        row.checked = row.value in active

    remembered = remembered_package_formats(project)
    origin = ("remembered for this project" if remembered is not None
              else "from config.json's defaults")
    picked = multiselect(
        param.label, rows,
        note=f"{origin} · your choice here is remembered for the next chapter",
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


def _not_asked(current_value, where: str):
    """Builds a prompter for a parameter the wizard deliberately does NOT
    ask about: it states what's configured and returns None, which every
    handler reads as "use the configured value".

    The reference voice, the background music and the TTS engine are all
    chosen once and then used for months. Asking which of them to use before
    every single chapter's run is a screen that answers itself every time -
    so the wizard says what it's about to use and moves on. Changing one is
    either a permanent edit (`where` names the settings screen for it) or an
    explicit CLI flag for a genuine one-off."""

    def prompt(param: Param, project: str, config: RemangaConfig, values: Dict[str, Any]) -> Any:
        configured = current_value(config)
        flag = param.flags[0]
        label = param.prompt or param.name
        console.print(
            f"[dim]{label}: {configured or 'none configured'} "
            f"(change it in {where}, or pass {flag} for a one-off)[/]"
        )
        return None

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


_SPECIAL = {
    "chapter": _prompt_chapter,
    "chapters": _prompt_chapters,
    "keep": _prompt_keep,
    "formats": _prompt_formats,
    "steps": _prompt_steps,
    "url": _prompt_url,
    "engine": _not_asked(lambda c: c.tts.spec.display_name, "Settings → TTS engine"),
    "voice": _not_asked(lambda c: c.tts.spk_audio_prompt, "Settings → Assets"),
    "bgm": _not_asked(lambda c: c.audio.bgm_path if c.audio.bgm_enabled else "", "Settings → Assets"),
}


# --- generic parameters ----------------------------------------------------


def _prompt_choice(param: Param) -> Any:
    """A choice param as a described menu. What each option *means* comes
    from the Param's own choice_help/choice_detail (see commands/spec.py),
    filled in by whichever module owns those choices - so the restart modes
    explain what each keeps, and the narration file modes explain what each
    writes, without this function knowing either of them exists."""
    rows = [
        Choice(label=value, hint=param.choice_help.get(value, ""),
               detail=param.choice_detail.get(value, ""), value=value)
        for value in (param.choices or [])
    ]
    return select(param.label, rows, default=param.default)


def _prompt_free_text(param: Param) -> Any:
    raw = ask_text(
        param.label + ("" if param.required else " (optional)"),
        default="" if param.default is None else str(param.default),
        allow_empty=not param.required,
    )
    return raw or None
