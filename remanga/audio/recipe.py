"""What produced the derived audio, so it can be reused or rebuilt on its own.

`audio/` is the expensive artifact - raw synthesized narration, minutes of
GPU time per chapter. `audio_modified/` is a cache derived from it: the
voice-chain-treated clips and the finished master. The standard rule for
that split is that a cache must be keyed on a fingerprint of every input
that produced it, so it invalidates itself rather than relying on anyone
remembering to clear it - and equally, so it is REUSED when nothing relevant
changed. Both halves matter here: the first stops a stale mix being shipped
after a settings change, the second is what makes changing one dB of gain
cost seconds instead of a full re-synthesis.

Two fingerprints, not one, because the two stages have different inputs and
wildly different costs:

  voice - the per-clip chain (audio/voice.py). Changing any of it means
          re-processing every panel, which is the slow part.
  mix   - BGM, ducking, loudness, panel gaps. Changing any of it only means
          re-assembling the master from clips that are already correct.

So swapping the background music does not re-run the voice chain, and
nudging the narration warmth does not force a re-download of anything. A
single combined fingerprint would collapse that distinction and make every
change cost the same as the most expensive one."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from remanga.config import AudioConfig

RECIPE_FILENAME = ".recipe.json"

# Settings that change what a PROCESSED CLIP sounds like. Listed explicitly
# rather than hashing the whole AudioConfig: most of it (bgm path, loudnorm,
# panel gaps) has no bearing on a single clip, and hashing it wholesale would
# throw away every processed clip in the project every time the music changed.
_VOICE_KEYS = (
    "voice_enhance", "voice_highpass_hz", "voice_warmth_db", "voice_presence_db",
    "voice_compress", "voice_compress_threshold_db", "voice_compress_ratio",
    "sample_rate",
)

# Settings that change the MASTER but not the clips it is assembled from.
_MIX_KEYS = (
    "bgm_enabled", "bgm_path", "bgm_volume_db", "enable_loudnorm",
    "pause_between_panels_ms", "edge_fade_ms", "sample_rate",
    "duck_music_under_narration", "duck_depth_db", "duck_fade_ms", "duck_carve_db",
)


def _digest(payload: dict[str, Any]) -> str:
    """A short, stable hash. sort_keys so a dict-ordering change - which
    changes nothing audible - cannot invalidate a whole project's cache."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def voice_fingerprint(audio_config: AudioConfig) -> str:
    """Deliberately does NOT include the TTS engine's own volume_boost_db.
    That gain is baked into the RAW clip by audio/tts.py as it is written, so
    it is part of what `audio/` holds, not part of what processing does to
    it - and audio_timing.json already tracks it for the resume path."""
    return _digest({k: getattr(audio_config, k, None) for k in _VOICE_KEYS})


def mix_fingerprint(audio_config: AudioConfig) -> str:
    payload = {k: getattr(audio_config, k, None) for k in _MIX_KEYS}
    # The music FILE, not just its path: swapping the contents of
    # global/bgm/track.wav while keeping the name is a real change, and a
    # path-only fingerprint would happily serve a master mixed with the old
    # one. Size+mtime rather than a content hash - the file can be hundreds
    # of MB and this runs on every mix.
    bgm = Path(str(audio_config.bgm_path or ""))
    if audio_config.bgm_enabled and bgm.is_file():
        stat = bgm.stat()
        payload["bgm_stat"] = [stat.st_size, int(stat.st_mtime)]
    return _digest(payload)


def read_recipe(directory: Path) -> dict[str, str]:
    """What produced the derived audio in `directory`, or {} if unknown.

    Unreadable counts as unknown, deliberately: a truncated recipe from an
    interrupted write should mean "rebuild", never "crash"."""
    path = directory / RECIPE_FILENAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_recipe(directory: Path, *, voice: str, mix: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / RECIPE_FILENAME).write_text(
        json.dumps({"voice": voice, "mix": mix}, indent=2) + "\n", encoding="utf-8",
    )
