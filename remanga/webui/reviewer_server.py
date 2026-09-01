"""Local web server for the Narration Reviewer UI: a panel-by-panel pass over
an LLM-written narration.json where the user flags lines that are wrong
before they ever reach TTS. Launches a Flask app bound to localhost, opens
the user's browser to it, and blocks the calling thread until the user hits
Submit, at which point it writes narration_review.json (see paths.py) - the
file the user then hands back to the LLM for a fix pass, alongside
prompts/narration_review.md.

This module is just the entry point (launch_and_wait_reviewer) and process
lifecycle - see reviewer_state.py for the in-memory session state and
reviewer_routes.py for the Flask app/API. Mirrors webui/server.py's shape for
the panel marker; kept as a separate module (rather than folded into it)
since the two UIs serve different stages and can, in principle, be open at
once on different ports.
"""

from __future__ import annotations

import logging
import threading
import webbrowser
from pathlib import Path

from werkzeug.serving import make_server

from remanga.config import ReviewerConfig
from remanga.console import console
from remanga.paths import get_chapter_dir, get_narration_review_path
from remanga.webui.reviewer_routes import create_reviewer_app
from remanga.webui.reviewer_state import ReviewerState

logging.getLogger("werkzeug").setLevel(logging.WARNING)


def launch_and_wait_reviewer(project_name: str, chapter_num: str, config: ReviewerConfig) -> Path:
    """Starts the Narration Reviewer web UI, opens the browser, and blocks
    until the user submits. Returns the path to narration_review.json it
    wrote (empty/placeholder if the user approved with nothing flagged)."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = ReviewerState(chapter_dir, chapter_num)

    httpd = make_server(config.host, config.port, create_reviewer_app(state, config, project_name))
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        state.finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    console.print(f"[bold cyan]Narration Reviewer running at:[/] {url} [dim](round {state.round})[/]")
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    console.print("[yellow]Waiting for you to review the narration and submit...[/]")
    state.finished.wait()
    server_thread.join(timeout=5)

    return get_narration_review_path(project_name, chapter_num)
