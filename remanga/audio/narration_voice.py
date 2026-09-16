"""Which voice a chapter's clips are in, and whether that is still the voice
being asked for.

audio_timing.json records the narrator each clip beside it was synthesized
with, so a resume can tell "these clips are what I would produce now" from
"these clips are another voice" - the second being the case where resuming
would otherwise narrate half a chapter in a voice nobody asked for."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.config.tts import engine_spec


def narration_voice_identity(engine: str, voice: str) -> dict[str, Any]:
    """The voice a chapter's clips are in, as audio_timing.json records it.

    A recording is identified by its size and modification time as well as
    its path - the way the mix fingerprint identifies the BGM file - because
    re-exporting a cleaner take of the clip under the same name makes a
    different narrator, and the chapter should be re-voiced with it."""
    identity: dict[str, Any] = {"engine": engine, "voice": voice}
    if engine_spec(engine).clones_voice:
        clip = Path(voice).expanduser()
        if clip.is_file():
            stat = clip.stat()
            identity.update(voice=str(clip.resolve()), clip_bytes=stat.st_size, clip_mtime_ns=stat.st_mtime_ns)
    return identity


def voice_changed_from(previous_timing: dict[str, Any], identity: dict[str, Any]) -> str | None:
    """The voice the clips already on disk are in, named for a person, when
    that is not `identity` - None when it is, or when there are no clips yet.

    A manifest written before the voice was recorded came from Kokoro, so for
    those only the engine can be compared."""
    if not previous_timing:
        return None

    previous_voice = previous_timing.get("voice") or {"engine": "kokoro"}
    if "voice" in previous_voice:
        changed = previous_voice != identity
    else:
        changed = previous_voice.get("engine") != identity["engine"]
    if not changed:
        return None

    was = engine_spec(str(previous_voice.get("engine", ""))).display_name
    if previous_voice.get("voice"):
        was += f", {Path(str(previous_voice['voice'])).name}"
    return was
