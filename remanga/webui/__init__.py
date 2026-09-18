"""The Panel Marker web UI: the browser tab where a chapter's panels are
marked - MAGI v3 finds them, you fix them by hand - and crops.json is saved.

    server.py          the Panel Marker: starting it and waiting for the save
    writer_*.py        the Narration Writer: write a chapter's narration by hand
    reviewer_*.py      the Narration Reviewer: flag what an LLM got wrong
    routes*.py         the HTTP endpoints
    marker_session.py  the chapters open in the tab, and the cursor over them
    marker_state.py    one chapter's marks, and reading order
    magi_assist.py     the MAGI v3 worker in .tools/venv-magi
    static/            the page itself"""

from remanga.webui.reviewer_server import launch_and_wait_reviewer
from remanga.webui.server import launch_and_wait, launch_and_wait_all
from remanga.webui.writer_server import launch_and_wait_writer

__all__ = ["launch_and_wait", "launch_and_wait_all", "launch_and_wait_reviewer", "launch_and_wait_writer"]
