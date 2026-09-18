"""Running one of remanga's local web UIs: the server, the browser tab, and
the wait for the person using it.

All three work the same way - a Flask app bound to localhost, a browser
opened at it, and the calling thread blocked until the page says it is
finished: the Panel Marker (server.py), the Narration Reviewer
(reviewer_server.py) and the Narration Writer (writer_server.py). What
differs is only what each prints and what it does afterwards, so everything
else lives here."""

from __future__ import annotations

import logging
import threading
import webbrowser
from collections.abc import Sequence
from dataclasses import dataclass

from werkzeug.serving import make_server

from remanga.console import console

# werkzeug's dev server logs every single request at INFO level by default
# ("127.0.0.1 - - [...] "GET /api/detect/status HTTP/1.1" 200 -"). The
# frontend polls a couple of status endpoints (page-nav.js) every ~1.2s for
# as long as the marker UI or MAGI detection is running, so left alone this
# floods the terminal with access-log lines - including right on top of the
# "Loading MAGI v3..." spinner (magi_assist.py's console.status()), which is
# what turned a clean progress spinner into a wall of spam. Only warnings/
# errors (a real 500, a bad request) are worth surfacing here.
logging.getLogger("werkzeug").setLevel(logging.WARNING)


@dataclass
class RunningUI:
    """A UI that is up and being used: where it is, and the wait for it."""

    url: str
    finished: threading.Event
    thread: threading.Thread

    def wait(self, waiting_for: str) -> None:
        """Blocks until the browser ends the session, saying what it is
        waiting for - the one line the terminal shows while the UI is open."""
        console.print(f"[yellow]Waiting for you to {waiting_for}...[/]")
        self.finished.wait()
        self.thread.join(timeout=5)


def start_ui(app, config, finished: threading.Event, *, title: str, title_note: str = "",
             notes: Sequence[str] = ()) -> RunningUI:
    """Serves `app` on this UI's configured host/port and opens the browser
    at it, unless the config says not to. `config` is any of the web UI
    configs - they all carry host, port and auto_open_browser.

    `finished` is the event the UI's own state sets when the person is done;
    a daemon thread waits on it and shuts the server down, so the browser
    ends the session rather than the terminal having to."""
    httpd = make_server(config.host, config.port, app)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    console.print(f"[bold cyan]{title} running at:[/] {url}{title_note}")
    for note in notes:
        console.print(note)
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    return RunningUI(url, finished, server_thread)
