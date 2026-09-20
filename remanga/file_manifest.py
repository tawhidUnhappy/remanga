"""A folder of generated files, checked as one unit.

A chapter's narration is many files on disk but one thing conceptually: a
folder missing three clips is not a chapter with three quiet panels, it is a
folder something outside remanga has been into. The manifest is what makes
that difference visible - written once, at the end of a run that finished,
listing exactly what that run produced, and checked before anything reads
the folder again.

Each row carries the file's size and a hash of its bytes, not just its name.
A name only proves something is still there: a file truncated by a full
disk, half-written by an older build, rewritten by another tool or restored
from the wrong backup all pass a name check and then fail later, somewhere
that cannot explain itself. Size is the cheap pre-check and the hash catches
the rest, including a file rewritten to exactly its old length.

Audio and subtitles both use this - what differs between them is only what
the file is called, what to call it in a message, and what the user should
do about it, which is a ManifestKind."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from remanga.json_io import read_json_or, write_json

# Read in blocks rather than whole files: these are small, but nothing here
# needs them in memory and the loop is the same either way.
READ_BLOCK_BYTES = 1 << 20

# How many names an error lists before it stops and says how many more.
NAMES_IN_MESSAGE = 5


class ManifestError(RuntimeError):
    """A folder no longer holds every file it was generated with, or no
    longer holds the same bytes."""


@dataclass(frozen=True)
class ManifestKind:
    """One kind of folder: its manifest's file name, what its contents are
    called in a message, and what the user can do when the check fails."""

    file_name: str
    what: str
    advice: str


def file_digest(path: Path) -> str:
    """The file's contents as a hex sha256."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def write_manifest(directory: Path, kind: ManifestKind, chapter_num: str, names: list[str]) -> None:
    """Records exactly the files this run finished with, and what each one
    was. Called once, after the run - never partway through, so a manifest on
    disk always describes a complete, consistent set."""
    files = []
    for name in sorted(names):
        path = directory / name
        files.append({"name": name, "bytes": path.stat().st_size, "sha256": file_digest(path)})
    write_json(directory / kind.file_name, {"chapter": str(chapter_num), "files": files})


def _rows(manifest: dict) -> list:
    """The manifest's rows, under whichever key it was written with. `clips`
    is what the audio manifest called them before this was shared."""
    for key in ("files", "clips"):
        if isinstance(manifest.get(key), list):
            return manifest[key]
    return []


def _listed(entry: str | dict) -> tuple[str, int | None, str | None]:
    """One row as (name, bytes, sha256). A row written before sizes and
    hashes were recorded is just a name - a folder from then is checked as
    far as its manifest allows and no further, which is not the same thing as
    being broken."""
    if isinstance(entry, str):
        return entry, None, None
    return entry.get("name", ""), entry.get("bytes"), entry.get("sha256")


def verify_manifest(directory: Path, kind: ManifestKind, chapter_num: str) -> None:
    """Raises ManifestError if a file the manifest lists is gone, or is no
    longer the file that was recorded. Does nothing when there is no manifest
    at all - a chapter made before this existed has nothing to check against,
    and that is not the same thing as being broken."""
    manifest = read_json_or(directory / kind.file_name, None)
    if not manifest:
        return

    rows = _rows(manifest)
    missing: list[str] = []
    changed: list[str] = []
    for entry in rows:
        name, size, digest = _listed(entry)
        path = directory / name
        if not name or not path.exists():
            missing.append(name or "<unnamed>")
        elif size is not None and path.stat().st_size != size:
            # A size that already differs says so without reading the file.
            changed.append(name)
        elif digest and file_digest(path) != digest:
            changed.append(name)

    if not missing and not changed:
        return

    def _some(names: list[str]) -> str:
        shown = ", ".join(names[:NAMES_IN_MESSAGE])
        extra = len(names) - NAMES_IN_MESSAGE
        return f"{shown} and {extra} more" if extra > 0 else shown

    trouble = []
    if missing:
        trouble.append(f"{len(missing)} missing ({_some(missing)})")
    if changed:
        trouble.append(f"{len(changed)} changed since they were made ({_some(changed)})")
    raise ManifestError(
        f"Chapter {chapter_num}'s {kind.what} no longer matches the {len(rows)} file(s) it was "
        f"generated with: {' and '.join(trouble)} - something outside remanga removed, moved, "
        f"renamed or rewrote them. {kind.advice}"
    )
