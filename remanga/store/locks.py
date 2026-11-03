"""One job at a time on a chapter: a lock taken by whatever writes a
chapter's narration, sound or video (workflow/video.py), so the queue and a
menu action - or two terminals - can never write the same chapter at once.

An flock on `store/locks/chapter_<N>.lock`: the operating system lets go of
it when the process ends, however it ends, so a crash never leaves a chapter
locked. Within one process the lock is re-entrant - make_video holds it and
calls narrate, mix and render, which take it too."""

from __future__ import annotations

import contextlib
import fcntl
import os
import threading
from collections.abc import Iterator
from pathlib import Path

from remanga.paths import get_project_dir


class ChapterBusy(RuntimeError):
    """Another run is working on this chapter."""


_held: dict[Path, int] = {}
_guard = threading.Lock()


def _lock_path(project: str, chapter: str) -> Path:
    return get_project_dir(project) / "store" / "locks" / f"chapter_{chapter}.lock"


@contextlib.contextmanager
def chapter_lock(project: str, chapter: str) -> Iterator[None]:
    path = _lock_path(project, chapter)
    with _guard:
        if path in _held:
            _held[path] += 1
            fd = None
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                holder = os.read(fd, 64).decode(errors="replace").strip() or "another run"
                os.close(fd)
                raise ChapterBusy(f"Chapter {chapter} is being worked on by {holder} - wait for it to "
                                  f"finish (the queue, or another terminal), then run this again.") from None
            os.ftruncate(fd, 0)
            os.write(fd, f"process {os.getpid()}".encode())
            _held[path] = 1
    try:
        yield
    finally:
        with _guard:
            _held[path] -= 1
            if _held[path] == 0:
                del _held[path]
                if fd is not None:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
