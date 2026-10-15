"""One stretch of work through Firefox: the bridge up, the helper there (or
how to load it), each job's progress said in the terminal, and the remanga
window closed at the end."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.paths.roots import REPO_ROOT
from remanga.plugins.browser.bridge import HELPER_VERSION, Bridge, HelperError, Job
from remanga.plugins.browser.helper import build_xpi, explain_loading, explain_reloading, install_signed

# The last page each kind of job looked at, for fixing the helper when a site
# changes its reader.
DISCOVERY_DIR = REPO_ROOT / ".cache" / "browser"


class Session:
    def __init__(self, bridge: Bridge, config: DownloaderConfig):
        self.bridge = bridge
        self.config = config

    def run(self, kind: str, payload: dict[str, Any], timeout: float = 900) -> Job:
        said_check = False

        def on_status(state: str, message: str) -> None:
            nonlocal said_check
            if state == "challenge" and not said_check:
                said_check = True
                console.print(f"[bold yellow]Firefox shows a check ({_esc(message)}) - solve it in the remanga "
                              f"window; remanga waits.[/]")
            elif state == "loading" and said_check:
                said_check = False
                console.print("[green]Check passed.[/]")
            elif state == "opening":
                console.print(f"[dim]Opening {_esc(message)}[/]")

        job = self.bridge.run(kind, payload, on_status=on_status, timeout=timeout)
        data = (job.result or {}).get("data") or {}
        if data.get("discovery"):
            # Page text can hold your account name on the site: readable only by you.
            DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
            target = DISCOVERY_DIR / f"last-{kind}.json"
            target.write_text(json.dumps(data["discovery"], indent=1), encoding="utf-8")
            target.chmod(0o600)
        return job


def _update(bridge: Bridge, config: DownloaderConfig) -> None:
    """An older helper in Firefox: a temporary one ("development"; helpers
    before 0.6 say nothing) is asked to read its file again (the one made just
    now); an installed one is offered the signed new version, which Firefox
    installs over it with one click."""
    if bridge.helper_install not in ("development", ""):  # installed: normal, sideload, ...
        console.print(f"[yellow]The remanga helper in Firefox is version {_esc(bridge.helper_version)}; "
                      f"this remanga has {HELPER_VERSION}.[/]")
        install_signed(config.browser_profile)
    else:
        build_xpi()
        with suppress(HelperError):
            bridge.run("reload", {}, timeout=20)
        if not bridge.wait_for_version(HELPER_VERSION, 20):
            explain_reloading(bridge.helper_version, config.browser_profile)
    bridge.wait_for_version(HELPER_VERSION, None)
    console.print(f"[green]The remanga helper is now version {HELPER_VERSION}.[/]")


@contextmanager
def helper_session(config: DownloaderConfig, wait: float | None = None) -> Iterator[Session]:
    """`wait`: how long to wait for the helper (None: until it is loaded or
    Ctrl+C)."""
    with Bridge() as bridge:
        if not bridge.wait_for_helper(wait, on_wait=lambda: explain_loading(config.browser_profile)):
            raise HelperError("The remanga helper isn't loaded in Firefox.")
        if not bridge.ready():
            # Older, or without this copy's key (another copy's helper, or one from before pairing).
            _update(bridge, config)
        try:
            yield Session(bridge, config)
        finally:
            with suppress(Exception):  # Firefox closed, or Ctrl+C: nothing left to tidy
                bridge.run("finish", {}, timeout=15)
