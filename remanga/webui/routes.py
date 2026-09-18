"""The panel marker's Flask app: the chapter on screen, its pages and their
marks, and the static/index routes. Pure HTTP glue - the chapter list and
cursor live in MarkerSession (marker_session.py), one chapter's marks in
MarkerState (marker_state.py), detection is queued on the session (one
worker, see marker_session.py) and run by detection.py.

Two groups of routes are mounted from their own modules: detection, remark
and reorder from routes_detect.py, and the action bar's switches and the
Shortcuts menu from routes_settings.py.
See server.py:launch_and_wait for how this gets started and torn down.

Every route reads `session.current`, never a captured state object: the
chapter under the cursor changes while the app is running (that is the whole
point of /api/goto and of /api/finish's advance), and a route holding the
state it was created with would keep serving the chapter the tab opened on.
"""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import MarkerConfig
from remanga.paths import MARKER_STATIC_DIR as STATIC_DIR, SHARED_STATIC_DIR
from remanga.webui.marker_session import MarkerSession
from remanga.webui.routes_detect import register_detection_routes
from remanga.webui.routes_settings import register_settings_routes


def create_app(session: MarkerSession, config: MarkerConfig) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

    def chapter_payload() -> dict:
        """Everything the browser needs to draw the chapter it's now on -
        the session's own shape plus this chapter's pages and marks. One
        builder, because /api/chapter (the first load) and /api/goto both
        hand the frontend the same thing; a tab arriving at a chapter must not
        be able to tell how it got there."""
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
            # ...and, separately, the ones a person deliberately emptied.
            # The sidebar draws those differently from a page that is merely
            # still blank, so it needs the narrower set too.
            "decided": sorted(state.decided),
            "magi_enabled": config.magi_enabled,
            "click_to_select": config.click_to_select,
            "detect_scope": config.auto_detect_scope,
            "auto_order": session.auto_order,
            "revision": state.revision,
        }

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/shared/<path:filename>")
    def shared_asset(filename: str):
        """The palette, the logo and the bits every remanga web UI shares -
        served from one folder rather than copied into each (see
        remanga/webui/static_shared/)."""
        return send_from_directory(SHARED_STATIC_DIR, filename)

    @app.get("/favicon.ico")
    def favicon():
        # Browsers ask for this at the root whatever the page links to.
        return send_from_directory(SHARED_STATIC_DIR / "img", "favicon.ico")

    @app.get("/api/chapter")
    def get_chapter():
        return jsonify(chapter_payload())

    @app.post("/api/goto")
    def goto_chapter():
        """Jump to another chapter in this session, saving the one being
        left. This is what makes "check chapter 3 again" cost a click
        instead of a second run of the whole command."""
        index = (request.get_json(force=True) or {}).get("index")
        if not isinstance(index, int) or not session.goto(index, save=not session.read_only):
            return jsonify({"ok": False, "error": f"No chapter at index {index} in this session"}), 400
        return jsonify({"ok": True, **chapter_payload()})

    @app.get("/api/pages/<path:filename>")
    def get_page_image(filename: str):
        return send_from_directory(session.current.pages_dir, filename)

    @app.post("/api/marks/<path:filename>")
    def post_marks(filename: str):
        # The browser doesn't offer any way to edit in a read-only session,
        # but "the UI doesn't show the button" is not the same guarantee as
        # "the server won't do it" - and a session opened to double-check
        # marks is exactly where the stronger one is the point.
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        state = session.current
        # The browser says which revision of this chapter its marks are from.
        # A reorder the server ran since then means the browser's
        # copy is out of date, and writing it would put the old order
        # straight back over the new one - so it's refused, and the
        # browser reloads the chapter instead.
        rev = request.args.get("rev")
        if rev is not None and rev.isdigit() and int(rev) != state.revision:
            return jsonify({"ok": False, "stale": True, "revision": state.revision}), 409
        marks = request.get_json(force=True) or []
        stored = state.set_marks(
            filename, marks,
            order_direction=session.reading_direction if session.auto_order else None,
        )
        session.mark_dirty(session.chapter_num)
        return jsonify({"ok": True, "marks": stored, "revision": state.revision})

    @app.get("/api/outline")
    def get_outline():
        """The whole session as a tree: chapters, their pages, and how many
        panels each page has. What the sidebar navigates."""
        return jsonify({"chapters": session.outline()})

    @app.post("/api/finish")
    def finish():
        """Save and exit: the chapter on screen and every chapter holding marks
        that aren't on disk yet are written, and the session ends - the
        terminal, blocked on it, moves on.

        Saving here is explicit - the user pressed Save - so it happens whether
        or not auto-save is on. Moving between chapters is navigation, not
        this: the page arrows and the chapter arrows (see /api/goto). In a
        read-only session nothing is written; it only closes."""
        written: list[str] = []
        if not session.read_only:
            for chapter in session.unsaved_chapters():
                session.save_chapter(chapter)
                written.append(chapter)
            if session.chapter_num not in written:
                session.save_current()
                written.append(session.chapter_num)
        session.finished.set()
        return jsonify({
            "ok": True,
            "done": True,
            "written": written,
            # Everything this session put on disk, auto-saves included - what
            # the closing screen reports.
            "saved_chapters": list(session.saved_chapters),
        })

    register_detection_routes(app, session, config)
    register_settings_routes(app, session, config)
    return app
