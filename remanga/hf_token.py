"""Optional Hugging Face token, shared by every model download in remanga
(IndexTTS-2.5, Audio8 TTS, MAGI v3, DeepSeek-OCR-2) - config.json's
`system.hf_token_path` points at a small JSON file:

    {"token": "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}

(a plain text/env-var token isn't accepted directly, on purpose - a file
path means the actual token value never has to sit in config.json itself,
which gets displayed/printed/git-committed far more casually than a
one-off secrets file would). Used to raise Hugging Face Hub's per-IP rate
limit and download speed for unauthenticated requests (the Hub prints this
suggestion itself - see the remanga-ops skill's DeepSeek-OCR-2 section).

Defaults to global/hf_token.json - auto-created (blank "token", plus a
"_hint" field pointing at where to actually get one) the first time it's
asked for, via remanga/paths/global_assets.py:ensure_hf_token_file(), so
there's always a real file to drop a token into without editing config.json
or creating anything by hand first. Pointing hf_token_path at a different,
custom path is also supported; that one is never auto-created - a missing
custom path is a real misconfiguration worth a warning, not silently
materializing a file somewhere the user didn't ask for one.

A blank "token" is the normal "nothing configured yet" state and falls back
to unauthenticated silently, no warning - only a genuinely broken file
(malformed JSON, or missing the "token" field/type entirely) warns. Same
principle either way: a bad token setup should never turn a working
unauthenticated download into a broken one, only a present, well-formed,
non-blank token changes anything.

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
    """Reads config.json's system.hf_token_path and returns the token string
    inside it - or None (falls back to unauthenticated) for every "nothing
    configured / can't use it" case. Loads RemangaConfig fresh each call
    (cheap - see TTSEngine.generate_narration_audio's own RemangaConfig.load()
    for the same on-demand-reload pattern already used elsewhere) so a token
    added mid-session is picked up without restarting."""
    from remanga.config import RemangaConfig  # deferred: avoids a config<->hf_token import cycle
    from remanga.paths import ensure_hf_token_file, get_hf_token_path

    token_path_str = (RemangaConfig.load().system.hf_token_path or "").strip()
    if not token_path_str:
        return None  # explicitly cleared - opted out of this entirely

    path = Path(token_path_str).expanduser()

    if path.resolve() == get_hf_token_path().resolve():
        # The default location: always ensure it exists (blank placeholder +
        # hint) rather than warning about it being "missing" - that's the
        # expected state for anyone who hasn't set a token yet.
        path = ensure_hf_token_file()
    elif not path.exists():
        # A custom path the user pointed at themselves - missing here is a
        # real misconfiguration, not the normal unconfigured state.
        console.print(f"[yellow]HF token file not found at {path} - continuing without one (unauthenticated).[/]")
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[yellow]Couldn't parse HF token file at {path} ({e}) - continuing without one.[/]")
        return None

    if not isinstance(data, dict) or "token" not in data:
        console.print(f"[yellow]HF token file at {path} has no \"token\" field - continuing without one.[/]")
        return None

    token = data["token"]
    if not token:
        return None  # blank - the normal "nothing configured yet" state, no warning
    if not isinstance(token, str):
        console.print(f"[yellow]HF token file at {path}'s \"token\" field isn't a string - continuing without one.[/]")
        return None

    return token
