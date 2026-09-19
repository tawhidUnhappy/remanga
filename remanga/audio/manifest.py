"""audio_manifest.json: the list of raw clip files a narration run finished
with, written once at the end of generate_narration_audio and checked before
anything downstream reads the audio folder again.

Nothing else in remanga deletes a raw clip out from under a chapter except
remanga's own code (a panel no longer narrated, or a full Reset/Delete,
which takes the manifest with it) - both of those also rewrite or remove the
manifest in the same step, so they never trip this. What this catches is
everything else: a clip moved, renamed or deleted by hand, a half-restored
backup, a folder copied without all its files. Zero trust on the user's
folder, not on remanga's own bookkeeping - the audio folder is meant to be
used as one unit even though it's many files on disk, and this is what
makes that true."""

from __future__ import annotations

from pathlib import Path

from remanga.json_io import read_json_or, write_json

MANIFEST_NAME = "audio_manifest.json"


class AudioManifestError(RuntimeError):
    """The audio folder no longer holds every clip it was generated with."""


def write_audio_manifest(audio_dir: Path, chapter_num: str, clip_names: list[str]) -> None:
    """Records exactly the clips this narration run finished with. Called
    once, after synthesis - never partway through a run, so a manifest on
    disk always describes a complete, consistent set of clips."""
    write_json(audio_dir / MANIFEST_NAME, {"chapter": str(chapter_num), "clips": sorted(clip_names)})


def verify_audio_manifest(audio_dir: Path, chapter_num: str) -> None:
    """Raises AudioManifestError if a clip the manifest lists is no longer on
    disk. Does nothing when there is no manifest at all - a chapter narrated
    before this existed has nothing to check against, and that is not the
    same thing as being broken."""
    manifest = read_json_or(audio_dir / MANIFEST_NAME, None)
    if not manifest:
        return
    missing = [name for name in manifest.get("clips", []) if not (audio_dir / name).exists()]
    if not missing:
        return
    shown = ", ".join(missing[:5]) + ("..." if len(missing) > 5 else "")
    raise AudioManifestError(
        f"Chapter {chapter_num}'s raw narration audio is missing {len(missing)} of "
        f"{len(manifest.get('clips', []))} clip(s) it was generated with ({shown}) - "
        f"something outside remanga removed, moved or renamed them. Use Remake video "
        f"to narrate the chapter again from scratch."
    )
