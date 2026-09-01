"""The Narration Reviewer's Flask app: every /api/* route and the static-file/
index routes. Pure HTTP glue - state lives in ReviewerState (reviewer_state.py).
See reviewer_server.py:launch_and_wait_reviewer for how this gets started and
torn down.
"""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import ReviewerConfig
from remanga.console import console, escape as _esc
from remanga.json_io import write_json
from remanga.paths import (
    REVIEWER_STATIC_DIR, get_narration_review_history_dir, get_narration_review_path,
)
from remanga.webui.reviewer_state import ReviewerState


def create_reviewer_app(state: ReviewerState, config: ReviewerConfig, project_name: str) -> Flask:
    app = Flask(__name__, static_folder=str(REVIEWER_STATIC_DIR), static_url_path="/static")

    @app.get("/")
    def index():
        return send_from_directory(REVIEWER_STATIC_DIR, "index.html")

    @app.get("/api/narration")
    def get_narration():
        return jsonify(state.to_payload())

    @app.get("/api/panels/<path:filename>")
    def get_panel_image(filename: str):
        return send_from_directory(state.panels_dir, filename)

    @app.post("/api/flag/<path:panel_id>")
    def post_flag(panel_id: str):
        body = request.get_json(force=True) or {}
        state.set_flag(panel_id, body.get("issue", ""), body.get("tag", ""))
        return jsonify({"ok": True})

    @app.post("/api/finish")
    def finish():
        body = request.get_json(force=True) or {}
        approved = bool(body.get("approved"))
        general_note = body.get("general_note", "")

        review = state.build_review_json(general_note, approved)

        review_path = get_narration_review_path(project_name, state.chapter_num)
        if approved and review["flagged_count"] == 0:
            # Nothing to send an LLM - clear any stale review file rather
            # than writing an empty one, so has_real_json_content() reads
            # this chapter as "review clean" the same way an untouched
            # chapter reads as "not started".
            review_path.write_text("", encoding="utf-8")
        else:
            write_json(review_path, review)
            history_path = get_narration_review_history_dir(project_name, state.chapter_num) / f"round_{state.round}.json"
            write_json(history_path, review)

        console.print(
            f"[bold green]✓ Review round {state.round} saved[/] "
            f"({review['flagged_count']} panel(s) flagged) to: {_esc(str(review_path))}"
        )
        state.submitted = True
        state.finished.set()
        return jsonify({"ok": True, "approved": approved, "flagged_count": review["flagged_count"]})

    return app
