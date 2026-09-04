"""Filesystem-side helpers for the settings screens: validating a path the
user gave, reading/writing the TTS reference transcript, and - the part
that keeps those screens from asking questions they can answer themselves -
finding the asset files that are already on disk.

Discovery matters more than it looks. Every path remanga asks a user for
(reference voice WAV, background music, transcript) is nearly always
already sitting in global/voice/ or global/bgm/, put there by bootstrap or
by the user five minutes earlier. Listing what's actually there turns
"type the absolute path to your reference voice" into picking a row, and
leaves typing a path as the escape hatch for the file that lives elsewhere."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from remanga.paths import GLOBAL_DIR

# What counts as an audio asset when scanning for candidates. Deliberately
# broader than what any one engine accepts - ffmpeg decodes all of these on
# the BGM side, and offering a file remanga can't use is a far smaller
# problem than hiding one it can.
AUDIO_EXTENSIONS = (".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac", ".opus")
TEXT_EXTENSIONS = (".txt", ".md")


def is_valid_file(raw_path: str, min_size: int = 0) -> Optional[Path]:
    """Returns the resolved Path if `raw_path` points at an existing,
    non-empty-enough file, else None."""
    raw_path = (raw_path or "").strip()
    if not raw_path:
        return None
    p = Path(raw_path).expanduser()
    if p.exists() and p.is_file() and p.stat().st_size >= min_size:
        return p
    return None


def discover_files(
    extensions: Sequence[str],
    *,
    preferred_subdir: str = "",
    extra_dirs: Iterable[Path] = (),
    limit: int = 40,
) -> List[Path]:
    """Every candidate file for one kind of asset, best guess first.

    Ordering is the whole point: files under global/<preferred_subdir>/ come
    first (that's where this asset kind belongs and where bootstrap puts
    it), then anything else under global/, then the directories a caller
    adds - normally the folder the currently-configured file lives in, so
    its siblings are one keypress away when swapping to a different take of
    the same recording.

    Capped at `limit` so a global/ folder someone has dropped a sample
    library into produces a usable menu rather than a thousand-row wall."""
    roots: List[Path] = []
    if preferred_subdir:
        roots.append(GLOBAL_DIR / preferred_subdir)
    roots.append(GLOBAL_DIR)
    roots.extend(extra_dirs)

    seen = set()
    found: List[Path] = []
    for root in roots:
        if not root or not root.exists() or not root.is_dir():
            continue
        try:
            entries = sorted(root.rglob("*") if root == GLOBAL_DIR else root.iterdir(),
                             key=lambda p: p.name.casefold())
        except OSError:
            continue
        for entry in entries:
            if len(found) >= limit:
                return found
            if not entry.is_file() or entry.suffix.lower() not in extensions:
                continue
            try:
                resolved = entry.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(entry)
    return found


def parent_dir_of(raw_path: str) -> List[Path]:
    """The directory holding whatever is configured right now, as a
    single-item list ready to pass to `discover_files(extra_dirs=...)`.
    Empty when nothing is configured or it no longer exists."""
    valid = is_valid_file(raw_path)
    return [valid.parent] if valid else []


def read_reference_text(path: str) -> str:
    """Reads the TTS reference transcript from its own text file rather than
    inline config.json (see Audio8Config.reference_text_path). A missing or
    empty file reads as "" - the worker tolerates an empty transcript
    (degraded cloning quality, not an error), so this stays a soft fallback
    rather than raising."""
    p = Path((path or "").strip()).expanduser()
    if not p.exists() or not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


def write_reference_text(path: str, text: str) -> Path:
    """Writes `text` to the reference-transcript file, creating its parent
    directory (typically global/) if needed. Returns the resolved path."""
    p = Path((path or "").strip()).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text((text or "").strip(), encoding="utf-8")
    return p.resolve()
