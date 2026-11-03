"""Which voice a chapter's clips are in, and whether that is still the voice
being asked for.

audio_timing.json records the narrator the clips beside it were synthesized
with - engine included - so a resume can tell "these clips are what I would
produce now" from "these clips are another voice", where resuming would
otherwise narrate half a chapter in a voice nobody asked for. What goes in it
is the engine's own `identity()` (config/tts.py), so an engine whose voice is
not a name says so in its own terms."""

from __future__ import annotations

from typing import Any


def voice_changed_from(previous_timing: dict[str, Any], identity: dict[str, Any]) -> str | None:
    """The voice the clips on disk are in, when that is not `identity` - None
    when it is, or when there are no clips yet."""
    if not previous_timing:
        return None
    previous = previous_timing.get("voice") or {}
    if previous == identity:
        return None
    engine = previous.get("engine", "another engine")
    voice = previous.get("voice", "another voice")
    speed = f" at {previous['speed']:g}x" if previous.get("speed") not in (None, 1.0) else ""
    if previous.get("engine") == identity.get("engine") and previous.get("voice") == identity.get("voice"):
        return f"{engine}, {voice} - with other settings{speed}"
    return f"{engine}, {voice}{speed}"
