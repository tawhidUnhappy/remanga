"""Local web server for the Narration Writer UI: a panel-by-panel pass where
the user types the narration text themselves instead of an LLM writing it.
Launches a Flask app bound to localhost, opens the user's browser to it, and
blocks the calling thread until the user hits Save, at which point it writes
narration.json (see paths.py).

This module is just the entry point (launch_and_wait_writer) and process
lifecycle - see writer_state.py for the in-memory session state and
writer_routes.py for the Flask app/API, and launch.py for serving it.
Mirrors reviewer_server.py's shape; kept as a separate module since all three
UIs serve different stages and can, in principle, be open at once on
different ports.
"""

from __future__ import annotations

from pathlib import Path

from remanga.config import WriterConfig
from remanga.paths import get_chapter_dir
from remanga.webui.launch import start_ui
from remanga.webui.writer_routes import create_writer_app
from remanga.webui.writer_state import WriterState


def launch_and_wait_writer(project_name: str, chapter_num: str, config: WriterConfig) -> Path:
    """Starts the Narration Writer web UI, opens the browser, and blocks
    until the user saves. Returns the path to narration.json it wrote."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = WriterState(chapter_dir, chapter_num)

    ui = start_ui(create_writer_app(state, config, project_name), config, state.finished,
                  title="Narration Writer")
    ui.wait("write the narration and save")
    # Frees the GPU/worker process promptly instead of leaving it idle until
    # the whole `remanga` process exits - this session might be one command
    # in a longer wizard loop (see remanga/wizard/'s nested menu), not the last
    # thing that runs.

    return state.narration_path
