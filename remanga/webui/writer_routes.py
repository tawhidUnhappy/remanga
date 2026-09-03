"""The Narration Writer's Flask app: every /api/* route and the static-file/
index routes. Pure HTTP glue - state lives in WriterState (writer_state.py).
See writer_server.py:launch_and_wait_writer for how this gets started and
torn down.
"""

from __future__ import annotations

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import WriterConfig
from remanga.console import console, escape as _esc
from remanga.json_io import write_json
from remanga.paths import WRITER_STATIC_DIR
from remanga.webui.writer_state import WriterState


def create_writer_app(state: WriterState, config: WriterConfig, project_name: str) -> Flask:
    app = Flask(__name__, static_folder=str(WRITER_STATIC_DIR), static_url_path="/static")

    @app.get("/")
    def index():
        return send_from_directory(WRITER_STATIC_DIR, "index.html")

    @app.get("/api/narration")
    def get_narration():
        return jsonify(state.to_payload())

    @app.get("/api/panels/<path:filename>")
    def get_panel_image(filename: str):
        return send_from_directory(state.panels_dir, filename)

    @app.post("/api/text/<path:panel_id>")
    def post_text(panel_id: str):
        body = request.get_json(force=True) or {}
        state.set_text(panel_id, body.get("text", ""))
        return jsonify({"ok": True})

    @app.post("/api/finish")
    def finish():
        narration = state.build_narration_json()
        write_json(state.narration_path, narration)

        written = sum(1 for e in narration["narration"] if e["text"].strip())
        console.print(
            f"[bold green]✓ narration.json saved[/] "
            f"({written}/{narration['total_panels']} panel(s) with text) to: {_esc(str(state.narration_path))}"
        )
        state.submitted = True
        state.finished.set()
        return jsonify({"ok": True, "total_panels": narration["total_panels"], "written": written})

    return app
