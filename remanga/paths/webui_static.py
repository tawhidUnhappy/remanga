"""Static-asset directories the two Flask apps (Panel Marker, Narration
Reviewer) serve their frontend from. Resolved from REPO_ROOT rather than
each app's own `Path(__file__).parent` so both live in one place with every
other path remanga resolves, instead of being invisible to anyone not
already reading routes.py/reviewer_routes.py directly."""

from __future__ import annotations

from .roots import REPO_ROOT

MARKER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static"
REVIEWER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_review"
