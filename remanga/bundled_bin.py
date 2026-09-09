"""Makes the vendored ffmpeg/ffprobe findable however remanga was started.

The repo ships its own ffmpeg and ffprobe in bin/ so a machine does not need
system ones, and run.sh prepends bin/ to PATH before launching. That covers
`./run.sh` and `./pipeline.sh` and nothing else - so `python -m remanga.cli`,
an editor's run button, a cron entry, or importing remanga from a script all
fell back to whatever ffmpeg the system happened to have.

On a machine with no system ffmpeg that is not a graceful degradation.
pydub reads every format except WAV by shelling out, so BGM loading fails
for mp3, m4a, ogg, opus, flac and aac with `FileNotFoundError: 'ffprobe'` -
measured, all six - while WAV keeps working, which makes it look like a
problem with the user's file rather than a missing binary. MP3 is the most
common thing anyone points BGM at.

Prepending here rather than setting pydub's `AudioSegment.converter` fixes
it once for everything that shells out - pydub's decoder AND its separate
ffprobe call AND remanga's own ffmpeg_io - instead of for whichever of them
somebody remembers to configure."""

from __future__ import annotations

import os

from remanga.paths.roots import BIN_DIR


def ensure_bundled_bin_on_path() -> bool:
    """Puts bin/ first on PATH for this process. Returns whether it did.

    Idempotent, and a no-op when bin/ holds no ffmpeg - a checkout that has
    not been bootstrapped yet should fall back to the system's copy rather
    than have a non-existent directory shadow it."""
    if not (BIN_DIR / "ffmpeg").exists() and not (BIN_DIR / "ffmpeg.exe").exists():
        return False

    bin_dir = str(BIN_DIR.resolve())
    current = os.environ.get("PATH", "")
    if current.split(os.pathsep)[:1] == [bin_dir]:
        return True
    parts = [p for p in current.split(os.pathsep) if p and p != bin_dir]
    os.environ["PATH"] = os.pathsep.join([bin_dir, *parts])
    return True
