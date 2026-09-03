"""Narration Writer web UI settings - see remanga/webui/writer_*.py."""

from __future__ import annotations

from pydantic import BaseModel


class WriterConfig(BaseModel):
    """The narration-writing web UI: where a user-authored narration.json comes
    from - the same panel-by-panel list as the Narration Reviewer, but each
    panel's field IS the narration text instead of a review note, for chapters
    where the user wants to write the script by hand instead of an LLM. See
    remanga/webui/writer_*.py. Separate host/port from ReviewerConfig/MarkerConfig
    so all three UIs could, in principle, be open at once without colliding."""
    host: str = "127.0.0.1"
    port: int = 8767
    auto_open_browser: bool = True
