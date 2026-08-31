"""Runs MAGI v3 panel detection for a chapter on a background thread and
streams progress into a MarkerState, so the browser (polling
GET /api/detect/status - see routes.py) sees pages fill in one at a time
instead of blocking on the whole chapter.
"""

from __future__ import annotations

from typing import List

from remanga.config import MarkerConfig
from remanga.console import console, escape as _esc
from remanga.webui.marker_state import MarkerState


def run_detection(state: MarkerState, config: MarkerConfig) -> None:
    from remanga.webui.magi_assist import detect_panels_for_pages

    # Pages already touched - crops.json was pre-loaded server-side (a
    # "remark" restart, or just reopening the marker on an already-marked
    # chapter; see marker_state.py:_load_existing_crops) - never get MAGI's
    # result applied anyway (apply_detected() refuses to overwrite a touched
    # page). Sending them to the worker regardless still pays for a full
    # model load onto the GPU and real per-page inference time for zero
    # actual effect: "redetecting" a chapter that already has all its marks.
    # Skip them here so the whole detection pass - worker spawn included -
    # is skipped entirely once nothing is actually pending.
    pending_pages = [p for p in state.pages if p["filename"] not in state.touched]

    state.detect_running = True
    state.detect_done = 0
    state.detect_total = len(pending_pages)
    state.detect_error = None

    if not pending_pages:
        state.detect_running = False
        return

    def on_page_done(filename: str, boxes: List[List[float]]) -> None:
        state.apply_detected(filename, boxes)
        state.detect_done += 1

    try:
        page_paths = [state.pages_dir / p["filename"] for p in pending_pages]
        detect_panels_for_pages(page_paths, config, on_page_done=on_page_done)
    except Exception as e:
        state.detect_error = str(e)
        console.print(f"[bold red]MAGI v3 detection failed:[/] {_esc(str(e))}")
    finally:
        state.detect_running = False
