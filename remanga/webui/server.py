"""Local web server for the panel-marking UI: replaces the old "paste crops.json
from an LLM" wizard step. Launches a Flask app bound to localhost, opens the
user's browser to it, and blocks the calling thread until the user hits Save
(Ctrl/Cmd+S or the Save button), at which point it writes crops.json in the exact
schema the rest of the pipeline (remanga/cropper/crop.py onward) already expects -
so gutter-snap, seam reconciliation, dedup, and whitespace trim all still run on
top of these marks, same as they did on LLM-produced ones.
"""

from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request, send_from_directory
from PIL import Image
from rich.console import Console
from werkzeug.serving import make_server

from remanga.config import MarkerConfig, ShortcutsConfig
from remanga.cropper.geometry import pixel_bounds_to_box_1000
from remanga.json_io import read_json_or, write_json
from remanga.paths import get_chapter_dir

console = Console()

STATIC_DIR = Path(__file__).parent / "static"

# Same cwd-relative file remanga.config.RemangaConfig.load()/.save() already
# use by default - the panel marker only ever holds config.marker (a
# MarkerConfig), not the full RemangaConfig or the path it was loaded from,
# so shortcut edits are persisted by patching this one file directly rather
# than plumbing the full config object/path through every call site.
CONFIG_JSON_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")


def _persist_shortcuts(shortcuts: Dict[str, Any]) -> None:
    """Writes marker.shortcuts into config.json, read-merge-write style (same
    pattern as remanga.paths.save_project_metadata) so every other section is
    left untouched. If config.json doesn't exist yet - the app was running on
    config.example.json's defaults - seed it from that file first instead of
    from nothing, so materializing config.json here doesn't silently drop
    whatever settings were actually in effect."""
    seed_path = CONFIG_JSON_PATH if CONFIG_JSON_PATH.exists() else CONFIG_EXAMPLE_PATH
    data = read_json_or(seed_path, {})
    data.setdefault("marker", {})
    data["marker"]["shortcuts"] = shortcuts
    write_json(CONFIG_JSON_PATH, data)


class MarkerState:
    """All in-memory state for one marking session. One chapter at a time."""

    def __init__(self, chapter_dir: Path, chapter_num: str):
        # Absolute: Flask's send_from_directory() resolves a relative directory
        # against the app's root_path (remanga/webui/), not the process cwd.
        self.chapter_dir = chapter_dir.resolve()
        self.chapter_num = chapter_num
        self.pages_dir = self.chapter_dir / "pages"
        self.pages: List[Dict[str, Any]] = []
        self.marks: Dict[str, List[Dict[str, Any]]] = {}
        self.touched: set = set()  # filenames the user has edited - MAGI won't overwrite these
        self.detect_running = False
        self.detect_done = 0
        self.detect_total = 0
        self.detect_error: Optional[str] = None
        self.finished = threading.Event()
        self._load_pages()

    def _load_pages(self) -> None:
        for i, path in enumerate(sorted(self.pages_dir.glob("page_*.*")), start=1):
            with Image.open(path) as img:
                w, h = img.size
            self.pages.append({"index": i, "filename": path.name, "width": w, "height": h})
            self.marks.setdefault(path.name, [])

    def set_marks(self, filename: str, marks: List[Dict[str, Any]]) -> None:
        self.marks[filename] = marks
        self.touched.add(filename)

    def apply_detected(self, filename: str, boxes: List[List[float]]) -> None:
        """Fills in MAGI's detected boxes for a page, unless the user already
        touched that page (never clobber a manual edit with a late-arriving
        background detection)."""
        if filename in self.touched:
            return
        self.marks[filename] = [
            {"id": f"ai-{filename}-{i}", "x": b[0], "y": b[1], "w": b[2] - b[0], "h": b[3] - b[1], "src": "ai"}
            for i, b in enumerate(boxes)
        ]

    def build_crops_json(self) -> Dict[str, Any]:
        pages_out = []
        for page in self.pages:
            filename = page["filename"]
            page_marks = self.marks.get(filename, [])
            if not page_marks:
                pages_out.append({
                    "page_index": page["index"],
                    "page_filename": filename,
                    "is_story_page": False,
                    "panels": [],
                })
                continue

            panels_out = []
            for i, m in enumerate(page_marks, start=1):
                bounds = (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
                box_1000 = pixel_bounds_to_box_1000(bounds, page["width"], page["height"])
                panels_out.append({"panel_id": i, "box_1000": box_1000})

            pages_out.append({
                "page_index": page["index"],
                "page_filename": filename,
                "is_story_page": True,
                "panels": panels_out,
            })

        return {"chapter": str(self.chapter_num), "pages": pages_out}


def _run_detection(state: MarkerState, config: MarkerConfig) -> None:
    from remanga.webui.magi_assist import detect_panels_for_pages

    state.detect_running = True
    state.detect_done = 0
    state.detect_total = len(state.pages)
    state.detect_error = None

    def on_page_done(filename: str, boxes: List[List[float]]) -> None:
        state.apply_detected(filename, boxes)
        state.detect_done += 1

    try:
        page_paths = [state.pages_dir / p["filename"] for p in state.pages]
        detect_panels_for_pages(page_paths, config, on_page_done=on_page_done)
    except Exception as e:
        state.detect_error = str(e)
        console.print(f"[bold red]MAGI v3 detection failed:[/] {e}")
    finally:
        state.detect_running = False


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
        _persist_shortcuts(updated.model_dump())
        return jsonify({"ok": True, "shortcuts": updated.model_dump()})

    @app.post("/api/detect")
    def start_detect():
        if not config.magi_enabled:
            return jsonify({"ok": False, "error": "MAGI v3 assist is disabled in config.json"}), 400
        if state.detect_running:
            return jsonify({"ok": False, "error": "Detection already running"}), 409
        threading.Thread(target=_run_detection, args=(state, config), daemon=True).start()
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
        console.print(f"[bold green]✓ Saved {total_panels} marked panel(s) across {len(crops['pages'])} page(s) to:[/] {crops_path}")
        state.finished.set()
        return jsonify({"ok": True})

    return app


def launch_and_wait(project_name: str, chapter_num: str, config: MarkerConfig) -> Path:
    """Starts the marking web UI, opens the browser, and blocks until the user
    saves. Returns the path to the crops.json it wrote."""
    chapter_dir = get_chapter_dir(project_name, chapter_num)
    state = MarkerState(chapter_dir, chapter_num)

    if not state.pages:
        raise FileNotFoundError(f"No downloaded pages found in {state.pages_dir} - download the chapter first.")

    httpd = make_server(config.host, config.port, create_app(state, config))
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)

    def shutdown_soon():
        state.finished.wait()
        httpd.shutdown()

    threading.Thread(target=shutdown_soon, daemon=True).start()

    url = f"http://{config.host}:{config.port}/"
    server_thread.start()

    console.print(f"[bold cyan]Panel Marker running at:[/] {url}")
    if config.auto_open_browser:
        webbrowser.open(url)
    else:
        console.print("[dim]Open that URL in your browser to continue.[/]")

    if config.magi_enabled:
        threading.Thread(target=_run_detection, args=(state, config), daemon=True).start()

    console.print("[yellow]Waiting for you to mark panels and save (Ctrl/Cmd+S in the browser)...[/]")
    state.finished.wait()
    server_thread.join(timeout=5)

    return chapter_dir / "crops.json"
