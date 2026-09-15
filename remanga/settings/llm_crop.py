"""The LLM crop settings screen: which grid uploads `crop-grid` builds, how
readily Gemini groups panels, and how its crops are cut.

The format checklist is generated from LLMCropConfig's Field metadata, the
way the packaging checklist is generated from PackageConfig's
(settings/vision.py) - a new grid format is one field, not a field plus a
menu row."""

from __future__ import annotations

from remanga.config import LLMCropConfig, RemangaConfig
from remanga.console import console
from remanga.settings.fields import set_field
from remanga.tui import Choice, ask_number, confirm, is_cancel, multiselect, select

_FORMAT_GROUPS = ("pages", "zip", "pdf")

GROUPING_CHOICES: tuple[tuple[str, str], ...] = (
    ("balanced", "groups only frames too slight to narrate alone - silent inserts, small reaction shots"),
    ("none", "every frame is its own crop"),
    ("generous", "also groups a tier or a column that shows the same scene"),
)


def grid_format_names() -> list[str]:
    """Every grid format switch, in model order."""
    return [name for name, field in LLMCropConfig.model_fields.items()
            if (field.json_schema_extra or {}).get("group") in _FORMAT_GROUPS]


def llm_crop_summary(config: RemangaConfig) -> str:
    llm = config.cropper.llm_crop
    formats = [name for name in grid_format_names() if getattr(llm, name)]
    return (f"{', '.join(formats) or 'no grid formats'} · {llm.grouping} grouping · "
            f"paint-out {'on' if llm.mask_foreign else 'off'}")


def _format_rows(llm: LLMCropConfig) -> list[Choice]:
    rows = []
    for name in grid_format_names():
        field = LLMCropConfig.model_fields[name]
        rows.append(Choice(
            label=field.title or name,
            hint=str((field.json_schema_extra or {}).get("produces", "")),
            detail=field.description or "",
            value=name,
            checked=bool(getattr(llm, name)),
        ))
    return rows


def configure_llm_crop(config: RemangaConfig) -> None:
    """Formats, then grouping, paint-out, previews and the grid image size.
    Every answer is saved as it is given, like every other settings screen."""
    llm = config.cropper.llm_crop
    picked = multiselect(
        "What crop-grid builds for Gemini", _format_rows(llm),
        note="the grid images are drawn either way - these decide which uploads are made from them",
    )
    if is_cancel(picked):
        return
    for name in grid_format_names():
        set_field(config, f"cropper.llm_crop.{name}", name in picked, save=False)
    config.save()
    if llm.grid_zip_splites or llm.pdf_split:
        cap = ask_number("Size cap per grid part, in MB", default=llm.max_mb, minimum=1, maximum=2000,
                         note="each part is kept at or under this by splitting between pages")
        if is_cancel(cap):
            return
        set_field(config, "cropper.llm_crop.max_mb", float(cap))

    grouping = select(
        "How readily should Gemini show several frames as one crop?",
        [Choice(label=name, hint=hint, value=name, badge="current" if name == llm.grouping else "")
         for name, hint in GROUPING_CHOICES],
        default=llm.grouping,
        note="written into each chapter's grid uploads - run crop-grid again for a change to reach Gemini",
    )
    if is_cancel(grouping):
        return
    set_field(config, "cropper.llm_crop.grouping", grouping)

    paint = confirm("Paint other crops' panels and bubbles out of each crop?", default=llm.mask_foreign,
                    note="removes half-bubbles and slivers of the next panel that a crop's rectangle takes in")
    if is_cancel(paint):
        return
    set_field(config, "cropper.llm_crop.mask_foreign", bool(paint))

    preview = confirm("Draw preview images when importing Gemini's crops?", default=llm.preview)
    if is_cancel(preview):
        return
    set_field(config, "cropper.llm_crop.preview", bool(preview))

    size = ask_number("Grid image size, in pixels (each side of the square)", default=llm.grid_image_size,
                      minimum=512, maximum=4096, integer=True,
                      note="each page is scaled to fit on a black square this size, anchored top-left")
    if is_cancel(size):
        return
    set_field(config, "cropper.llm_crop.grid_image_size", int(size))
    console.print(f"[green]✓ LLM crop:[/] {llm_crop_summary(config)}")
