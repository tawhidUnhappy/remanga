"""
remanga: manga pages to recap video - download, PDF for an LLM to narrate, Kokoro-82M narration, video.
"""

__version__ = "0.3.0"

# Before anything can shell out to ffmpeg. Importing remanga at all is enough
# to make the vendored binaries findable, so BGM in mp3/m4a/ogg/opus/flac
# works whether or not the process was started through run.sh - see
# remanga/bundled_bin.py for what used to happen when it was not.
from remanga.bundled_bin import ensure_bundled_bin_on_path as _ensure_bundled_bin

_ensure_bundled_bin()
