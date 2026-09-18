"""Which voice a chapter's clips are in, and whether that is still the voice
being asked for.

audio_timing.json records the narrator the clips beside it were synthesized
with, so a resume can tell "these clips are what I would produce now" from
"these clips are another voice" - where resuming would otherwise narrate half a
chapter in a voice nobody asked for."""

from __future__ import annotations

from typing import Any


def narration_voice_identity(voice: str, speed: float) -> dict[str, Any]:
    """The voice AND its speed: a clip made at another speed is another
    delivery, and resuming over it would mix two paces in one chapter."""
    return {"engine": "kokoro", "voice": voice, "speed": round(float(speed), 3)}


def voice_changed_from(previous_timing: dict[str, Any], identity: dict[str, Any]) -> str | None:
    """The voice the clips on disk are in, when that is not `identity` - None
    when it is, or when there are no clips yet."""
    if not previous_timing:
        return None
    previous = previous_timing.get("voice") or {}
    if previous == identity:
        return None
    speed = f" at {previous['speed']:g}x" if "speed" in previous else ""
    return f"{previous.get('engine', 'another engine')}, {previous.get('voice', 'another voice')}{speed}"
