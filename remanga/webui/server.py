"""Local web server for the panel-marking UI: replaces the old "paste crops.json
from an LLM" wizard step. Launches a Flask app bound to localhost, opens the
user's browser to it, and blocks the calling thread until the user hits Save
(Ctrl/Cmd+S or the Save button), at which point it writes crops.json in the exact
schema the rest of the pipeline (remanga/cropper/crop.py onward) already expects -
so gutter-snap, seam reconciliation, dedup, and whitespace trim all still run on
top of these marks, same as they did on LLM-produced ones.

This module is just the entry point (launch_and_wait) and process lifecycle -
see marker_state.py for the in-memory session state, detection.py for the
background MAGI thread, routes.py for the Flask app/API, and
shortcuts_store.py for how the Shortcuts menu's edits get saved.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path

from rich.console import Console
from werkzeug.serving import make_server

from remanga.config import MarkerConfig
from remanga.paths import get_chapter_dir
from remanga.webui.detection import run_detection
from remanga.webui.marker_state import MarkerState
from remanga.webui.routes import create_app

console = Console()


def launch_and_wait(project_name: str, chapter_num: str, config: MarkerConfig) -> Path:
    """Starts the marking web UI, opens the browser, and blocks until the user
    saves. Returns the path to the crops.json it wrote."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = MarkerState(chapter_dir, chapter_num)

    if not state.pages:
        raise FileNotFoundError(f"No downloaded pages found in {state.pages_dir} - download the chapter first.")

    httpd = make_server(config.host, config.port, create_app(state, config))
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        state.finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    console.print(f"[bold cyan]Panel Marker running at:[/] {url}")
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    if config.magi_enabled:
        threading.Thread(target=run_detection, args=(state, config), daemon=True).start()

    console.print("[yellow]Waiting for you to mark panels and save (Ctrl/Cmd+S in the browser)...[/]")
    state.finished.wait()
    server_thread.join(timeout=5)

    return chapter_dir / "crops.json"
