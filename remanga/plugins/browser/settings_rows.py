"""The Settings screen's rows for sites downloaded through Firefox: which
Firefox profile, how slowly, and the remanga helper itself."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remanga.config import RemangaConfig
from remanga.ui.dialogs import Ask, Result, number_check
from remanga.ui.voice_rows import Row

if TYPE_CHECKING:
    from remanga.ui.screens.settings import SettingsScreen

GROUP = "Downloads"


async def _change_profile(screen: SettingsScreen, config: RemangaConfig) -> None:
    from remanga.plugins.browser.helper import profile_folder

    name = await screen.app.push_screen_wait(Ask(
        "Firefox profile", "Profile name (empty: Firefox's default)", value=config.downloader.browser_profile,
        check=lambda text: None if not text.strip() or profile_folder(text.strip())
        else "No Firefox profile has that name.",
        note="The name Firefox's profile menu shows. comix.to is read in that profile, where its "
             "remanga helper is installed and you are signed in."))
    if name is not None:
        config.downloader.browser_profile = name.strip()


async def _change_pace(screen: SettingsScreen, config: RemangaConfig) -> None:
    downloader = config.downloader
    chapter = await screen.app.push_screen_wait(Ask(
        "Download pace", "Pause between two chapters, in seconds",
        value=f"{downloader.browser_chapter_pause_seconds:g}",
        check=number_check(3, 600),
        note="Varied by ±30%. Slower is kinder to the site; under ~5 s reads like a robot."))
    if chapter is None:
        return
    listing = await screen.app.push_screen_wait(Ask(
        "Download pace", "Pause between two pages of the chapter list, in seconds",
        value=f"{downloader.browser_list_pause_seconds:g}", check=number_check(4, 120),
        note="comix.to's firewall asks for a check when its list is turned quickly. The whole list is "
             "read once, then only when it grows."))
    downloader.browser_chapter_pause_seconds = float(chapter)
    if listing is not None:
        downloader.browser_list_pause_seconds = float(listing)


def _helper_state() -> str:
    from remanga.plugins.browser import amo
    from remanga.plugins.browser.helper import manifest

    version = manifest()["version"]
    if amo.is_signed(amo.signed_path(version)):
        return f"{version} - installs for good"
    return f"{version} - " + ("ready to sign" if amo.api_key() else "temporary (no Mozilla key)")


async def _helper(screen: SettingsScreen, config: RemangaConfig) -> None:
    from remanga.plugins.browser import amo
    from remanga.plugins.browser.helper import install_signed

    if not amo.api_key():
        await screen.app.push_screen_wait(Result(screen.path, "remanga helper", [
            "To install it for good (through Firefox restarts) Mozilla signs it as a private add-on, "
            "under your own free addons.mozilla.org account:",
            f"  1. Make an API key at {amo.KEY_PAGE}",
            "  2. In a terminal: ./run.sh helper --set-key",
            "  3. Back here, open this row again.",
            "", "Without it remanga offers the helper as a temporary add-on, until Firefox restarts."], ok=True))
        return
    await screen.run_work("Installing the remanga helper", "Signed by Mozilla, then offered to Firefox",
                          lambda: install_signed(config.downloader.browser_profile))


def rows(config: RemangaConfig) -> list[Row]:
    downloader = config.downloader
    return [
        Row("Firefox profile", downloader.browser_profile or "Firefox's default", _change_profile,
            "where comix.to is read (your sign-in, the helper)", GROUP, ("downloader.browser_profile",)),
        Row("Download pace",
            f"{downloader.browser_chapter_pause_seconds:g} s between chapters · "
            f"{downloader.browser_list_pause_seconds:g} s between list pages", _change_pace,
            "how gently comix.to is read", GROUP,
            ("downloader.browser_chapter_pause_seconds", "downloader.browser_list_pause_seconds")),
        Row("remanga helper", _helper_state(), _helper, "the Firefox extension comix.to is read through - "
            "install or update it", GROUP, ()),
    ]
