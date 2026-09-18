"""Local web server for the Narration Reviewer UI: a panel-by-panel pass over
an LLM-written narration.json where the user flags lines that are wrong
before they ever reach TTS. Launches a Flask app bound to localhost, opens
the user's browser to it, and blocks the calling thread until the user hits
Submit, at which point it writes narration_review.json (see paths.py) - the
file the user then hands back to the LLM for a fix pass, alongside
prompts/narration_review.md.

This module is just the entry point (launch_and_wait_reviewer) and process
lifecycle - see reviewer_state.py for the in-memory session state and
reviewer_routes.py for the Flask app/API, and launch.py for serving it.
Mirrors webui/server.py's shape for the panel marker; kept as a separate
module (rather than folded into it) since the two UIs serve different stages
and can, in principle, be open at once on different ports.
"""

from __future__ import annotations

from pathlib import Path

from remanga.config import ReviewerConfig
from remanga.paths import get_chapter_dir, get_narration_review_path
from remanga.webui.launch import start_ui
from remanga.webui.reviewer_routes import create_reviewer_app
from remanga.webui.reviewer_state import ReviewerState


def launch_and_wait_reviewer(project_name: str, chapter_num: str, config: ReviewerConfig) -> Path:
    """Starts the Narration Reviewer web UI, opens the browser, and blocks
    until the user submits. Returns the path to narration_review.json it
    wrote (empty/placeholder if the user approved with nothing flagged)."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = ReviewerState(chapter_dir, chapter_num)

    ui = start_ui(create_reviewer_app(state, config, project_name), config, state.finished,
                  title="Narration Reviewer", title_note=f" [dim](round {state.round})[/]")
    ui.wait("review the narration and submit")

    return get_narration_review_path(project_name, chapter_num)
