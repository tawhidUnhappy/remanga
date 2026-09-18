"""The Panel Marker web UI: the browser tab where a chapter's panels are
marked - MAGI v3 finds them, you fix them by hand - and crops.json is saved.

    server.py          starting the Flask app and waiting for the save
    routes*.py         the HTTP endpoints
    marker_session.py  the chapters open in the tab, and the cursor over them
    marker_state.py    one chapter's marks, and reading order
    magi_assist.py     the MAGI v3 worker in .tools/venv-magi
    static/            the page itself"""

from remanga.webui.server import launch_and_wait, launch_and_wait_all

__all__ = ["launch_and_wait", "launch_and_wait_all"]
