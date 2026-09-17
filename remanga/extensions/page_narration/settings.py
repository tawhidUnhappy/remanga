"""The page narration settings screen: which pages uploads `page-upload`
builds, and their size cap. The checklist is generated from
PageNarrationConfig's Field metadata (remanga.settings.format_switches)."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.extensions.page_narration.config import PageNarrationConfig
from remanga.settings.format_switches import FormatSwitches
from remanga.tui import ask_number, is_cancel, multiselect

FIELD_PREFIX = "extensions.page_narration"
PAGE_FORMATS = FormatSwitches(PageNarrationConfig, FIELD_PREFIX, ("pdf",), "pages", "Settings → Page narration")


def page_narration_summary(config: RemangaConfig) -> str:
    settings = config.extensions.page_narration
    return f"{', '.join(PAGE_FORMATS.active(settings)) or 'no pages formats'} · capped at {settings.max_mb:g}MB"


def configure_page_narration(config: RemangaConfig) -> None:
    from remanga.settings.fields import set_field

    settings = config.extensions.page_narration
    picked = multiselect("What page-upload builds", PAGE_FORMATS.rows(settings), allow_empty=False,
                         note="the pages themselves, unchanged - these decide which files they go into")
    if is_cancel(picked):
        return
    for name in PAGE_FORMATS.names():
        set_field(config, f"{FIELD_PREFIX}.{name}", name in picked, save=False)
    config.save()
    cap = ask_number("Size cap per pages file, in MB", default=settings.max_mb, minimum=1, maximum=2000,
                     note="no pages PDF goes over this - pages stay as they are when they fit, "
                          "near-lossless when they don't")
    if is_cancel(cap):
        return
    set_field(config, f"{FIELD_PREFIX}.max_mb", float(cap))
    console.print(f"[green]✓ Page narration:[/] {page_narration_summary(config)}")
