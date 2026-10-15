"""Work through Firefox: the bridge up, the helper there (or how to load it),
each job's progress said, and the remanga tab closed once the work is over.

One session is shared by everything in a run of remanga: a list of chapters
downloaded one step at a time (the menus, the queue) keeps the same tab, and
the pause between two chapters holds across them. The tab closes a little
after the last job, or when remanga exits."""

from __future__ import annotations

import atexit
import json
import random
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

from remanga import activity
from remanga.config import DownloaderConfig
from remanga.console import console, escape as _esc
from remanga.paths.roots import REPO_ROOT
from remanga.plugins.browser.bridge import HELPER_VERSION, Bridge, HelperError, Job
from remanga.plugins.browser.helper import build_xpi, explain_loading, explain_reloading, install_signed

# The last page each kind of job looked at, for fixing the helper when a site
# changes its reader.
DISCOVERY_DIR = REPO_ROOT / ".cache" / "browser"
# How long the remanga tab stays after the last job, for the next one.
IDLE_CLOSE_SECONDS = 90

_lock = threading.RLock()
_jobs = threading.Lock()  # one job at a time through the one tab
_shared: dict[str, Any] = {"bridge": None, "users": 0, "timer": None, "last_chapter": 0.0}


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
                              f"tab; remanga waits.[/]")
                activity.status("solve the check in Firefox's remanga tab")
            elif state == "loading" and said_check:
                said_check = False
                console.print("[green]Check passed.[/]")
                activity.status("check passed")
            elif state == "opening":
                console.print(f"[dim]Opening {_esc(message)}[/]")
                activity.status("reading the site in Firefox…")
            elif state == "reading":
                activity.status(message)

        with _jobs:
            job = self.bridge.run(kind, payload, on_status=on_status, timeout=timeout)
        data = (job.result or {}).get("data") or {}
        if data.get("discovery"):
            # Page text can hold your account name on the site: readable only by you.
            DISCOVERY_DIR.mkdir(parents=True, exist_ok=True)
            target = DISCOVERY_DIR / f"last-{kind}.json"
            target.write_text(json.dumps(data["discovery"], indent=1), encoding="utf-8")
            target.chmod(0o600)
        return job

    def pace_chapter(self) -> None:
        """The pause between two chapters (varied by +-30%), counted from the
        end of the last one - also when they are downloaded one step at a time."""
        pause = self.config.browser_chapter_pause_seconds * random.uniform(0.7, 1.3)
        left = _shared["last_chapter"] + pause - time.time()
        if left > 0:
            activity.status(f"pausing {left:.0f} s between chapters")
            time.sleep(left)

    def chapter_done(self) -> None:
        _shared["last_chapter"] = time.time()


def _update(bridge: Bridge, config: DownloaderConfig) -> None:
    """An older helper in Firefox: a temporary one ("development"; helpers
    before 0.6 say nothing) is asked to read its file again (the one made just
    now); an installed one is offered the signed new version, which Firefox
    installs over it with one click."""
    if bridge.helper_install not in ("development", ""):  # installed: normal, sideload, ...
        console.print(f"[yellow]The remanga helper in Firefox is version {_esc(bridge.helper_version)}; "
                      f"this remanga has {HELPER_VERSION}.[/]")
        activity.status("Firefox asks to update the remanga helper - click Update")
        install_signed(config.browser_profile)
    else:
        build_xpi()
        with suppress(HelperError):
            bridge.run("reload", {}, timeout=20)
        if not bridge.wait_for_version(HELPER_VERSION, 20):
            explain_reloading(bridge.helper_version, config.browser_profile)
    bridge.wait_for_version(HELPER_VERSION, None)
    console.print(f"[green]The remanga helper is now version {HELPER_VERSION}.[/]")


def _close_shared(force: bool = False) -> None:
    """The remanga tab closed and the bridge stopped - unless work came back."""
    with _lock:
        bridge = _shared["bridge"]
        if bridge is None or (_shared["users"] and not force):
            return
        _shared["bridge"] = None
    # A job stopped mid-way (Ctrl+C) may still hold the tab: not waited on for long.
    if _jobs.acquire(timeout=15):
        try:
            with suppress(Exception):  # Firefox closed, or remanga stopping: nothing left to tidy
                bridge.run("finish", {}, timeout=10)
        finally:
            _jobs.release()
    bridge.__exit__(None, None, None)


atexit.register(_close_shared, True)


@contextmanager
def helper_session(config: DownloaderConfig, wait: float | None = None, quiet: bool = False) -> Iterator[Session]:
    """`wait`: how long to wait for the helper (None: until it is loaded or
    Ctrl+C). `quiet`: when it isn't there, don't start Firefox or say how to
    load it - just give up after `wait` (work that can do without it)."""
    with _lock:
        if _shared["timer"]:
            _shared["timer"].cancel()
            _shared["timer"] = None
        if _shared["bridge"] is None:
            _shared["bridge"] = Bridge().__enter__()
        bridge = _shared["bridge"]
        _shared["users"] += 1
    try:
        if not bridge.connected() and not quiet:
            activity.status("waiting for the remanga helper in Firefox…")
        on_wait = None if quiet else (lambda: explain_loading(config.browser_profile))
        if not bridge.wait_for_helper(wait, on_wait=on_wait):
            raise HelperError("The remanga helper isn't loaded in Firefox.")
        if not bridge.ready():
            # Older, or without this copy's key (another copy's helper, or one from before pairing).
            _update(bridge, config)
        yield Session(bridge, config)
    finally:
        with _lock:
            _shared["users"] -= 1
            if _shared["users"] == 0:
                timer = threading.Timer(IDLE_CLOSE_SECONDS, _close_shared)
                timer.daemon = True
                timer.start()
                _shared["timer"] = timer
