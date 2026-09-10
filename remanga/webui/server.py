"""Local web server for the panel-marking UI: replaces the old "paste crops.json
from an LLM" wizard step. Launches a Flask app bound to localhost, opens the
user's browser to it, and blocks the calling thread until the user is done, at
which point crops.json has been written in the exact schema the rest of the
pipeline (remanga/cropper/crop.py onward) already expects - so gutter-snap, seam
reconciliation, dedup, and whitespace trim all still run on top of these marks,
same as they did on LLM-produced ones.

One tab can cover any number of chapters. `launch_and_wait_all` takes a list and
the browser walks through them without ever reloading: each Save writes that
chapter's crops.json and hands the next chapter's pages to the same tab, and the
chapter arrows go back to one already done. `launch_and_wait` (one chapter) is
that same thing with a one-item list, so the single-chapter callers - the `mark`
command, the pipeline's mark step, a "remark" restart - are unchanged.

This module is just the entry points and process lifecycle - see
marker_session.py for the chapter list and cursor, marker_state.py for one
chapter's in-memory state, detection.py for the background MAGI thread,
routes.py for the Flask app/API, and settings_store.py for how the Shortcuts
menu's edits get saved.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from remanga.config import MarkerConfig
from remanga.console import console
from remanga.paths import get_chapter_dir
from remanga.webui.marker_session import MarkerSession
from remanga.webui.routes import create_app

# werkzeug's dev server logs every single request at INFO level by default
# ("127.0.0.1 - - [...] "GET /api/detect/status HTTP/1.1" 200 -"). The
# frontend polls a couple of status endpoints (page-nav.js) every ~1.2s for
# as long as the marker UI or MAGI detection is running, so left alone this
# floods the terminal with access-log lines - including right on top of the
# "Loading MAGI v3..." spinner (magi_assist.py's console.status()), which is
# what turned a clean progress spinner into a wall of spam. Only warnings/
# errors (a real 500, a bad request) are worth surfacing here.
logging.getLogger("werkzeug").setLevel(logging.WARNING)


def launch_and_wait(project_name: str, chapter_num: str, config: MarkerConfig) -> Path:
    """Starts the marking web UI for ONE chapter, opens the browser, and
    blocks until the user saves. Returns the path to the crops.json it
    wrote."""
    launch_and_wait_all(project_name, [chapter_num], config)
    return get_chapter_dir(project_name, chapter_num) / "crops.json"


def launch_and_wait_all(project_name: str, chapters: list[str], config: MarkerConfig,
                        read_only: bool = False) -> list[Path]:
    """Starts the marking web UI over `chapters`, opens ONE browser tab, and
    blocks until the session ends - either because the last chapter was
    saved, or because the user ended it early from the browser. Returns the
    crops.json paths actually written, in the order they were saved.

    Chapters with nothing downloaded are dropped before the browser opens
    rather than presented as empty pages to mark: they are named in the
    terminal, because "chapter 7 was skipped" is something to see once, not
    to discover twenty chapters later."""
    session = MarkerSession(project_name, chapters, read_only=read_only)
    if session.skipped:
        console.print(
            f"[yellow]Skipping {len(session.skipped)} chapter(s) with no downloaded pages:[/] "
            f"{', '.join(session.skipped)}"
        )

    httpd = make_server(config.host, config.port, create_app(session, config))
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        session.finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    title = "Panel Viewer" if read_only else "Panel Marker"
    console.print(f"[bold cyan]{title} running at:[/] {url}")
    if read_only:
        console.print("[dim]Read-only: nothing you do in this tab can change a crops.json.[/]")
    if len(session.chapters) > 1:
        console.print(
            f"[dim]{len(session.chapters)} chapter(s) in this session: "
            f"{', '.join(session.chapters)} — the browser moves between them, one tab.[/]"
        )
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    # The saved switches (config.json's marker section) are what this session
    # opens with: auto-save as it was left, and - if the last session turned
    # it on - the whole project queued for detection before anyone clicks
    # anything.
    session.auto_save = config.auto_save
    session.auto_order = config.auto_order
    if config.auto_detect_all:
        session.set_auto_all(True, config)
    else:
        session.start_detection(config)

    if read_only:
        waiting_for = "look through the marks and close the session in the browser"
    elif len(session.chapters) == 1:
        waiting_for = "mark panels and save (Ctrl/Cmd+S in the browser)"
    else:
        waiting_for = "mark every chapter and finish in the browser"
    console.print(f"[yellow]Waiting for you to {waiting_for}...[/]")
    session.finished.wait()
    server_thread.join(timeout=5)

    return session.saved
