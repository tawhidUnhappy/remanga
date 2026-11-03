"""The panel marker's detection routes: running MAGI over a scope, replacing
marks with what it finds (remark), putting marks into reading order, and the
status the browser polls.

Mounted on the app by routes.py. The scopes - this page, this chapter, a
range of chapters, all of them - are resolved here, once, so Detect, Remark
and Reorder can't mean different things by the same word."""

from __future__ import annotations

from typing import Any

from flask import Flask, jsonify, request

from remanga.config import MarkerConfig
from remanga.webui.marker_session import MarkerSession


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


def register_detection_routes(app: Flask, session: MarkerSession, config: MarkerConfig) -> None:
    """Adds the detection, remark, reorder and status routes to `app`."""

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

    @app.post("/api/remark")
    def remark():
        """MAGI detects the pages again and REPLACES their marks - hand-drawn
        and edited ones included - for this page, this chapter, a range or
        every chapter. Queued on the same worker as Detect (one GPU).

        `dry_run` answers without doing anything - how many pages, how many
        with marks (and hand-made ones) would be replaced, how many emptied on
        purpose, which chapters are narrated - so the browser can say exactly
        what is about to be lost before it is."""
        if session.read_only:
            return jsonify({"ok": False, "error": "This session is read-only"}), 403
        if not config.magi_enabled:
            return jsonify({"ok": False, "error": "MAGI v3 assist is disabled in config.json"}), 400
        body = request.get_json(silent=True) or {}
        target = _scope_targets(session, body)
        if isinstance(target, str):
            return jsonify({"ok": False, "error": target}), 400
        chapters, pages = target
        plan = session.remark_plan(chapters, pages)
        if body.get("dry_run"):
            return jsonify({"ok": True, **plan})
        accepted = session.queue_remark(config, plan["chapters"], pages)
        return jsonify({"ok": True, **plan, "accepted": accepted, **session.detection_status()})

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
