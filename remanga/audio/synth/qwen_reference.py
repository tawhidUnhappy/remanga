"""The recording a cloned Qwen voice is made from, as ONE clip/transcript pair:
never a transcript beside a clip it is not of (a word the model is shown and
never hears, it says out loud - see remanga-ops). Re-exported by qwen.py."""

from __future__ import annotations

import json
from pathlib import Path

from remanga.config.tts_qwen import QwenConfig

# How much of a reference recording the clone is built from. Qwen conditions
# on the start of the clip anyway, and a long one makes every generation
# slower - a 31-second reference pushed one chunk past the three-minute
# timeout, where 15 seconds of the same recording reads it comfortably, and
# 30 seconds blew a 670s timeout on a take the 15s clip finished in 325s.
#
# A ceiling, not the cut: where the clip actually ends is decided with its
# transcript, at the last sentence that finishes inside this (see
# audio/reference_text.py). Cutting on the stopwatch instead is what put
# words in a chapter that nobody wrote.
REFERENCE_MAX_SECONDS = 15.0


def reference_pair_path(sample: Path) -> Path:
    """Where the clip-and-transcript pair built from a recording is kept -
    beside the recording, named after it. One file describing both halves, so
    a transcript can never be read next to a clip it is not of."""
    return sample.with_name(f"{sample.stem}.reference.json")


def _fallback_clip(path: Path) -> Path:
    """The clone's reference when no pair was built (nothing could read the
    recording): the first REFERENCE_MAX_SECONDS of it, cut on the stopwatch.

    Safe only because a clip with no transcript is used through
    x_vector_only_mode - the speaker embedding alone - where the model is
    given no words at all and so has none to leak. The moment there IS a
    transcript, the pair decides the cut instead (audio/reference_text.py)."""
    from pydub import AudioSegment

    audio = AudioSegment.from_file(path)
    limit_ms = int(REFERENCE_MAX_SECONDS * 1000)
    if len(audio) <= limit_ms:
        return path.resolve()
    trimmed = path.with_name(f"{path.stem}.reference.wav")
    if not trimmed.exists() or trimmed.stat().st_mtime < path.stat().st_mtime:
        audio[:limit_ms].export(trimmed, format="wav")
    return trimmed.resolve()


def reference_pair(config: QwenConfig) -> tuple[Path, str]:
    """The clip the clone is built from and what it says - the pair
    audio/reference_text.py built, or the embedding-only fallback.

    The text is worth having rather than "": with it, the clone uses the
    recording IN CONTEXT instead of the speaker embedding alone. Measured on a
    take that collapses either way, in-context read 863 words where
    embedding-only managed 98, and 40% of the script was findable in it
    against 2%. It is only worth having while it is TRUE of the clip beside
    it, which is the whole job of reference_text.py."""
    sample = Path(config.designed_sample)
    if config.designed_text.strip():
        # remanga wrote this sample and chose its words - exact by construction.
        return sample.resolve(), config.designed_text.strip()
    try:
        saved = json.loads(reference_pair_path(sample).read_text(encoding="utf-8"))
        clip = sample.with_name(saved["clip"])
        text = str(saved["text"]).strip()
        if clip.exists() and text:
            return clip.resolve(), text
    except (OSError, ValueError, KeyError):
        pass
    return _fallback_clip(sample), ""
