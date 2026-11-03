"""The remanga helper extension: packing it into a file Firefox loads, and
saying how to load it.

Firefox only installs signed extensions for good. Unsigned, the helper goes in
as a temporary add-on - in your own profile, in the Firefox you already have
open - until Firefox restarts; `./run.sh helper --install` has Mozilla sign it
under your own addons.mozilla.org account (amo.py) so it stays.

Each copy of remanga gives its helper an ID of its own, kept in
global/browser-helper/extension-id (never committed): Mozilla ties an add-on
ID to the one account that first signs it, so a shared ID would let only one
person ever sign the helper. extension/manifest.json's ID is a placeholder
that every build replaces."""

from __future__ import annotations

import configparser
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import zipfile
from pathlib import Path

from remanga.console import console, escape as _esc
from remanga.paths.roots import GLOBAL_DIR
from remanga.plugins.browser.bridge import pairing_key

EXTENSION_DIR = Path(__file__).resolve().parent / "extension"
XPI_PATH = Path(__file__).resolve().parent / "remanga-helper.xpi"
DEBUGGING_URL = "about:debugging#/runtime/this-firefox"
ID_PATH = GLOBAL_DIR / "browser-helper" / "extension-id"


def extension_id() -> str:
    """This copy's helper ID, made the first time it is needed."""
    if ID_PATH.exists() and ID_PATH.read_text(encoding="utf-8").strip():
        return ID_PATH.read_text(encoding="utf-8").strip()
    made = f"remanga-helper-{secrets.token_hex(6)}@remanga.local"
    ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    ID_PATH.write_text(made + "\n", encoding="utf-8")
    return made


def manifest() -> dict:
    """extension/manifest.json with this copy's own ID in it."""
    meta = json.loads((EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))
    meta["browser_specific_settings"]["gecko"]["id"] = extension_id()
    return meta


def ensure_signed() -> Path:
    """This helper version, signed by Mozilla - made once per version."""
    from remanga.plugins.browser import amo

    meta = manifest()
    version, guid = meta["version"], extension_id()
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
    """extension/ zipped as remanga-helper.xpi with this copy's ID and key in
    it - one file, which Firefox's file picker hands over whole. It holds the
    key: it stays in this copy (gitignored), like the key itself."""
    files = sorted(p for p in EXTENSION_DIR.iterdir() if p.is_file())
    partial = XPI_PATH.with_suffix(".xpi.partial")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.name == "manifest.json":
                archive.writestr(path.name, json.dumps(manifest(), indent=2, ensure_ascii=False) + "\n")
            elif path.name == "pairing.js":
                # This copy's key, so the helper works only with this remanga.
                archive.writestr(path.name, f'const REMANGA_PAIRING_KEY = "{pairing_key()}";\n')
            else:
                archive.write(path, path.name)
    partial.chmod(0o600)  # it holds this copy's pairing key
    partial.replace(XPI_PATH)
    return XPI_PATH


# Where Firefox keeps its profiles (under your home folder): Linux - a plain
# install, the snap, the flatpak - then macOS and Windows.
FIREFOX_ROOTS = (".mozilla/firefox", "snap/firefox/common/.mozilla/firefox",
                 ".var/app/org.mozilla.firefox/.mozilla/firefox", "Library/Application Support/Firefox",
                 "AppData/Roaming/Mozilla/Firefox")
FIREFOX_PROGRAMS = ("/Applications/Firefox.app/Contents/MacOS/firefox",
                    os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
                    os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"))


def firefox_program() -> str | None:
    return shutil.which("firefox") or next((p for p in FIREFOX_PROGRAMS if Path(p).is_file()), None)


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
    firefox = firefox_program()
    if not firefox:
        return False
    folder = profile_folder(profile) if profile else None
    if folder and folder.resolve() in _default_folders() and firefox_running() is not False:
        # The default profile, already open: a plain `firefox URL` reaches it
        # (a running Firefox given --profile can refuse).
        chosen = []
    else:
        # Starting Firefox: named outright, so a profile chooser set to show at
        # startup doesn't stop it with no profile (and no helper) loaded.
        chosen = ["--profile", str(folder)] if folder else (["-P", profile] if profile else [])
    args = [firefox, *chosen, url]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return True


def firefox_running() -> bool | None:
    """Whether Firefox is running (None: can't tell on this system)."""
    if not shutil.which("pgrep"):
        return None
    return subprocess.run(["pgrep", "-x", "firefox"], stdout=subprocess.DEVNULL).returncode == 0


def explain_loading(profile: str = "") -> None:
    from remanga.plugins.browser import amo

    where = f"Firefox (profile {profile})" if profile else "Firefox"
    if amo.is_signed(amo.signed_path(manifest()["version"])):
        # Installed for good: it only needs Firefox open.
        started = firefox_running() is False and open_in_firefox("about:home", profile)
        console.print(
            f"\n[bold yellow]Waiting for the remanga helper in {_esc(where)}[/]"
            + (" - starting Firefox." if started else " - it connects by itself while Firefox is open.")
            + "\n  [dim]Removed it? ./run.sh helper --install puts it back. Ctrl+C to stop waiting.[/]\n"
        )
        return
    xpi = build_xpi()
    opened = open_in_firefox(DEBUGGING_URL, profile)
    console.print(
        f"\n[bold yellow]Waiting for the remanga helper in {_esc(where)}.[/]\n"
        f"  1. In {_esc(where)}, {'the tab remanga just opened: ' if opened else 'open '}"
        f"[bold]{DEBUGGING_URL}[/]\n"
        "  2. [bold]Load Temporary Add-on…[/] and choose this file (Ctrl+L to paste the path):\n"
        f"     [cyan]{_esc(str(xpi))}[/]\n"
        "  It stays loaded until Firefox restarts - `./run.sh helper` installs it for good. remanga carries on "
        "by itself once it is in - Ctrl+C to stop waiting.\n"
    )


def explain_reloading(old_version: str, profile: str = "") -> None:
    open_in_firefox(DEBUGGING_URL, profile)
    console.print(
        f"\n[bold yellow]The remanga helper in Firefox is version {_esc(old_version)} - remanga has a newer one.[/]\n"
        f"  In the about:debugging tab remanga just opened, click [bold]Reload[/] under remanga helper.\n"
        "  (From this version on the helper updates itself.) remanga carries on by itself.\n"
    )
