"""The panel marker's Flask app: every /api/* route and the static-file/index
routes. Pure HTTP glue - the chapter list and cursor live in MarkerSession
(marker_session.py), one chapter's marks in MarkerState (marker_state.py),
detection runs via detection.py, shortcut persistence via shortcuts_store.py.
See server.py:launch_and_wait for how this gets started and torn down.

Every route reads `session.current`, never a captured state object: the
chapter under the cursor changes while the app is running (that is the whole
point of /api/goto and of /api/finish's advance), and a route holding the
state it was created with would keep serving the chapter the tab opened on.
"""

from __future__ import annotations

import threading

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import MarkerConfig, ShortcutsConfig
from remanga.paths import MARKER_STATIC_DIR as STATIC_DIR
from remanga.webui.detection import run_detection, start_once
from remanga.webui.marker_session import MarkerSession
from remanga.webui.shortcuts_store import persist_shortcuts


def create_app(session: MarkerSession, config: MarkerConfig) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

    def chapter_payload() -> dict:
        """Everything the browser needs to draw the chapter it's now on -
        the session's own shape plus this chapter's pages and marks. One
        builder, because /api/chapter (the first load), /api/goto and
        /api/finish's advance all hand the frontend the same thing; a tab
        arriving at a chapter must not be able to tell how it got there."""
        state = session.current
        return {
            **session.describe(),
            "pages": state.pages,
            "marks": state.marks,
            # Which pages already count as edited, so the browser can seed
            # its own touched-set instead of treating a chapter it comes
            # back to as untouched and letting a detection poll overwrite
            # its cache with what's on the server.
            "touched": sorted(state.touched),
            "magi_enabled": config.magi_enabled,
            "click_to_select": config.click_to_select,
        }

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/chapter")
    def get_chapter():
        return jsonify(chapter_payload())

    @app.post("/api/goto")
    def goto_chapter():
        """Jump to another chapter in this session, saving the one being
        left. This is what makes "check chapter 3 again" cost a click
        instead of a second run of the whole command."""
        index = (request.get_json(force=True) or {}).get("index")
        if not isinstance(index, int) or not session.goto(index):
            return jsonify({"ok": False, "error": f"No chapter at index {index} in this session"}), 400
        start_once(session.current, config)
        return jsonify({"ok": True, **chapter_payload()})

    @app.get("/api/pages/<path:filename>")
    def get_page_image(filename: str):
        return send_from_directory(session.current.pages_dir, filename)

    @app.post("/api/marks/<path:filename>")
    def post_marks(filename: str):
        marks = request.get_json(force=True) or []
        session.current.set_marks(filename, marks)
        return jsonify({"ok": True})

    @app.get("/api/shortcuts")
    def get_shortcuts():
        return jsonify({
            "shortcuts": config.shortcuts.model_dump(),
            "defaults": ShortcutsConfig().model_dump(),
        })

    @app.post("/api/shortcuts")
    def post_shortcuts():
        try:
            updated = ShortcutsConfig.model_validate(request.get_json(force=True) or {})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        config.shortcuts = updated
        persist_shortcuts(updated.model_dump())
        return jsonify({"ok": True, "shortcuts": updated.model_dump()})

    @app.post("/api/detect")
    def start_detect():
        if not config.magi_enabled:
            return jsonify({"ok": False, "error": "MAGI v3 assist is disabled in config.json"}), 400
        state = session.current
        if state.detect_running:
            return jsonify({"ok": False, "error": "Detection already running"}), 409
        state.detect_started = True
        threading.Thread(target=run_detection, args=(state, config), daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/detect/status")
    def detect_status():
        state = session.current
        return jsonify({
            "chapter": state.chapter_num,
            "running": state.detect_running,
            "done": state.detect_done,
            "total": state.detect_total,
            "error": state.detect_error,
            "marks": state.marks,
        })

    @app.post("/api/finish")
    def finish():
        """Save this chapter and move on: to the next chapter if the session
        has one, otherwise to the end of the session.

        `end` in the request body forces the second - the "I'm done, don't
        walk me through the remaining fifteen" answer, which has to exist
        because the terminal is blocked on this session and closing the tab
        is not a way to tell it anything."""
        end_now = bool((request.get_json(silent=True) or {}).get("end"))
        session.save_current()
        if end_now or not session.has_next:
            session.finished.set()
            return jsonify({"ok": True, "done": True})
        session.goto(session.index + 1, save=False)
        start_once(session.current, config)
        return jsonify({"ok": True, "done": False, **chapter_payload()})

    return app
