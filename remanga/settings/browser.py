"""The complete settings browser - every config field, edited in place.

Built entirely from settings/schema.py, so it covers whatever the models
currently hold rather than whatever somebody remembered to add a screen for.
Adding a config field anywhere under RemangaConfig makes it appear here, with
the right editor and the right bounds, without touching this file. That is
the whole point: the curated screens are better where they exist, and this
guarantees a floor underneath them that cannot rot.

Three levels, because 89 fields in one list is not navigable: pick a section,
pick a field, edit it. Every level shows live values, the same way the
curated menu does, so it reads as a view of the configuration and not just a
way to change it."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.fields import get_field, set_field
from remanga.settings.schema import FieldSpec, fields_by_section
from remanga.tui import Choice, ask_number, ask_text, confirm, is_cancel, select

_SECTION_TITLES = {
    "system": "System (threads, GPU preference, logging)",
    "downloader": "Downloading (retries, pacing, image quality)",
    "cropper": "Cropping (gutters, trimming, dedupe, packaging)",
    "marker": "Panel Marker (server, MAGI, keyboard shortcuts)",
    "reviewer": "Narration Reviewer (server)",
    "writer": "Narration Writer (server)",
    "tts": "Text-to-speech",
    "ocr": "OCR",
    "audio": "Audio (music, levels, pacing)",
    "video": "Video (resolution, framing, encoding)",
}


def _shown(value: object) -> str:
    if isinstance(value, bool):
        return "on" if value else "off"
    if value is None or value == "":
        return "(not set)"
    return str(value)


def _edit_field(config: RemangaConfig, spec: FieldSpec) -> None:
    """One field, with the editor its type asks for."""
    current = get_field(config, spec.dotted)
    note = f"{spec.dotted}   default: {_shown(spec.default)}"
    if spec.bounds_hint:
        note += f"   allowed: {spec.bounds_hint}"

    if spec.kind == "bool":
        picked = confirm(spec.label, default=bool(current))
        if is_cancel(picked):
            return
        value: object = bool(picked)
    elif spec.kind in ("int", "float"):
        # Bounds come from the model's own validators, so the menu cannot
        # offer a number that set_field would then reject.
        raw = ask_number(
            spec.label, default=current,
            minimum=spec.minimum if spec.minimum is not None else -1_000_000,
            maximum=spec.maximum if spec.maximum is not None else 1_000_000,
            integer=spec.kind == "int", note=note,
        )
        if is_cancel(raw):
            return
        value = int(raw) if spec.kind == "int" else float(raw)
    else:
        raw = ask_text(spec.label, default="" if current is None else str(current), note=note)
        if is_cancel(raw):
            return
        value = raw

    try:
        set_field(config, spec.dotted, value)
    except Exception as e:
        # Pydantic validates on assignment, so a value this screen thought was
        # fine can still be refused. Report it and stay put rather than
        # letting a traceback out of a settings menu.
        console.print(f"[bold red]✗ {spec.dotted} rejected that value:[/] {e}")
        return
    console.print(f"[bold green]✓ {spec.dotted}:[/] {_shown(value)}")


def _run_section(config: RemangaConfig, section: str, specs: list[FieldSpec]) -> None:
    while True:
        rows = [
            Choice(
                label=spec.label, hint=_shown(get_field(config, spec.dotted)),
                detail=f"{spec.dotted}" + (f"   ({spec.bounds_hint})" if spec.bounds_hint else ""),
                value=spec.dotted,
            )
            for spec in specs
        ]
        picked = select(
            _SECTION_TITLES.get(section, section), rows,
            note="changes save immediately", back_label="Back",
        )
        if is_cancel(picked):
            return
        _edit_field(config, next(s for s in specs if s.dotted == picked))


def run_all_settings(config: RemangaConfig) -> None:
    """Browse and edit every config field, grouped by section."""
    grouped = fields_by_section(config)
    while True:
        rows = [
            Choice(
                label=_SECTION_TITLES.get(section, section),
                hint=f"{len(specs)} setting{'s' if len(specs) != 1 else ''}",
                value=section,
            )
            for section, specs in grouped.items()
        ]
        picked = select(
            "All settings", rows,
            note="everything config.json holds - the screens above cover the common ones better",
            back_label="Back",
        )
        if is_cancel(picked):
            return
        _run_section(config, picked, grouped[picked])
