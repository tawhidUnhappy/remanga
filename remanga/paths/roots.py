"""Every filesystem root the other path modules build on."""

from __future__ import annotations

from pathlib import Path

# Two directories up from this file: remanga/paths/roots.py -> remanga/ -> repo root.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Bundled binaries (ffmpeg/ffprobe/uv/uvx) - see bootstrap.sh.
BIN_DIR = REPO_ROOT / "bin"
UV_BIN = BIN_DIR / "uv"

# Kokoro's isolated virtualenv (.tools/venv-kokoro) - see remanga/tool_envs/.
TOOLS_DIR = REPO_ROOT / ".tools"

# config.json (the user's live settings) and config.example.json (the
# fallback/reference defaults) - both resolved relative to cwd, same as
# every entry point (run.sh, pipeline.sh) already assumes: they cd to the
# repo root before invoking remanga.cli.
CONFIG_PATH = Path("config.json")
CONFIG_EXAMPLE_PATH = Path("config.example.json")

# The prompt uploaded to the LLM with each chapter's PDF.
PROMPTS_DIR = REPO_ROOT / "prompts"

# Shared across projects: background music (global/bgm/) and the optional
# Hugging Face token. A sibling of projects/, so it never shows up as a project.
GLOBAL_DIR = Path("global")
