"""A project's store: every expensive result kept once, by what made it.

An object is a folder `store/<kind>/<key[:2]>/<key>/` holding its files and
`object.json` - the recipe it was made from (the inputs and settings that
decide it, which the key is the hash of), each file's size and SHA-256, and
when it was made. The rules, which nothing in remanga goes around:

- An object is written once. It is put together in `store/.tmp/` and
  renamed into place in one step, after its files are synced; a run killed
  halfway leaves a temp folder (cleared on the next run), never a half
  object. A key that is already there is never written again.
- An object is never changed. Its files are read-only; a chapter's folders
  use them through hard links (or copies, across disks), and every writer in
  remanga replaces a file by renaming a new one over it, so a link in a
  chapter's folder can be replaced, never written through.
- An object is only trusted whole: `find` checks its record and each file's
  size; `verify` checks every SHA-256.
- Same recipe, same key, same object - which is how a take, a word timing or
  a video already made is reused instead of made again."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import stat
import time
import uuid
from pathlib import Path
from typing import Any

from remanga.paths import get_project_dir

RECORD = "object.json"
# Bumped if the layout of an object changes.
LAYOUT = 1


def recipe_key(kind: str, recipe: dict[str, Any]) -> str:
    """The key of what `recipe` makes: SHA-256 of the kind and the recipe."""
    payload = json.dumps({"kind": kind, "layout": LAYOUT, "recipe": recipe}, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_only(path: Path) -> None:
    path.chmod(path.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _writable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IWUSR)


def link_or_copy(src: Path, dest: Path) -> None:
    """`src` at `dest` as a hard link (a copy across disks), in one step: a
    reader of `dest` sees the old file or the new one, nothing between."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.samefile(src):
        return  # already this very file
    tmp = dest.with_name(f".{dest.name}.{uuid.uuid4().hex[:8]}.tmp")
    try:
        os.link(src, tmp)
    except OSError:
        shutil.copy2(src, tmp)
    tmp.replace(dest)
    # rename() between two links of one file does nothing and leaves both
    # names (POSIX) - which left a hidden .tmp beside every video placed
    # again (2026-10-27: 29 of them across three projects).
    tmp.unlink(missing_ok=True)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Store:
    def __init__(self, project: str) -> None:
        self.root = get_project_dir(project) / "store"
        self._clear_dead_temps()

    def _dir(self, kind: str, key: str) -> Path:
        return self.root / kind / key[:2] / key

    def _clear_dead_temps(self) -> None:
        """Temp folders of runs that died before they finished an object."""
        tmp = self.root / ".tmp"
        if not tmp.is_dir():
            return
        for folder in tmp.iterdir():
            pid = folder.name.split("-", 1)[0]
            if pid.isdigit() and not _pid_alive(int(pid)):
                _remove_tree(folder)

    def find(self, kind: str, key: str) -> Path | None:
        """The object's folder when it is there whole, else None."""
        folder = self._dir(kind, key)
        try:
            record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        for name, info in record.get("files", {}).items():
            path = folder / name
            if not path.is_file() or path.stat().st_size != info.get("size"):
                return None
        return folder

    def record(self, kind: str, key: str) -> dict[str, Any] | None:
        folder = self.find(kind, key)
        return json.loads((folder / RECORD).read_text(encoding="utf-8")) if folder else None

    def put(self, kind: str, key: str, files: dict[str, Path], recipe: dict[str, Any],
            about: dict[str, Any] | None = None) -> Path:
        """`files` (stored name -> a finished file) kept as the object `key`
        of `kind`; the folder that holds it. A key already there is returned
        as it is - its files are never written again."""
        found = self.find(kind, key)
        if found:
            return found
        staging = self.root / ".tmp" / f"{os.getpid()}-{uuid.uuid4().hex[:12]}"
        staging.mkdir(parents=True)
        try:
            listed = {}
            for name, src in files.items():
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    os.link(src, dest)
                except OSError:
                    shutil.copy2(src, dest)
                with dest.open("rb") as f:
                    os.fsync(f.fileno())
                listed[name] = {"size": dest.stat().st_size, "sha256": file_sha256(dest)}
                _read_only(dest)
            (staging / RECORD).write_text(json.dumps(
                {"kind": kind, "key": key, "made": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "recipe": recipe, "about": about or {}, "files": listed}, indent=2, default=str),
                encoding="utf-8")
            final = self._dir(kind, key)
            final.parent.mkdir(parents=True, exist_ok=True)
            try:
                staging.rename(final)
            except OSError:
                # Another run finished the same key first: that one stands.
                if self.find(kind, key):
                    _remove_tree(staging)
                    return final
                raise
            return final
        except BaseException:
            _remove_tree(staging)
            raise

    def place(self, kind: str, key: str, name: str, dest: Path) -> bool:
        """The object's file `name` put at `dest` (see link_or_copy) - after
        every file of it is checked against its SHA-256, so a damaged object
        is never used (it is set aside, see set_aside, and made again). False
        when the object is not there, or not whole."""
        folder = self.find(kind, key)
        if folder is None or not (folder / name).is_file():
            return False
        if not self.verify(kind, key):
            self.set_aside(kind, key)
            return False
        link_or_copy(folder / name, dest)
        return True

    def set_aside(self, kind: str, key: str) -> Path | None:
        """A damaged object moved to `store/damaged/` - never deleted, so
        whoever wants to look at it can - and out of the way, so the next run
        makes it again."""
        folder = self._dir(kind, key)
        if not folder.is_dir():
            return None
        dest = self.root / "damaged" / f"{kind}-{key[:16]}-{time.strftime('%Y%m%d-%H%M%S')}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        folder.rename(dest)
        return dest

    def verify(self, kind: str, key: str) -> bool:
        """Every file of the object against its SHA-256 (slow: reads it all)."""
        folder = self.find(kind, key)
        if folder is None:
            return False
        record = json.loads((folder / RECORD).read_text(encoding="utf-8"))
        return all(file_sha256(folder / name) == info["sha256"] for name, info in record["files"].items())

    def size(self, kind: str, key: str) -> int:
        record = self.record(kind, key)
        return sum(info["size"] for info in (record or {}).get("files", {}).values())

    def remove(self, kind: str, key: str) -> None:
        """Deletes one object - only ever on the user's say-so (a version
        deleted in the menus), never to make room."""
        folder = self._dir(kind, key)
        if folder.is_dir():
            _remove_tree(folder)


def _remove_tree(folder: Path) -> None:
    """A folder of read-only files, removed: write permission back first."""
    for path in sorted(folder.rglob("*"), reverse=True):
        with contextlib.suppress(OSError):
            _writable(path)
    with contextlib.suppress(OSError):
        _writable(folder)
    shutil.rmtree(folder, ignore_errors=True)
