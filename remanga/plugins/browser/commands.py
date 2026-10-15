"""`./run.sh helper`: where the remanga helper stands, saving the
addons.mozilla.org API key, and installing the signed helper."""

from __future__ import annotations

import getpass
import json
import os

from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.plugins.browser import amo
from remanga.plugins.browser.helper import install_signed, manifest


def _set_key() -> None:
    console.print(f"Your addons.mozilla.org API key - make one at [cyan]{amo.KEY_PAGE}[/] "
                  "(\"Generate new credentials\").")
    issuer = input("  JWT issuer (looks like user:12345:67): ").strip()
    secret = getpass.getpass("  JWT secret (not shown): ").strip()
    if not issuer.startswith("user:") or not secret:
        raise ValueError("That doesn't look like an addons.mozilla.org key - nothing saved.")
    amo.KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(amo.KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump({"issuer": issuer, "secret": secret}, handle)
    amo.KEY_PATH.chmod(0o600)  # also when the file was there before, with other permissions
    console.print(f"[green]✓ Saved[/] [dim]({_esc(str(amo.KEY_PATH))}, readable only by you)[/]")


def helper_command(set_key: bool = False, install: bool = False) -> None:
    if set_key:
        _set_key()
    if install:
        install_signed(RemangaConfig.load().downloader.browser_profile)
        return
    version = manifest()["version"]
    signed = amo.signed_path(version)
    has_key = amo.api_key() is not None
    console.print(f"\n[bold]remanga helper {version}[/] - the Firefox extension comix.to downloads go through.")
    shown = f"[green]{_esc(str(signed))}[/]" if amo.is_signed(signed) else "[dim]not yet[/]"
    console.print(f"  signed file:  {shown}")
    console.print(f"  API key:      {'[green]saved[/]' if has_key else '[yellow]not saved[/]'}")
    console.print(
        "\n[bold]Installing it for good[/] (stays through Firefox restarts):\n"
        + ("" if has_key else
           "  1. Sign in (or sign up, free) at https://addons.mozilla.org, open\n"
           f"     {amo.KEY_PAGE} and press \"Generate new credentials\".\n"
           "  2. ./run.sh helper --set-key   and paste the two values.\n")
        + f"  {'1' if has_key else '3'}. ./run.sh helper --install   Mozilla signs it as a private (unlisted)\n"
          "     add-on - a few minutes - and Firefox asks to add it.\n"
          "  After that a newer helper is offered the same way, by itself, when remanga needs it.\n"
    )
