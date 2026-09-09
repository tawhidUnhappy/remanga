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

There is one fingerprint, covering what the mix does: BGM, loudness and
panel gaps. There used to be a second for a per-clip voice chain; that stage
was removed because it cost roughly a quarter of real time per chapter for a
result too subtle to justify it, and the narration is now used exactly as
synthesized."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from remanga.config import AudioConfig

RECIPE_FILENAME = ".recipe.json"

# Everything that changes the mixed master. Listed explicitly rather than
# hashing the whole AudioConfig, so a field added later for something
# unrelated cannot silently invalidate every master in the project.
_MIX_KEYS = (
    "bgm_enabled", "bgm_path", "bgm_volume_db", "enable_loudnorm",
    "bgm_auto_level", "bgm_target_below_narration_db",
    "pause_between_panels_ms", "edge_fade_ms", "sample_rate",
)


def _digest(payload: dict[str, Any]) -> str:
    """A short, stable hash. sort_keys so a dict-ordering change - which
    changes nothing audible - cannot invalidate a whole project's cache."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


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


def write_recipe(directory: Path, *, mix: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / RECIPE_FILENAME).write_text(
        json.dumps({"mix": mix}, indent=2) + "\n", encoding="utf-8",
    )
