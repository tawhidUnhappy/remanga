"""audio_manifest.json: the raw clip files a narration run finished with, and
what each of them was, written once at the end of generate_narration_audio and
checked before anything downstream reads the audio folder again.

Nothing else in remanga deletes a raw clip out from under a chapter except
remanga's own code (a panel no longer narrated, or a full Reset/Delete,
which takes the manifest with it) - both of those also rewrite or remove the
manifest in the same step, so they never trip this. What this catches is
everything else: a clip moved, renamed or deleted by hand, a half-restored
backup, a folder copied without all its files. Zero trust on the user's
folder, not on remanga's own bookkeeping - the audio folder is meant to be
used as one unit even though it's many files on disk, and this is what
makes that true.

Each clip is recorded with its size and a hash of its bytes, not just its
name. A name tells you a file is still there and nothing else: a clip
truncated by a full disk, half-written by an older build, rewritten by
another tool or restored from the wrong backup all pass a name check and
then play as silence or noise in the middle of a finished chapter. The hash
is what turns those into an error at the start of the run that could still
fix them, which is the whole point of checking at all. It costs one read of
the folder - a 137-panel chapter is about 70MB, well under a second."""

from __future__ import annotations

import hashlib
from pathlib import Path

from remanga.json_io import read_json_or, write_json

MANIFEST_NAME = "audio_manifest.json"

# Read in blocks rather than whole files: a chapter's clips are small, but
# nothing here needs them in memory, and the loop is the same either way.
READ_BLOCK_BYTES = 1 << 20


class AudioManifestError(RuntimeError):
    """The audio folder no longer holds every clip it was generated with, or
    no longer holds the same bytes."""


def clip_digest(path: Path) -> str:
    """The clip's contents as a hex sha256."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(READ_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def write_audio_manifest(audio_dir: Path, chapter_num: str, clip_names: list[str]) -> None:
    """Records exactly the clips this narration run finished with, and what
    each one was. Called once, after synthesis - never partway through a run,
    so a manifest on disk always describes a complete, consistent set."""
    clips = []
    for name in sorted(clip_names):
        clip = audio_dir / name
        clips.append({"name": name, "bytes": clip.stat().st_size, "sha256": clip_digest(clip)})
    write_json(audio_dir / MANIFEST_NAME, {"chapter": str(chapter_num), "clips": clips})


def _listed(entry: str | dict) -> tuple[str, int | None, str | None]:
    """One manifest row as (name, bytes, sha256). A row written before this
    recorded anything but the name is just that name - an older chapter is
    checked as far as its manifest allows and no further, which is not the
    same thing as being broken."""
    if isinstance(entry, str):
        return entry, None, None
    return entry.get("name", ""), entry.get("bytes"), entry.get("sha256")


def verify_audio_manifest(audio_dir: Path, chapter_num: str) -> None:
    """Raises AudioManifestError if a clip the manifest lists is gone, or is
    no longer the file that was recorded. Does nothing when there is no
    manifest at all - a chapter narrated before this existed has nothing to
    check against, and that is not the same thing as being broken."""
    manifest = read_json_or(audio_dir / MANIFEST_NAME, None)
    if not manifest:
        return

    entries = manifest.get("clips", [])
    missing: list[str] = []
    changed: list[str] = []
    for entry in entries:
        name, size, digest = _listed(entry)
        clip = audio_dir / name
        if not name or not clip.exists():
            missing.append(name or "<unnamed>")
        elif size is not None and clip.stat().st_size != size:
            # A size that already differs says so without reading the file.
            changed.append(name)
        elif digest and clip_digest(clip) != digest:
            changed.append(name)

    if not missing and not changed:
        return

    def _some(names: list[str]) -> str:
        return ", ".join(names[:5]) + ("..." if len(names) > 5 else "")

    trouble = []
    if missing:
        trouble.append(f"{len(missing)} missing ({_some(missing)})")
    if changed:
        trouble.append(f"{len(changed)} changed since they were made ({_some(changed)})")
    raise AudioManifestError(
        f"Chapter {chapter_num}'s raw narration audio no longer matches the {len(entries)} clip(s) "
        f"it was generated with: {' and '.join(trouble)} - something outside remanga removed, "
        f"moved, renamed or rewrote them. Use Remake video to narrate the chapter again from "
        f"scratch."
    )
