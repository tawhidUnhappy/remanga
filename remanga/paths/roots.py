"""Every filesystem root remanga resolves other paths against - the single
place that knows where the repo lives on disk, where its bundled binaries
and isolated tool environments sit, where config.json is read from, and
where cross-project shared assets (voice/BGM/TTS transcript/narration
lessons) live. Every other module in remanga/paths/ builds on these instead
of re-deriving `Path(__file__).resolve().parent...` or `Path("config.json")`
on its own - that duplication (this exact literal used to be defined
separately in remanga/config/root.py AND remanga/webui/shortcuts_store.py) is
exactly what this package exists to rule out.

Swapping any of these later (e.g. config.json somewhere other than cwd, a
different tools/ layout) is a one-line change here, not a grep-and-replace
across the codebase."""

from __future__ import annotations

from pathlib import Path

# Two directories up from this file: remanga/paths/roots.py -> remanga/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Bundled binaries (ffmpeg/ffprobe/uv/uvx) - see bootstrap.sh.
BIN_DIR = REPO_ROOT / "bin"
UV_BIN = BIN_DIR / "uv"

# Isolated per-tool virtualenvs (indextts, audio8, magi, ...) bootstrap.sh
# provisions alongside the main .venv - see remanga/paths/tools.py.
TOOLS_DIR = REPO_ROOT / ".tools"

# config.json (the user's live settings) and config.example.json (the
# fallback/reference defaults) - both resolved relative to cwd, same as
# every entry point (run.sh, pipeline.sh) already assumes: they cd to the
# repo root before invoking remanga.cli.
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")

# Cross-project shared assets that aren't tied to any one manga: reference
# voice WAV, BGM file, the audio8 TTS transcript, and the narration-lessons
# log (see remanga/paths/global_assets.py). Deliberately a SIBLING of
# projects/, not a subdirectory of it - list_projects() (projects.py) walks
# every directory under projects/ and treats each as a manga project, so a
# folder for shared assets living inside it used to show up as a bogus
# project in the wizard's picker.
GLOBAL_DIR = Path("global")
