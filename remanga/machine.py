"""What this machine has, as far as a narrator engine cares: the GPU and its
memory, the RAM, the free disk, Vulkan, the internet. Read once when remanga
first opens, so it can offer only the engines this machine can run (each
engine's `fits` - plugins/_kinds.py:TTSEngine).

Separate from hardware.py, which bootstrap.sh runs as a bare script before
any environment exists and which only decides wheel indexes and encoders."""

from __future__ import annotations

import ctypes.util
import os
import shutil
import socket
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from remanga.paths import REPO_ROOT


@dataclass(frozen=True)
class Machine:
    gpu: str            # "" when there is no GPU this can read
    vram_gb: float      # the GPU's memory, 0 when unknown
    ram_gb: float
    disk_free_gb: float  # on the disk remanga (and its models) live on
    vulkan: bool        # the Vulkan loader and a driver for it are installed
    online: bool

    def describe(self) -> str:
        gpu = f"{self.gpu} ({self.vram_gb:.0f} GB)" if self.gpu else "no GPU found"
        return (f"{gpu}, {self.ram_gb:.0f} GB RAM, {self.disk_free_gb:.0f} GB free disk, "
                f"{'online' if self.online else 'offline'}")


def _nvidia() -> tuple[str, float]:
    if not shutil.which("nvidia-smi"):
        return "", 0.0
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=10).stdout.strip().splitlines()
    except (OSError, subprocess.SubprocessError):
        return "", 0.0
    if not out:
        return "", 0.0
    name, mib = (part.strip() for part in out[0].split(",", 1))
    try:
        return name, float(mib) / 1024
    except ValueError:
        return name, 0.0


def _ram_gb() -> float:
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9
    except (ValueError, OSError, AttributeError):
        return 0.0


def _vulkan() -> bool:
    """The loader, and at least one driver manifest for it."""
    if not ctypes.util.find_library("vulkan"):
        return False
    for folder in ("/usr/share/vulkan/icd.d", "/etc/vulkan/icd.d", "/usr/local/share/vulkan/icd.d"):
        if Path(folder).is_dir() and any(Path(folder).glob("*.json")):
            return True
    return False


def _online(timeout: float = 3.0) -> bool:
    for host in ("huggingface.co", "speech.platform.bing.com"):
        try:
            with socket.create_connection((host, 443), timeout=timeout):
                return True
        except OSError:
            continue
    return False


@lru_cache(maxsize=1)
def detect() -> Machine:
    gpu, vram = _nvidia()
    return Machine(gpu=gpu, vram_gb=vram, ram_gb=_ram_gb(),
                   disk_free_gb=shutil.disk_usage(REPO_ROOT).free / 1e9,
                   vulkan=_vulkan(), online=_online())
