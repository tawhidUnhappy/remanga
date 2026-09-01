"""Audio mixing settings (BGM, loudnorm, edge fades) - see remanga/audio/mix.py."""

from __future__ import annotations

from pydantic import BaseModel


class AudioConfig(BaseModel):
    sample_rate: int = 44100
    edge_fade_ms: int = 35
    # The gap inserted between one panel's narration clip and the next in the
    # assembled master track (audio/mix.py) - not the silence a reaction-beat
    # panel's own empty-text clip gets (that's a fixed 500ms floor in
    # audio/tts.py, since it's the panel's content, not a gap between two
    # panels' audio). 0 means panels play back to back with no dead air
    # between them at all.
    pause_between_panels_ms: int = 0
    bgm_enabled: bool = False
    bgm_path: str = ""
    bgm_volume_db: float = -22.0
    enable_loudnorm: bool = True
