"""The optional Hugging Face token under global/, used when downloading the
Kokoro weights (see remanga/hf_token.py)."""

from __future__ import annotations

import json
from pathlib import Path

from .roots import GLOBAL_DIR


def get_hf_token_path() -> Path:
    p = GLOBAL_DIR / "hf_token.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def ensure_hf_token_file() -> Path:
    """A placeholder the first time it's needed, never clobbering a token
    already written there. A blank token means download unauthenticated."""
    p = get_hf_token_path()
    if not p.exists():
        placeholder = {
            "token": "",
            "_hint": "Optional - a Hugging Face access token ('Read' scope) raises the Hub's rate limit when "
                     "downloading Kokoro-82M. Leave \"token\" blank to download without one.",
        }
        p.write_text(json.dumps(placeholder, indent=2) + "\n", encoding="utf-8")
    return p
