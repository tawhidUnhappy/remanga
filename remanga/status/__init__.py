"""Chapter production status - computing it (compute.py) and printing it
(panel.py). Split because the computation is called constantly by the
wizard's own listings, while the printed panel is only ever the `status`
command's output."""

from __future__ import annotations

from remanga.status.compute import get_chapter_status
from remanga.status.panel import render_status_panel

__all__ = ["get_chapter_status", "render_status_panel"]
