"""Local web server for the Narration Writer UI: a panel-by-panel pass where
the user types the narration text themselves instead of an LLM writing it.
Launches a Flask app bound to localhost, opens the user's browser to it, and
blocks the calling thread until the user hits Save, at which point it writes
narration.json (see paths.py).

This module is just the entry point (launch_and_wait_writer) and process
lifecycle - see writer_state.py for the in-memory session state and
writer_routes.py for the Flask app/API. Mirrors reviewer_server.py's shape;
kept as a separate module since all three UIs serve different stages and
can, in principle, be open at once on different ports.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from remanga.config import WriterConfig
from remanga.console import console
from remanga.paths import get_chapter_dir
from remanga.webui.writer_routes import create_writer_app
from remanga.webui.writer_state import WriterState

logging.getLogger("werkzeug").setLevel(logging.WARNING)


def launch_and_wait_writer(project_name: str, chapter_num: str, config: WriterConfig) -> Path:
    """Starts the Narration Writer web UI, opens the browser, and blocks
    until the user saves. Returns the path to narration.json it wrote."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = WriterState(chapter_dir, chapter_num)

    httpd = make_server(config.host, config.port, create_writer_app(state, config, project_name))
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        state.finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    console.print(f"[bold cyan]Narration Writer running at:[/] {url}")
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    console.print("[yellow]Waiting for you to write the narration and save...[/]")
    state.finished.wait()
    server_thread.join(timeout=5)

    return state.narration_path
