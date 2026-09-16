"""Static-asset directories the three Flask apps (Panel Marker, Narration
Reviewer, Narration Writer) serve their frontend from, plus the bundle two of
them share. Resolved from REPO_ROOT rather than each app's own
`Path(__file__).parent` so all four live in one place with every other path
remanga resolves, instead of being invisible to anyone not already reading
routes.py/reviewer_routes.py/writer_routes.py directly."""

from __future__ import annotations

from .roots import REPO_ROOT

MARKER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static"
REVIEWER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_review"
WRITER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_write"
# Served at /shared by the Writer and the Reviewer, which show the same panel
# images in the same list layout (the lightbox, and escaping text into it).
SHARED_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_shared"
