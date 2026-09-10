"""The panel marker's Flask app: every /api/* route and the static-file/index
routes. Pure HTTP glue - the chapter list and cursor live in MarkerSession
(marker_session.py), one chapter's marks in MarkerState (marker_state.py),
detection is queued on the session (one worker, see marker_session.py) and
run by detection.py, settings persistence via settings_store.py.
See server.py:launch_and_wait for how this gets started and torn down.

Every route reads `session.current`, never a captured state object: the
chapter under the cursor changes while the app is running (that is the whole
point of /api/goto and of /api/finish's advance), and a route holding the
state it was created with would keep serving the chapter the tab opened on.
"""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import MarkerConfig, ShortcutsConfig
from remanga.paths import MARKER_STATIC_DIR as STATIC_DIR
from remanga.webui.marker_session import MarkerSession
from remanga.webui.settings_store import persist_marker_settings, persist_shortcuts


def _chapter_span(session: MarkerSession, first: Any, last: Any) -> list[str] | None:
    """The chapters from `first` to `last` inclusive, by chapter NUMBER as a
    person would say them ("4" to "9"), not by index.

    Reversed is accepted and normalized: someone who picks 9 and then 4 has
    said which chapters they mean just as clearly as someone who picked them
    the other way round."""
    chapters = session.chapters
    try:
        start, end = chapters.index(str(first)), chapters.index(str(last))
    except ValueError:
        return None
    if start > end:
        start, end = end, start
    return chapters[start:end + 1]


def _scope_targets(session: MarkerSession, body: dict[str, Any]) -> tuple[list[str], list[str] | None] | str:
    """The chapters (and, for "page", the one page) a scoped request covers -
    or an error message. The same four scopes the Detect button takes, so
    Reorder means exactly what Detect means by "this chapter" or
    "4 to 9"."""
    scope = str(body.get("scope") or "chapter")
    if scope == "page":
        filename = body.get("filename") or ""
        if not any(page["filename"] == filename for page in session.current.pages):
            return f"No page {filename!r} in this chapter"
        return [session.chapter_num], [filename]
    if scope == "all":
        return session.chapters[session.index:] + session.chapters[:session.index], None
    if scope == "range":
        span = _chapter_span(session, body.get("from"), body.get("to"))
        if span is None:
            return "That chapter range isn't in this session"
        return span, None
    return [session.chapter_num], None


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
        session.start_detection(config)
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

    @app.post("/api/reorder")
    def reorder_marks():
        """Put marks into reading order over a page, a chapter, a range or
        everything - immediately, not queued behind detection (see
        MarkerSession.reorder). Same scopes as /api/detect."""
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        target = _scope_targets(session, request.get_json(silent=True) or {})
        if isinstance(target, str):
            return jsonify({"ok": False, "error": target}), 400
        chapters, pages = target
        changed = session.reorder(chapters, pages)
        return jsonify({"ok": True, "changed": changed, "revision": session.current.revision})

    @app.get("/api/outline")
    def get_outline():
        """The whole session as a tree: chapters, their pages, and how many
        panels each page has. What the sidebar navigates."""
        return jsonify({"chapters": session.outline()})

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
        """Queue a MAGI pass. `scope` says how much:

            page     just the page named in `filename` (the one on screen),
                     even if it was previously recorded as having no panels
            chapter  the chapter on screen
            range    every chapter from `from` to `to`, inclusive
            all      every chapter in the session

        Range is the one that earns its keep: "I got as far as chapter 9
        before the power went out" is a from/to, and expressing it any other
        way means either nine clicks or redetecting the whole manga.
        """
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        if not config.magi_enabled:
            return jsonify({"ok": False, "error": "MAGI v3 assist is disabled in config.json"}), 400

        body = request.get_json(silent=True) or {}
        scope = str(body.get("scope") or "chapter")

        if scope == "page":
            filename = body.get("filename") or ""
            if not any(page["filename"] == filename for page in session.current.pages):
                return jsonify({"ok": False, "error": f"No page {filename!r} in this chapter"}), 400
            # force: naming one page is asking for that page. A previous
            # "no panels here" gives way; a page with marks on it does not
            # (see MarkerState.apply_detected).
            queued = session.queue_detection(config, [session.chapter_num], pages=[filename], force=True)
        elif scope == "all":
            queued = session.queue_all(config)
        elif scope == "range":
            span = _chapter_span(session, body.get("from"), body.get("to"))
            if span is None:
                return jsonify({"ok": False, "error": "That chapter range isn't in this session"}), 400
            queued = session.queue_detection(config, span)
        else:
            queued = session.queue_detection(config, [session.chapter_num])

        # "accepted" is what THIS request added; detection_status()'s "queued"
        # is what is still waiting, which by the time this is serialized may
        # already be less - the worker starts immediately. Two different
        # questions, so two different names.
        return jsonify({"ok": True, "accepted": queued, **session.detection_status()})

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
            "revision": state.revision,
            **session.detection_status(),
        })

    @app.post("/api/settings")
    def post_settings():
        """The assist card's switches. Applied to this session AND written
        into config.json, because they describe how someone works rather
        than anything about today's manga - see
        settings_store.persist_marker_settings."""
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        body = request.get_json(silent=True) or {}
        saved: dict[str, Any] = {}

        if "auto_all" in body:
            session.set_auto_all(bool(body["auto_all"]), config)
            config.auto_detect_all = session.auto_all
            saved["auto_detect_all"] = session.auto_all
        if "auto_save" in body:
            session.set_auto_save(bool(body["auto_save"]))
            config.auto_save = session.auto_save
            saved["auto_save"] = session.auto_save
        if "auto_order" in body:
            session.set_auto_order(bool(body["auto_order"]))
            config.auto_order = session.auto_order
            saved["auto_order"] = session.auto_order
        if "scope" in body:
            scope = str(body["scope"])
            if scope not in ("page", "chapter", "range", "all"):
                return jsonify({"ok": False, "error": f"Unknown scope {scope!r}"}), 400
            config.auto_detect_scope = scope
            saved["auto_detect_scope"] = scope

        if saved:
            persist_marker_settings(saved)
        return jsonify({"ok": True, **session.detection_status()})

    @app.post("/api/finish")
    def finish():
        """Save this chapter and move on: to the next chapter if the session
        has one, otherwise to the end of the session.

        Saving here is explicit - the user pressed the button - so it happens
        whether or not auto-save is on.

        `end` forces the second - the "I'm done, don't walk me through the
        remaining fifteen" answer, which has to exist because the terminal is
        blocked on this session and closing the tab is not a way to tell it
        anything. `save_all` writes every chapter still holding unsaved
        marks, which is what the browser offers when auto-save has been off
        and the session is about to close."""
        body = request.get_json(silent=True) or {}
        end_now = bool(body.get("end"))
        if body.get("save_all"):
            for chapter in session.unsaved_chapters():
                session.save_chapter(chapter)
        session.save_current()
        if end_now or not session.has_next:
            session.finished.set()
            return jsonify({"ok": True, "done": True, "unsaved": session.unsaved_chapters()})
        # save=False: save_current() above already wrote this chapter, and
        # goto's own save would write it a second time and report it twice.
        session.goto(session.index + 1, save=False)
        session.start_detection(config)
        return jsonify({"ok": True, "done": False, **chapter_payload()})

    return app
