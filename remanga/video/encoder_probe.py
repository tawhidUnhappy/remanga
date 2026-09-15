"""Which ffmpeg and codec a render encodes with: the GPU encoder when one
actually works against this machine's driver right now - the bundled
ffmpeg's first, then a system ffmpeg's - else the CPU fallback. Probed once
per renderer, and mixed into VideoRenderer (render.py)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from remanga.ffmpeg_io import run_ffmpeg
from remanga.paths import BIN_DIR


class EncoderChoiceMixin:
    """VideoRenderer's encoder choice. Uses the renderer's `system_config`
    and caches the answer in `_encoder_choice`."""

    def _probe_nvenc(self, ffmpeg_bin: str) -> subprocess.CompletedProcess:
        # A too-small test frame fails NVENC's own minimum-dimension check even
        # when the encoder is otherwise fully working ("Frame Dimension less
        # than the minimum supported value") - indistinguishable from a real
        # failure unless the test frame is comfortably above that floor.
        # 256x256 clears it with real margin while still encoding instantly.
        cmd = [
            ffmpeg_bin, "-y", "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.1",
            "-c:v", self.system_config.resolve_gpu_codec(), "-f", "null", "-",
        ]
        return run_ffmpeg(cmd, capture=True)

    def _probe_error_summary(self, stderr: str) -> str:
        """Pulls out just the encoder's own diagnostic lines from a failed
        probe's stderr - e.g. "[h264_nvenc @ 0x...] Driver does not support
        the required nvenc API version." - instead of the generic filter-graph
        teardown noise ("Terminating thread with error: ...", "Nothing was
        written...") that surrounds it and says nothing about the actual
        cause. Falls back to the last couple of lines if nothing matches."""
        tag = f"[{self.system_config.resolve_gpu_codec()} @ "
        matches = [ln.strip() for ln in stderr.splitlines() if ln.strip().startswith(tag)]
        if matches:
            return " / ".join(m.split("]", 1)[1].strip() for m in matches)
        return " / ".join(stderr.strip().splitlines()[-2:]) or "unknown error"

    def _find_system_ffmpeg(self) -> str | None:
        """The first `ffmpeg` on PATH that ISN'T remanga's own isolated bin/ffmpeg -
        run.sh prepends bin/ to PATH, so a plain shutil.which("ffmpeg") always
        resolves to that one first. Returns whatever the OS/package manager
        already has installed, if anything - used as a fallback GPU-encoding
        path only (see _resolve_gpu_ffmpeg); every other ffmpeg call in the
        pipeline keeps using the isolated binary, so this doesn't compromise
        the "leaves zero footprint" guarantee - nothing is installed, only an
        already-present system binary is optionally read from."""
        isolated_dir = str(BIN_DIR.resolve())
        for path_dir in os.environ.get("PATH", "").split(os.pathsep):
            if not path_dir or str(Path(path_dir).resolve()) == isolated_dir:
                continue
            candidate = shutil.which("ffmpeg", path=path_dir)
            if candidate:
                return candidate
        return None

    def _resolve_gpu_ffmpeg(self) -> tuple[str | None, str]:
        """Finds an ffmpeg binary whose GPU encoder actually works against the
        driver installed on THIS machine right now, and returns (path, note) -
        note explains why the bundled binary was skipped, if it was, for the
        console message in render_video(); path is None if nothing worked.

        Why the bundled bin/ffmpeg can fail NVENC even with a real, working
        NVIDIA GPU: bootstrap.sh downloads whatever the latest BtbN/FFmpeg-
        Builds master snapshot is, built against whatever NVIDIA NVENC SDK
        version was current that day. NVENC's minimum required driver version
        only ever goes up over time, so a bundled build newer than your last
        driver update can require an NVENC API version your installed driver
        doesn't support yet ("Driver does not support the required nvenc API
        version") - a real environment mismatch, not a bug in this check. A
        distro-packaged system ffmpeg is typically built against far more
        conservative headers and often still works fine on the same driver,
        so it's tried next before giving up on GPU encoding entirely.
        """
        if not self.system_config.prefer_gpu:
            return None, ""

        bundled = shutil.which("ffmpeg")
        if bundled:
            res = self._probe_nvenc(bundled)
            if res.returncode == 0:
                return bundled, ""
            bundled_error = self._probe_error_summary(res.stderr or "")
        else:
            bundled_error = "bundled ffmpeg not found on PATH"

        system_ffmpeg = self._find_system_ffmpeg()
        if system_ffmpeg:
            res = self._probe_nvenc(system_ffmpeg)
            if res.returncode == 0:
                note = (
                    f"the bundled ffmpeg's {self.system_config.resolve_gpu_codec()} didn't work here "
                    f"({bundled_error}) - using the system ffmpeg ({system_ffmpeg}) instead, which does"
                )
                return system_ffmpeg, note

        return None, f"falling back to CPU - {self.system_config.resolve_gpu_codec()} didn't work: {bundled_error}"

    def encoder(self) -> tuple[str, str, bool, str]:
        """(ffmpeg binary, codec, is-GPU, note) - probed once per renderer.
        A full recap asks for every chapter, and the answer shouldn't change
        mid-run anyway: pictures from two different encoders can't be
        stream-copied into one join."""
        if self._encoder_choice is None:
            gpu_ffmpeg, note = self._resolve_gpu_ffmpeg()
            use_gpu = gpu_ffmpeg is not None
            codec = self.system_config.resolve_gpu_codec() if use_gpu else self.system_config.fallback_codec
            self._encoder_choice = (gpu_ffmpeg or "ffmpeg", codec, use_gpu, note)
        return self._encoder_choice
