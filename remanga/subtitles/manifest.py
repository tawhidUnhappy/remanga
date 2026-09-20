"""subtitle_manifest.json: the word-timing files a narration run finished
with, checked the same way the audio folder is (remanga/file_manifest.py)."""

from __future__ import annotations

from pathlib import Path

from remanga.file_manifest import ManifestKind, verify_manifest, write_manifest

SUBTITLE_MANIFEST = ManifestKind(
    file_name="subtitle_manifest.json",
    what="narration word timings",
    advice="Use Remake video to read them again from the audio.",
)

MANIFEST_NAME = SUBTITLE_MANIFEST.file_name


def write_subtitle_manifest(subs_dir: Path, chapter_num: str, names: list[str]) -> None:
    write_manifest(subs_dir, SUBTITLE_MANIFEST, chapter_num, names)


def verify_subtitle_manifest(subs_dir: Path, chapter_num: str) -> None:
    verify_manifest(subs_dir, SUBTITLE_MANIFEST, chapter_num)
