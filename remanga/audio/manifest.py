"""audio_manifest.json: the raw clip files a narration run finished with.

The folder-as-one-unit check itself, and why each row carries a hash rather
than just a name, is remanga/file_manifest.py. This is only what that check
is called and says for the audio folder.

Nothing else in remanga deletes a raw clip out from under a chapter except
remanga's own code (a panel no longer narrated, or a full Reset/Delete,
which takes the manifest with it) - both of those also rewrite or remove the
manifest in the same step, so they never trip this. What it catches is
everything else: a clip moved, renamed or deleted by hand, a half-restored
backup, a folder copied without all its files. Zero trust on the user's
folder, not on remanga's own bookkeeping."""

from __future__ import annotations

from pathlib import Path

from remanga.file_manifest import ManifestError, ManifestKind, verify_manifest, write_manifest

AUDIO_MANIFEST = ManifestKind(
    file_name="audio_manifest.json",
    what="raw narration audio",
    advice="Use Remake video to narrate the chapter again from scratch.",
)

# Kept as names of their own: callers and older code know the audio folder's
# manifest by these, and neither has any business knowing it is shared.
MANIFEST_NAME = AUDIO_MANIFEST.file_name
AudioManifestError = ManifestError


def write_audio_manifest(audio_dir: Path, chapter_num: str, clip_names: list[str]) -> None:
    """Records exactly the clips this narration run finished with."""
    write_manifest(audio_dir, AUDIO_MANIFEST, chapter_num, clip_names)


def verify_audio_manifest(audio_dir: Path, chapter_num: str) -> None:
    """Raises AudioManifestError if the audio folder no longer holds what it
    was generated with."""
    verify_manifest(audio_dir, AUDIO_MANIFEST, chapter_num)
