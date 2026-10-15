"""The remanga helper extension: packing it into a file Firefox loads, and
saying how to load it.

Firefox only installs signed extensions for good, so the helper goes in as a
temporary add-on - in your own profile, in the Firefox you already have open -
and stays until Firefox restarts. remanga says when it isn't there."""

from __future__ import annotations

import configparser
import json
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

from remanga.console import console, escape as _esc

EXTENSION_DIR = Path(__file__).resolve().parent / "extension"
XPI_PATH = Path(__file__).resolve().parent / "remanga-helper.xpi"
DEBUGGING_URL = "about:debugging#/runtime/this-firefox"


def manifest() -> dict:
    return json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))


def ensure_signed() -> Path:
    """This helper version, signed by Mozilla - made once per version."""
    from remanga.plugins.browser import amo

    meta = manifest()
    version, guid = meta["version"], meta["browser_specific_settings"]["gecko"]["id"]
    path = amo.signed_path(version)
    if path.exists() and amo.is_signed(path):
        return path
    return amo.sign(build_xpi(), guid, version)


def install_signed(profile: str = "") -> Path:
    """Opens the signed helper in Firefox, which asks to add (or update) it -
    installed for good, like any extension."""
    path = ensure_signed()
    open_in_firefox(path.resolve().as_uri(), profile)
    console.print(f"[bold]Firefox now asks to add remanga helper {manifest()['version']}[/] - click [bold]Add[/] "
                  "(or Update). Then it stays installed through restarts.\n"
                  "  [dim]If no prompt appears: about:addons → gear → Install Add-on From File… → "
                  f"{_esc(str(path))}[/]")
    return path


def build_xpi() -> Path:
    """extension/ zipped as remanga-helper.xpi, remade whenever a file in it
    is newer - one file, which Firefox's file picker hands over whole."""
    files = sorted(p for p in EXTENSION_DIR.iterdir() if p.is_file())
    if XPI_PATH.exists() and all(p.stat().st_mtime <= XPI_PATH.stat().st_mtime for p in files):
        return XPI_PATH
    partial = XPI_PATH.with_suffix(".xpi.partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.name)
    partial.replace(XPI_PATH)
    return XPI_PATH


# Where Firefox keeps its profiles: a plain install, the snap, the flatpak.
FIREFOX_ROOTS = (".mozilla/firefox", "snap/firefox/common/.mozilla/firefox",
                 ".var/app/org.mozilla.firefox/.mozilla/firefox")


def profile_folder(name: str) -> Path | None:
    """The folder of the Firefox profile called `name` - the name Firefox's
    profile menu shows (kept in "Profile Groups/*.sqlite" since profiles got
    names and avatars) or the older profiles.ini one."""
    for root in (Path.home() / r for r in FIREFOX_ROOTS):
        ini = configparser.ConfigParser()
        ini.read(root / "profiles.ini")
        for section in ini.sections():
            if ini.get(section, "Name", fallback="").casefold() == name.casefold() and ini.has_option(section, "Path"):
                path = ini.get(section, "Path")
                return root / path if ini.get(section, "IsRelative", fallback="1") == "1" else Path(path)
        for groups in sorted((root / "Profile Groups").glob("*.sqlite")):
            try:
                with sqlite3.connect(f"file:{groups}?mode=ro", uri=True) as db:
                    row = db.execute("SELECT path FROM Profiles WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
            except sqlite3.Error:
                continue
            if row:
                return root / row[0]
    return None


def _default_folders() -> set[Path]:
    """The profile folders Firefox opens when given none (profiles.ini's
    Install default, or the profile marked Default=1)."""
    folders = set()
    for root in (Path.home() / r for r in FIREFOX_ROOTS):
        ini = configparser.ConfigParser()
        ini.read(root / "profiles.ini")
        for section in ini.sections():
            if section.startswith("Install") and ini.has_option(section, "Default"):
                folders.add((root / ini.get(section, "Default")).resolve())
            elif ini.get(section, "Default", fallback="") == "1" and ini.has_option(section, "Path"):
                folders.add((root / ini.get(section, "Path")).resolve())
    return folders


def open_in_firefox(url: str, profile: str = "") -> bool:
    """Opens `url` as a tab in the Firefox already running with `profile`
    (Firefox's default profile when empty) - or starts it."""
    firefox = shutil.which("firefox")
    if not firefox:
        return False
    folder = profile_folder(profile) if profile else None
    if folder and folder.resolve() in _default_folders():
        chosen = []  # the default profile: a plain `firefox URL` reaches it, running or not
    else:
        chosen = ["--profile", str(folder)] if folder else (["-P", profile] if profile else [])
    args = [firefox, *chosen, url]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True


def explain_loading(profile: str = "") -> None:
    xpi = build_xpi()
    opened = open_in_firefox(DEBUGGING_URL, profile)
    where = f"Firefox (profile {profile})" if profile else "Firefox"
    console.print(
        f"\n[bold yellow]Waiting for the remanga helper in {_esc(where)}.[/]\n"
        f"  1. In {_esc(where)}, {'the tab remanga just opened: ' if opened else 'open '}"
        f"[bold]{DEBUGGING_URL}[/]\n"
        "  2. [bold]Load Temporary Add-on…[/] and choose this file (Ctrl+L to paste the path):\n"
        f"     [cyan]{_esc(str(xpi))}[/]\n"
        "  It stays loaded until Firefox restarts. remanga carries on by itself once it is in - "
        "Ctrl+C to stop waiting.\n"
    )


def explain_reloading(old_version: str, profile: str = "") -> None:
    open_in_firefox(DEBUGGING_URL, profile)
    console.print(
        f"\n[bold yellow]The remanga helper in Firefox is version {_esc(old_version)} - remanga has a newer one.[/]\n"
        f"  In the about:debugging tab remanga just opened, click [bold]Reload[/] under remanga helper.\n"
        "  (From this version on the helper updates itself.) remanga carries on by itself.\n"
    )
