"""Runs MAGI v3 panel detection for one chapter, streaming progress into its
MarkerState so the browser (polling GET /api/detect/status - see routes.py)
sees pages fill in one at a time instead of blocking on the whole chapter.

This is the unit of work, not the scheduler: what gets detected, in what
order, and on which thread is MarkerSession's detection queue
(marker_session.py). Only one of these runs at a time - MAGI loads a model
onto the GPU per pass, and two at once is how a machine with one GPU starts
swapping instead of working.
"""

from __future__ import annotations

from remanga.config import MarkerConfig
from remanga.console import console, escape as _esc
from remanga.webui.marker_state import MarkerState


def run_detection(state: MarkerState, config: MarkerConfig,
                  only_pages: list[str] | None = None, force: bool = False) -> None:
    """Detects panels for this chapter, streaming progress into `state`.

    `only_pages` narrows it to specific page filenames - what the assist
    card's "This page" scope asks for. Left None it means every page of the
    chapter that the user hasn't already touched, which is what every other
    scope wants.

    `force` carries that same single-page request down to apply_detected,
    where it lets a page previously recorded as having no panels be detected
    after all - see MarkerState.apply_detected for why that is safe and why
    a page with marks on it is still refused.
    """
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
    wanted = set(only_pages) if only_pages is not None else None

    def is_pending(page: dict) -> bool:
        filename = page["filename"]
        if wanted is not None and filename not in wanted:
            return False
        if filename not in state.touched:
            return True
        # Touched: only a forced request for a page with nothing on it gets
        # through, which is exactly what apply_detected will accept.
        return force and not state.marks.get(filename)

    pending_pages = [p for p in state.pages if is_pending(p)]

    state.detect_running = True
    state.detect_done = 0
    state.detect_total = len(pending_pages)
    state.detect_error = None

    if not pending_pages:
        state.detect_running = False
        return

    def on_page_done(filename: str, boxes: list[list[float]]) -> None:
        state.apply_detected(filename, boxes, force=force)
        state.detect_done += 1

    try:
        page_paths = [state.pages_dir / p["filename"] for p in pending_pages]
        detect_panels_for_pages(page_paths, config, on_page_done=on_page_done)
    except Exception as e:
        state.detect_error = str(e)
        console.print(f"[bold red]MAGI v3 detection failed:[/] {_esc(str(e))}")
    finally:
        state.detect_running = False
