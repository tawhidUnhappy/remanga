"""MAGI v3 panel detection for a project's chapters, headless - what the Panel Marker's
Detect does, saved straight to each chapter's crops.json (reading order from project.json).

    PYTHONPATH=. .venv/bin/python .claude/skills/remanga-long-recap/detect.py PROJECT 1,2.1,2.2

Run from the remanga repo root (model paths are relative to it). MAGI is wrong on roughly
one page in eight here, so review every page afterwards (overlay.py) - see SKILL.md."""
import sys
import time

from remanga.config import RemangaConfig
from remanga.paths import load_project_metadata
from remanga.webui.detection import run_detection
from remanga.webui.marker_session import MarkerSession

project, chapters = sys.argv[1], sys.argv[2].split(",")
config = RemangaConfig.load()
direction = load_project_metadata(project).get("reading_direction", "right_to_left")
session = MarkerSession(project, chapters)
for ch in chapters:
    started = time.time()
    run_detection(session.state_for(ch), config.marker, order_direction=direction)
    print(ch, "saved", session.save_chapter(ch), f"{time.time() - started:.0f}s", flush=True)
