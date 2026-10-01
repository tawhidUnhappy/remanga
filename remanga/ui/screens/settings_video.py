"""The settings screen's Video and PDF rows: what each offers and how
it changes the config. The screen itself is settings.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.ui.dialogs import Ask, Choice, number_check
from remanga.video.intro import INTRO_EXTS

if TYPE_CHECKING:
    from remanga.ui.screens.settings import SettingsScreen


UPSCALE_CAPS = ((2.0, "sharpest - small panels sit noticeably small"),
                (3.0, "balanced - recommended"),
                (4.0, "fuller frame, a little softer"),
                (0.0, "no cap - every panel fills the frame, small ones look soft"))


RESOLUTIONS = ((1920, 1080, "1080p widescreen"), (2560, 1440, "1440p - keeps bigger panels sharp"),
               (3840, 2160, "4K - slowest to render"), (1280, 720, "720p widescreen"),
               (1080, 1920, "1080p vertical"), (1440, 2560, "1440p vertical"))


async def change_intro(screen: SettingsScreen, config: RemangaConfig) -> None:
    folder = GLOBAL_DIR / "intro"
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in INTRO_EXTS) if folder.exists() else []
    current = config.video.intro_path if config.video.intro_enabled else "off"
    picked = await screen.app.push_screen_wait(Choice(
        "Intro", [("No intro", "", "off")] + [(p.name, "", str(p)) for p in files],
        current=current, note=f"Played before every recap. Put intro videos in {folder}/"))
    if picked == "off":
        config.video.intro_enabled = False
    elif picked:
        config.video.intro_path, config.video.intro_enabled = picked, True


async def change_video_size(screen: SettingsScreen, config: RemangaConfig) -> None:
    size = await screen.app.push_screen_wait(Choice(
        "Video size", [(f"{w}x{h}", label, (w, h)) for w, h, label in RESOLUTIONS],
        current=(config.video.width, config.video.height),
        note="Panels are cut at the page's own resolution, so a bigger video keeps more of them at "
             "full detail - making a video says which panels it would shrink."))
    if size:
        config.video.width, config.video.height = size


async def change_max_upscale(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Choice(
        "Panel enlargement limit", [(f"up to {c:g}x" if c else "no cap", hint, c) for c, hint in UPSCALE_CAPS],
        current=config.video.max_upscale,
        note="A small panel blown up to fill a 4K frame has nothing to fill it with and looks soft. "
             "Capped, it sits smaller and stays sharp."))
    if cap is not None:
        config.video.max_upscale = cap


async def change_pdf_cap(screen: SettingsScreen, config: RemangaConfig) -> None:
    cap = await screen.app.push_screen_wait(Ask(
        "PDF file size limit", "Largest PDF file, in MB", value=f"{config.pdf.max_mb:g}",
        check=number_check(1, 2000),
        note="A chapter bigger than this is split into panels_1.pdf, panels_2.pdf, ..."))
    if cap is not None:
        config.pdf.max_mb = float(cap)
