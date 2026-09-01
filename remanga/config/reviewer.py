"""Narration Reviewer web UI settings - see remanga/webui/reviewer_*.py."""

from __future__ import annotations

from pydantic import BaseModel


class ReviewerConfig(BaseModel):
    """The narration-review web UI: where narration_review.json comes from -
    a panel-by-panel pass over an LLM-written narration.json where the user
    flags lines that are wrong before they ever reach TTS. See remanga/webui/
    reviewer_*.py. Separate host/port from MarkerConfig so both UIs could, in
    principle, be open at once without colliding."""
    host: str = "127.0.0.1"
    port: int = 8766
    auto_open_browser: bool = True
