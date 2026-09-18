"""Where the Panel Marker serves its frontend from. Resolved from REPO_ROOT
like every other path remanga uses, rather than from webui/routes.py's own
`Path(__file__).parent`."""

from __future__ import annotations

from .roots import REPO_ROOT

MARKER_STATIC_DIR = REPO_ROOT / "remanga" / "webui" / "static"
