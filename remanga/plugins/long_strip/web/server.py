"""The Strip Marker's web server: a long-strip (webtoon) chapter marked the
way it is read - the whole chapter as one strip, scrolled top to bottom, each
panel a band across it. Ported from mangaEasy's webtoon panel editor (removed
there with its GUI - see git history of /mnt/datadisk/mangaEasy) and grown:
tiles instead of whole images, overlapping marks, sides, snapping, undo.

Routes only; the state is session.py, the page static/. Marks are
saved to chapter_N/strip_marks.json on every change; Finish (or the next step
that needs them - remanga/plugins/long_strip/build.py:ensure_strip) turns them into
strip/ pages and crops.json."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from remanga.config import MarkerConfig
from remanga.console import console, escape as _esc
from remanga.plugins.long_strip.build import ensure_strip, strip_panels
from remanga.plugins.long_strip.web.session import StripSession
from remanga.webui.launch import start_ui
from remanga.webui.shared_routes import add_shared_routes

STRIP_STATIC_DIR = Path(__file__).parent / "static"


def create_strip_app(session: StripSession) -> Flask:
    app = Flask(__name__, static_folder=str(STRIP_STATIC_DIR), static_url_path="/static")

    @app.get("/")
    def index():
        return send_from_directory(STRIP_STATIC_DIR, "index.html")

    add_shared_routes(app)


    @app.get("/api/layout")
    def layout():
        return jsonify(session.layout())

    @app.get("/api/strip")
    def strip():
        return jsonify(session.payload())

    @app.get("/api/tile/<int:run>/<int:number>.jpg")
    def tile(run: int, number: int):
        try:
            data = session.view.tile(run, number)
        except IndexError:
            abort(404)
        return Response(data, mimetype="image/jpeg", headers={"Cache-Control": "max-age=3600"})

    @app.post("/api/auto")
    def auto():
        """Auto marks (R): the proposed marks again, replacing the saved ones."""
        return jsonify({"panels": [list(m) for m in session.save(session.proposed())]})

    @app.post("/api/marks")
    def save_marks():
        """Every change, so a closed tab loses nothing - only the marks file."""
        marks = session.save((request.get_json(force=True) or {}).get("panels"))
        return jsonify({"ok": True, "panels": len(marks)})

    @app.post("/api/finish")
    def finish():
        marks = session.save((request.get_json(force=True) or {}).get("panels"))
        pages = len(strip_panels(ensure_strip(session.project, session.chapter)))
        console.print(f"[bold green]✓ Chapter {_esc(session.chapter)}: {len(marks)} panel(s) marked on the strip[/]")
        session.finished.set()
        return jsonify({"ok": True, "panels": len(marks), "pages": pages, "chapter": session.chapter})

    return app


def launch_and_wait_strip(project: str, chapter: str, config: MarkerConfig) -> int:
    """Opens the Strip Marker for one chapter and blocks until Finish.
    Returns how many panels are marked."""
    session = StripSession(project, chapter)
    ui = start_ui(create_strip_app(session), config, session.finished, title=f"Strip Marker - chapter {chapter}")
    ui.wait(f"mark chapter {chapter}'s panels in the browser and press Finish")
    # Whatever happened in the tab, the strip matches the marks on disk now.
    ensure_strip(project, chapter)
    return len(session.marks()[0])
