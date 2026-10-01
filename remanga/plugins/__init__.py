"""remanga's plug-ins: everything that comes in more than one flavour is a
plug-in, registered under its kind and found through the registry - nothing
in the pipeline names a particular engine, layout or site.

    kind     what one is                               built in
    tts      a narrator engine (TTSEngine)              kokoro, qwen_tts
    tool     an isolated environment (ToolSpec)         kokoro, qwen-tts, magi, faster-whisper
    layout   how images are marked into panels (Layout) pages, long_strip
    source   where manga come from (Source)             mangadex
    job      a queueable chapter action (Job)           jobs

Each built-in is a folder here holding all of its own code; its __init__.py
only registers a description (_kinds.py) that names that code by reference.
A plug-in of your own is a .py file or package in the repo's top-level
plugins/ folder, or an installed package with a `remanga.plugins` entry
point - see _loader.py, and plugins/README.md at the repo root.

The machinery is in the "_" modules: _registry.py (register/get/items),
_loader.py (discovery), _kinds.py (what each kind describes)."""

from __future__ import annotations

from remanga.plugins._kinds import Job, Layout, Source, TTSEngine
from remanga.plugins._loader import failures, load
from remanga.plugins._registry import KINDS, call, find, get, items, names, origin, register, resolve

__all__ = [
    "KINDS",
    "Job",
    "Layout",
    "Source",
    "TTSEngine",
    "call",
    "failures",
    "find",
    "get",
    "items",
    "load",
    "names",
    "origin",
    "register",
    "resolve",
]
