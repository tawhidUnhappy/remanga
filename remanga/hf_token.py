"""Optional Hugging Face token, shared by every model download in remanga
(IndexTTS-2.5, Audio8 TTS, MAGI v3, DeepSeek-OCR-2) - config.json's
`system.hf_token_path`, if set, points at a small JSON file:

    {"token": "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}

(a plain text/env-var token isn't accepted directly, on purpose - a file
path means the actual token value never has to sit in config.json itself,
which gets displayed/printed/git-committed far more casually than a
one-off secrets file would). Used to raise Hugging Face Hub's per-IP rate
limit and download speed for unauthenticated requests (the Hub prints this
suggestion itself - see the remanga-ops skill's DeepSeek-OCR-2 section).

If the path is empty, missing, or the file is malformed/lacks a "token"
field, every caller here falls straight back to today's plain unauthenticated
behavior - a bad token FILE should never turn a working unauthenticated
download into a broken one, only a present, well-formed one changes
anything.

Passed to each download script as a plain positional CLI argument (see
models/weights.py:ModelManager.ensure_model and magi_assist.py's own
subprocess call) - simple and consistent with every other arg these scripts
already take, at the cost of being visible to `ps`/`/proc/<pid>/cmdline` for
other local users on a shared machine for the download's duration. Fine for
remanga's single-user local-machine use case; flag if that ever changes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from remanga.console import console


def resolve_hf_token() -> Optional[str]:
    """Reads config.json's system.hf_token_path, if set, and returns the
    token string inside it - or None (falls back to unauthenticated) for
    every "nothing configured / can't use it" case. Loads RemangaConfig
    fresh each call (cheap - see TTSEngine.generate_narration_audio's own
    RemangaConfig.load() for the same on-demand-reload pattern already used
    elsewhere) so a token added mid-session is picked up without restarting."""
    from remanga.config import RemangaConfig  # deferred: avoids a config<->hf_token import cycle

    token_path = (RemangaConfig.load().system.hf_token_path or "").strip()
    if not token_path:
        return None

    path = Path(token_path).expanduser()
    if not path.exists():
        console.print(f"[yellow]HF token file not found at {path} - continuing without one (unauthenticated).[/]")
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[yellow]Couldn't parse HF token file at {path} ({e}) - continuing without one.[/]")
        return None

    token = data.get("token") if isinstance(data, dict) else None
    if not token or not isinstance(token, str):
        console.print(f"[yellow]HF token file at {path} has no \"token\" string field - continuing without one.[/]")
        return None

    return token
