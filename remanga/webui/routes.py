"""The panel marker's Flask app: every /api/* route and the static-file/index
routes. Pure HTTP glue - state lives in MarkerState (marker_state.py),
detection runs via detection.py, shortcut persistence via shortcuts_store.py.
See server.py:launch_and_wait for how this gets started and torn down.
"""

from __future__ import annotations

import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import MarkerConfig, ShortcutsConfig
from remanga.console import console, escape as _esc
from remanga.json_io import write_json
from remanga.webui.detection import run_detection
from remanga.webui.marker_state import MarkerState
from remanga.webui.shortcuts_store import persist_shortcuts


STATIC_DIR = Path(__file__).parent / "static"


def create_app(state: MarkerState, config: MarkerConfig) -> Flask:
    app = Flask(__name__, static_folder=str(STATIC_DIR), static_url_path="/static")

    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/api/chapter")
    def get_chapter():
        return jsonify({
            "chapter": state.chapter_num,
            "pages": state.pages,
            "marks": state.marks,
            "magi_enabled": config.magi_enabled,
            "click_to_select": config.click_to_select,
        })

    @app.get("/api/pages/<path:filename>")
    def get_page_image(filename: str):
        return send_from_directory(state.pages_dir, filename)

    @app.post("/api/marks/<path:filename>")
    def post_marks(filename: str):
        marks = request.get_json(force=True) or []
        state.set_marks(filename, marks)
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
        if state.detect_running:
            return jsonify({"ok": False, "error": "Detection already running"}), 409
        threading.Thread(target=run_detection, args=(state, config), daemon=True).start()
        return jsonify({"ok": True})

    @app.get("/api/detect/status")
    def detect_status():
        return jsonify({
            "running": state.detect_running,
            "done": state.detect_done,
            "total": state.detect_total,
            "error": state.detect_error,
            "marks": state.marks,
        })

    @app.post("/api/finish")
    def finish():
        crops = state.build_crops_json()
        crops_path = state.chapter_dir / "crops.json"
        write_json(crops_path, crops)
        total_panels = sum(len(p["panels"]) for p in crops["pages"])
        console.print(f"[bold green]✓ Saved {total_panels} marked panel(s) across {len(crops['pages'])} page(s) to:[/] {_esc(str(crops_path))}")
        state.finished.set()
        return jsonify({"ok": True})

    return app
