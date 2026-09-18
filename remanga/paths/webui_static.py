"""Where each web UI serves its frontend from - the Panel Marker, the
Narration Writer, the Narration Reviewer, and the bundle the last two share.
Resolved from REPO_ROOT like every other path remanga uses, rather than from
each routes.py's own `Path(__file__).parent`."""

from __future__ import annotations

from .roots import REPO_ROOT

MARKER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static"
REVIEWER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_review"
WRITER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_write"
# Served at /shared by the Writer and the Reviewer, which show the same panel
# images in the same list layout (the lightbox, and escaping text into it).
SHARED_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static_shared"
