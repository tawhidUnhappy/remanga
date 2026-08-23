"""Runs MAGI v3 panel detection for a chapter on a background thread and
streams progress into a MarkerState, so the browser (polling
GET /api/detect/status - see routes.py) sees pages fill in one at a time
instead of blocking on the whole chapter.
"""

from __future__ import annotations

from typing import List

from rich.console import Console

from remanga.config import MarkerConfig
from remanga.webui.marker_state import MarkerState

console = Console()


def run_detection(state: MarkerState, config: MarkerConfig) -> None:
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
