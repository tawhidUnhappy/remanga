"""What this machine actually is, and which wheels match it.

bootstrap.sh used to install the same things everywhere: a Linux-x86_64
static ffmpeg, whatever `uv pip install torch` resolved to, and an
unconditional attempt at building CUDA kernels. That works on exactly one
kind of machine - an x86_64 Linux box with a recent NVIDIA card - and on
anything else it either wastes a 2.5GB CUDA download on a laptop that can
never use it, or fails outright.

This module is the single place that answers "what is this machine, and
what should therefore be installed on it". It is deliberately:

  * stdlib only, so it runs under a bare interpreter before any environment
    has been provisioned - which is exactly when bootstrap.sh needs it;
  * side-effect free - it detects and reports, it never installs;
  * importable AND runnable (`python -m remanga.hardware --shell`), so the
    shell script and the application agree on one answer rather than each
    sniffing the hardware their own way.

The PyTorch wheel index is the part worth being careful about, because the
obvious mapping is wrong. PyTorch publishes a separate index per compute
backend, and they do NOT all carry the same torch versions. IndexTTS-2.5
pins `torch==2.8.*`, and as of this writing:

    cu126, cu128, cu129   have 2.8   <- usable
    rocm6.4               has  2.8   <- usable
    cpu                   has  2.8   <- usable
    cu118                 stops at 2.7   <- would fail to resolve
    cu130                 starts at 2.9  <- would fail to resolve

So "pick the newest CUDA index" is wrong (the newest has no 2.8) and so is
"pick whatever the driver supports" (an old driver's only option, cu118,
has no 2.8 either). The rule that is right is "the newest index that both
the driver can run AND still carries 2.8" - see _CUDA_INDEX_BY_DRIVER.

Driver requirements come from CUDA's own compatibility rules: a CUDA 13.x
runtime needs a 580+ driver, while any CUDA 12.x runtime runs on 525+
(Linux) / 528+ (Windows) thanks to minor-version compatibility, and newer
drivers stay backward compatible. Below the CUDA 12 floor there is no
honest answer for this project, so we say so and install CPU builds rather
than something that would install and then fail at the first kernel.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

# CUDA wheel index by minimum NVIDIA driver, newest first. Two constraints
# meet here and both matter:
#
#   * the driver floor - a CUDA 13.x runtime needs a 580+ driver, while any
#     CUDA 12.x runtime runs on 525+ (Linux) thanks to minor-version
#     compatibility, and newer drivers stay backward compatible;
#   * torch 2.8 has to exist in whichever index is chosen, because
#     IndexTTS-2.5 pins it - which is what rules out cu130 (starts at 2.9)
#     even on a machine whose driver could run it, and cu118 (stops at 2.7)
#     on machines that could run nothing else.
#
# So this stops at cu129 rather than climbing to the newest CUDA available:
# cu129 is the newest index that still carries 2.8, and it also carries
# everything up to 2.13, so a modern machine is not held back by the pin.
_CUDA_INDEX_BY_DRIVER: tuple[tuple[int, str], ...] = (
    (580, "cu129"),
    (525, "cu128"),
)

# Same table for Windows, whose driver numbering for the CUDA 12.x floor is
# 528 rather than Linux's 525.
_CUDA_INDEX_BY_DRIVER_WINDOWS: tuple[tuple[int, str], ...] = (
    (580, "cu129"),
    (528, "cu128"),
)

# Oldest driver that can run any CUDA index above. Below this there is no
# honest CUDA answer for this project: the only index that would load is
# cu118, and it has no torch 2.8 - so CUDA 12 wheels would install and then
# fail at the first kernel launch, which is far worse than running on CPU.
MIN_CUDA_DRIVER_LINUX = 525
MIN_CUDA_DRIVER_WINDOWS = 528


# ROCm index to use when an AMD stack is detected. Same constraint as CUDA:
# this is the oldest ROCm index that still carries torch 2.8.
ROCM_INDEX = "rocm6.4"

_TORCH_INDEX_BASE = "https://download.pytorch.org/whl"

# Static ffmpeg builds, by (os, arch). BtbN publishes Linux and Windows
# only; macOS has no build here on purpose - see ffmpeg_plan().
_BTBN_ASSET = {
    ("linux", "x86_64"): "linux64",
    ("linux", "arm64"): "linuxarm64",
    ("windows", "x86_64"): "win64",
    ("windows", "arm64"): "winarm64",
}


@dataclass(frozen=True)
class Hardware:
    """One machine's answer to "what should be installed here"."""

    os: str                  # linux | macos | windows
    arch: str                # x86_64 | arm64
    accelerator: str         # cuda | rocm | mps | cpu
    device_name: str = ""
    driver_version: str = ""
    torch_backend: str = "cpu"        # cu128 | rocm6.4 | default | cpu
    video_encoder: str = "libx264"
    notes: list[str] = field(default_factory=list)

    @property
    def torch_index_url(self) -> str:
        """The `--index-url` to install torch from. "default" means plain
        PyPI, which is already the right wheel on macOS (where torch ships
        with Metal/MPS support built in and there is no separate index)."""
        if self.torch_backend == "default":
            return ""
        return f"{_TORCH_INDEX_BASE}/{self.torch_backend}"

    @property
    def has_cuda(self) -> bool:
        return self.accelerator == "cuda"

    def summary(self) -> str:
        gpu = self.device_name or self.accelerator.upper()
        backend = self.torch_backend if self.torch_backend != "default" else "pypi/default"
        return f"{self.os}/{self.arch}, {self.accelerator} ({gpu}), torch wheels: {backend}"


def _run(cmd: list[str], timeout: float = 10.0) -> str:
    """A command's stdout, or "" if it isn't installed / fails / hangs.
    Never raises: every probe here is optional by definition."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _normalize_os() -> str:
    system = platform.system().lower()
    if system == "darwin":
        return "macos"
    if system.startswith("win") or system == "cygwin":
        return "windows"
    return "linux" if system == "linux" else system


def _normalize_arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64", "x64"):
        return "x86_64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    return machine


def _detect_nvidia() -> tuple[str, str]:
    """(device name, driver version) from nvidia-smi, or ("", "").

    nvidia-smi rather than importing torch: this has to work before any
    environment with torch in it exists, which is the whole point."""
    if not shutil.which("nvidia-smi"):
        return "", ""
    out = _run(["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"])
    if not out:
        return "", ""
    first = out.splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def _driver_major(driver_version: str) -> int:
    match = re.match(r"(\d+)", driver_version or "")
    return int(match.group(1)) if match else 0


def cuda_index_for(driver_version: str, host_os: str = "linux") -> str:
    """The newest torch-2.8-carrying CUDA index this driver can run, or ""
    if the driver is too old for any of them."""
    table = _CUDA_INDEX_BY_DRIVER_WINDOWS if host_os == "windows" else _CUDA_INDEX_BY_DRIVER
    major = _driver_major(driver_version)
    for minimum, index in table:
        if major >= minimum:
            return index
    return ""


def _detect_rocm() -> str:
    """AMD GPU name if a ROCm stack is present, else ""."""
    if shutil.which("rocminfo"):
        out = _run(["rocminfo"])
        for line in out.splitlines():
            if "Marketing Name" in line and "CPU" not in line:
                name = line.split(":", 1)[-1].strip()
                if name:
                    return name
        if out:
            return "AMD GPU"
    if Path("/opt/rocm").is_dir():
        return "AMD GPU"
    return ""


def detect(override: str | None = None) -> Hardware:
    """What to install on this machine.

    `override` (or REMANGA_TORCH_BACKEND) forces the torch backend when the
    detection is wrong or a user wants something specific - "cpu" to skip a
    2.5GB CUDA download on a machine whose GPU they don't intend to use,
    "cu126"/"cu129"/"rocm6.3" to pin a different index. Detection is a
    default, never a straitjacket."""
    host_os, arch = _normalize_os(), _normalize_arch()
    notes: list[str] = []
    override = (override or os.environ.get("REMANGA_TORCH_BACKEND") or "").strip()

    # --- macOS: Metal on Apple Silicon, CPU on Intel. Either way the plain
    # PyPI wheel is the correct one; there is no per-backend index for Mac.
    if host_os == "macos":
        apple_silicon = arch == "arm64"
        hw = Hardware(
            os=host_os, arch=arch,
            accelerator="mps" if apple_silicon else "cpu",
            device_name="Apple Silicon (Metal)" if apple_silicon else "Intel Mac",
            torch_backend="default",
            video_encoder="h264_videotoolbox",
            notes=notes,
        )
        if not apple_silicon:
            notes.append("Intel Mac: no GPU acceleration for the ML models; synthesis will be slow.")
        return _apply_override(hw, override)

    # --- NVIDIA, if a driver is actually present.
    name, driver = _detect_nvidia()
    if name:
        minimum = MIN_CUDA_DRIVER_WINDOWS if host_os == "windows" else MIN_CUDA_DRIVER_LINUX
        index = cuda_index_for(driver, host_os)
        if index:
            return _apply_override(Hardware(
                os=host_os, arch=arch, accelerator="cuda", device_name=name,
                driver_version=driver, torch_backend=index,
                video_encoder="h264_nvenc", notes=notes,
            ), override)
        notes.append(
            f"NVIDIA driver {driver or 'unknown'} is older than {minimum}, the minimum for the CUDA 12.x "
            f"wheels this project needs (IndexTTS pins torch 2.8, which no CUDA 11 index carries). "
            f"Installing CPU builds for the ML models - update the driver and re-run bootstrap.sh for GPU speed."
        )
        # Still h264_nvenc, not libx264: video encoding runs on the card's
        # separate NVENC block and has nothing to do with which torch wheel
        # the ML models use, so an old driver that rules out CUDA 12 often
        # still encodes video fine. video/render.py probes the encoder for
        # real before each render and falls back to CPU on its own, so
        # naming it here costs nothing and keeps GPU rendering available on
        # a machine that can't do GPU inference.
        return _apply_override(Hardware(
            os=host_os, arch=arch, accelerator="cpu", device_name=name,
            driver_version=driver, torch_backend="cpu", video_encoder="h264_nvenc", notes=notes,
        ), override)

    # --- AMD ROCm (Linux only; there are no ROCm wheels for Windows).
    if host_os == "linux":
        amd = _detect_rocm()
        if amd:
            return _apply_override(Hardware(
                os=host_os, arch=arch, accelerator="rocm", device_name=amd,
                torch_backend=ROCM_INDEX, video_encoder="h264_vaapi", notes=notes,
            ), override)

    # --- Nothing to accelerate with.
    notes.append("No supported GPU detected - installing CPU-only builds (much smaller, much slower).")
    return _apply_override(Hardware(
        os=host_os, arch=arch, accelerator="cpu", torch_backend="cpu",
        video_encoder="libx264", notes=notes,
    ), override)


@lru_cache(maxsize=4)
def detect_cached(override: str | None = None) -> Hardware:
    """`detect`, memoized. Detection shells out to nvidia-smi/rocminfo, which
    is far too slow to repeat per rendered chapter - and the answer cannot
    change inside one process anyway. Anything on a hot path (the video
    encoder lookup, most obviously) should come through here."""
    return detect(override)


def _apply_override(hw: Hardware, override: str) -> Hardware:
    if not override or override in ("auto", hw.torch_backend):
        return hw
    hw.notes.append(f"torch backend forced to {override!r} (REMANGA_TORCH_BACKEND); detected {hw.torch_backend!r}.")
    accelerator = hw.accelerator
    if override == "cpu":
        accelerator = "cpu"
    elif override.startswith("cu"):
        accelerator = "cuda"
    elif override.startswith("rocm"):
        accelerator = "rocm"
    return Hardware(
        os=hw.os, arch=hw.arch, accelerator=accelerator, device_name=hw.device_name,
        driver_version=hw.driver_version, torch_backend=override,
        video_encoder=hw.video_encoder, notes=hw.notes,
    )


def ffmpeg_plan(hw: Hardware) -> dict[str, str]:
    """How to get an ffmpeg on this machine.

    `kind` is "btbn" when there's a static build to download (Linux and
    Windows, x86_64 and arm64), or "system" when there isn't - macOS, and
    any architecture BtbN doesn't publish. "system" is not a failure: the
    bootstrap falls back to whatever ffmpeg is on PATH, which on a Mac is
    the normal way to have one."""
    asset = _BTBN_ASSET.get((hw.os, hw.arch))
    if not asset:
        return {"kind": "system", "asset": "", "archive": ""}
    return {
        "kind": "btbn",
        "asset": asset,
        "archive": "zip" if hw.os == "windows" else "tar.xz",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect this machine's accelerator and matching wheels.")
    parser.add_argument("--shell", action="store_true", help="emit KEY=value lines for `eval` in bootstrap.sh")
    parser.add_argument("--backend", default=None, help="force a torch backend (cpu, cu128, rocm6.4, ...)")
    args = parser.parse_args()

    hw = detect(args.backend)
    plan = ffmpeg_plan(hw)
    if not args.shell:
        print(json.dumps({**asdict(hw), "torch_index_url": hw.torch_index_url, "ffmpeg": plan}, indent=2))
        return

    def emit(key: str, value: object) -> None:
        print(f"{key}={json.dumps(str(value))}")

    emit("REMANGA_OS", hw.os)
    emit("REMANGA_ARCH", hw.arch)
    emit("REMANGA_ACCEL", hw.accelerator)
    emit("REMANGA_DEVICE", hw.device_name)
    emit("REMANGA_DRIVER", hw.driver_version)
    emit("REMANGA_TORCH_BACKEND", hw.torch_backend)
    emit("REMANGA_TORCH_INDEX", hw.torch_index_url)
    emit("REMANGA_VIDEO_ENCODER", hw.video_encoder)
    emit("REMANGA_FFMPEG_KIND", plan["kind"])
    emit("REMANGA_FFMPEG_ASSET", plan["asset"])
    emit("REMANGA_FFMPEG_ARCHIVE", plan["archive"])
    emit("REMANGA_SUMMARY", hw.summary())
    emit("REMANGA_NOTES", " | ".join(hw.notes))


if __name__ == "__main__":
    main()
