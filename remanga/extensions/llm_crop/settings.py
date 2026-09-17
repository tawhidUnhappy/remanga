"""The LLM crop settings screen: which grid uploads `crop-grid` builds, how
readily Gemini groups panels, and how its crops are cut.

The format checklist is generated from LLMCropConfig's Field metadata
(remanga.settings.format_switches, shared with page narration), the way the
packaging checklist is generated from PackageConfig's - a new grid format is
one field, not a field plus a menu row.

set_field is imported where it is used: this module is loaded while the
settings package is still building its section list (see
remanga.extensions.spec), and importing the package's own modules at the top
would ask it for itself."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.extensions.llm_crop.config import LLMCropConfig
from remanga.settings.format_switches import FormatSwitches
from remanga.tui import Choice, ask_number, confirm, is_cancel, multiselect, select

FIELD_PREFIX = "extensions.llm_crop"

GROUPING_CHOICES: tuple[tuple[str, str], ...] = (
    ("balanced", "groups only frames too slight to narrate alone - silent inserts, small reaction shots"),
    ("none", "every frame is its own crop"),
    ("generous", "also groups a tier or a column that shows the same scene"),
)


GRID_FORMATS = FormatSwitches(LLMCropConfig, FIELD_PREFIX, ("pages", "zip", "pdf"), "grid",
                              "Settings → LLM crop")


def llm_crop_summary(config: RemangaConfig) -> str:
    llm = config.extensions.llm_crop
    formats = GRID_FORMATS.active(llm)
    ruler = f"{llm.grid_image_size}px grid" + (f", ticks every {llm.grid_tick_step}"
                                                if llm.grid_tick_step else ", no ticks")
    return (f"{', '.join(formats) or 'no grid formats'} · {llm.grouping} grouping · "
            f"paint-out {'on' if config.cropper.paint_out else 'off'} · {ruler}")


def configure_llm_crop(config: RemangaConfig) -> None:
    """Formats, then grouping, paint-out, previews and the grid image size.
    Every answer is saved as it is given, like every other settings screen."""
    from remanga.settings.fields import set_field

    llm = config.extensions.llm_crop
    picked = multiselect(
        "What crop-grid builds for Gemini", GRID_FORMATS.rows(llm),
        note="the grid images are drawn either way - these decide which uploads are made from them",
    )
    if is_cancel(picked):
        return
    for name in GRID_FORMATS.names():
        set_field(config, f"{FIELD_PREFIX}.{name}", name in picked, save=False)
    config.save()
    if llm.grid_zip_splites or llm.pdf_active:
        cap = ask_number("Size cap per grid file, in MB", default=llm.max_mb, minimum=1, maximum=2000,
                         note="no grid PDF goes over this - pages stay lossless when they fit, near-lossless "
                              "when they don't · split zips are cut into parts under it")
        if is_cancel(cap):
            return
        set_field(config, f"{FIELD_PREFIX}.max_mb", float(cap))

    grouping = select(
        "How readily should Gemini show several frames as one crop?",
        [Choice(label=name, hint=hint, value=name, badge="current" if name == llm.grouping else "")
         for name, hint in GROUPING_CHOICES],
        default=llm.grouping,
        note="written into each chapter's grid uploads - run crop-grid again for a change to reach Gemini",
    )
    if is_cancel(grouping):
        return
    set_field(config, f"{FIELD_PREFIX}.grouping", grouping)

    paint = confirm("Paint other crops' panels and bubbles out of each crop?", default=config.cropper.paint_out,
                    note="removes half-bubbles and slivers of the next panel that a crop's rectangle takes in")
    if is_cancel(paint):
        return
    set_field(config, "cropper.paint_out", bool(paint))

    preview = confirm("Draw preview images when importing Gemini's crops?", default=llm.preview)
    if is_cancel(preview):
        return
    set_field(config, f"{FIELD_PREFIX}.preview", bool(preview))

    size = ask_number("Grid image size, in pixels (each side of the square)", default=llm.grid_image_size,
                      minimum=512, maximum=4096, integer=True,
                      note="each page is scaled to fit on a black square this size, anchored top-left · "
                           "bigger keeps the ruler's ticks apart once Gemini scales the image down")
    if is_cancel(size):
        return
    set_field(config, f"{FIELD_PREFIX}.grid_image_size", int(size))

    ticks = ask_number("Ruler ticks every N units (0 for none)", default=llm.grid_tick_step,
                       minimum=0, maximum=100, integer=True,
                       note="along the four edges and across every labeled line, so an edge between two "
                            "lines is counted rather than estimated · finer than 10 needs a bigger square")
    if is_cancel(ticks):
        return
    set_field(config, f"{FIELD_PREFIX}.grid_tick_step", int(ticks))
    console.print(f"[green]✓ LLM crop:[/] {llm_crop_summary(config)}")
