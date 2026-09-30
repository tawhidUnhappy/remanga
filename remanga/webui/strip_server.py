"""The Strip Marker: a long-strip (webtoon) chapter marked the way it is read -
every downloaded image stacked into one strip, scrolled top to bottom, each
panel a band across it. Ported from mangaEasy's webtoon panel editor (its
mangaeasy/web/panel_editor.py + assets/static/js/editor.js, removed there with
its GUI), because MAGI, trained on printed pages, cannot mark a webtoon.

The browser proposes nothing itself: the first marks are mangaEasy's gutter
split (remanga/longstrip/split.py), and the marks are saved as strip rows in
chapter_N/strip_marks.json on every change. Finish (or the next step that
needs them) turns them into strip/ pages and crops.json - see
remanga/longstrip/build.py:ensure_strip."""

from __future__ import annotations

import threading

from flask import Flask, jsonify, request, send_from_directory

from remanga.config import MarkerConfig
from remanga.console import console, escape as _esc
from remanga.longstrip import (
    auto_panels,
    ensure_strip,
    image_layout,
    read_strip_marks,
    write_strip_marks,
)
from remanga.paths import SHARED_STATIC_DIR, STRIP_STATIC_DIR, get_pages_dir, load_project_metadata
from remanga.webui.launch import start_ui


def create_strip_app(project: str, chapter: str, finished: threading.Event) -> Flask:
    app = Flask(__name__, static_folder=str(STRIP_STATIC_DIR), static_url_path="/static")
    pages_dir = get_pages_dir(project, chapter).resolve()

    @app.get("/")
    def index():
        return send_from_directory(STRIP_STATIC_DIR, "index.html")

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(SHARED_STATIC_DIR / "img", "favicon.ico")

    @app.get("/shared/<path:filename>")
    def shared_asset(filename: str):
        return send_from_directory(SHARED_STATIC_DIR, filename)

    @app.get("/api/images/<path:name>")
    def image(name: str):
        return send_from_directory(pages_dir, name)

    @app.get("/api/strip")
    def strip():
        """The images to stack, and the marks: the saved ones, else mangaEasy's."""
        marks = read_strip_marks(project, chapter)
        proposed = marks is None
        if proposed:
            marks = auto_panels(project, chapter)
            write_strip_marks(project, chapter, marks)
        return jsonify({
            "project": project,
            "title": load_project_metadata(project).get("manga_title", project),
            "chapter": chapter,
            "images": image_layout(project, chapter),
            "panels": [list(p) for p in marks],
            "proposed": proposed,
        })

    @app.post("/api/auto")
    def auto():
        """Auto marks (R): mangaEasy's split again, replacing the marks."""
        marks = write_strip_marks(project, chapter, auto_panels(project, chapter))
        return jsonify({"panels": [list(p) for p in marks]})

    @app.post("/api/marks")
    def save_marks():
        """Every change, so a closed tab loses nothing - only the marks file;
        the strip is rebuilt from it at Finish or when next needed."""
        body = request.get_json(force=True) or {}
        marks = write_strip_marks(project, chapter, body.get("panels") or [])
        return jsonify({"ok": True, "panels": len(marks)})

    @app.post("/api/finish")
    def finish():
        body = request.get_json(force=True) or {}
        marks = write_strip_marks(project, chapter, body.get("panels") or [])
        ensure_strip(project, chapter)
        console.print(f"[bold green]✓ Chapter {_esc(chapter)}: {len(marks)} panel(s) marked on the strip[/]")
        finished.set()
        return jsonify({"ok": True, "panels": len(marks)})

    return app


def launch_and_wait_strip(project: str, chapter: str, config: MarkerConfig) -> int:
    """Opens the Strip Marker for one chapter and blocks until Finish.
    Returns how many panels are marked."""
    finished = threading.Event()
    ui = start_ui(create_strip_app(project, chapter, finished), config, finished,
                  title=f"Strip Marker - chapter {chapter}")
    ui.wait(f"mark chapter {chapter}'s panels in the browser and press Finish")
    # Whatever happened in the tab, the strip matches the marks on disk now.
    ensure_strip(project, chapter)
    return len(read_strip_marks(project, chapter) or [])
