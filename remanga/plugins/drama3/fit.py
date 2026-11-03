"""Whether a machine can run Drama 3, and its recommended settings - asked the
first time remanga opens (ui/first_run.py)."""

from __future__ import annotations

from remanga.machine import Machine

# speech.cpp needs ~5.2 GB free on the GPU beside the experts it puts there
# (its docs/models/drama3.md), and the worker holds headroom on top while it
# loads (scripts/drama3_worker.py) - 8 GB is the smallest card that leaves
# room. The model is 20.8 GB, ~2 GB more of caches, and the system its own:
# the GPU's memory and the RAM together hold all of it.
MIN_VRAM_GB = 8.0
MIN_MEMORY_GB = 28.0
DOWNLOAD_GB = 22.0


def fits(machine: Machine) -> str | None:
    from remanga.config import RemangaConfig
    from remanga.plugins.drama3.synth import model_manager

    if not machine.gpu:
        return "needs a GPU (none found)"
    if not machine.vulkan:
        return "needs Vulkan - the GPU driver's Vulkan support is not installed"
    if machine.vram_gb < MIN_VRAM_GB:
        return f"needs a GPU with {MIN_VRAM_GB:.0f} GB+ (this one has {machine.vram_gb:.0f} GB)"
    if machine.vram_gb + machine.ram_gb < MIN_MEMORY_GB:
        return (f"needs the GPU's memory and the RAM to add up to {MIN_MEMORY_GB:.0f} GB+ "
                f"(here {machine.vram_gb + machine.ram_gb:.0f} GB)")
    downloaded = model_manager(RemangaConfig().tts.drama3).path.is_file()
    if not downloaded and machine.disk_free_gb < DOWNLOAD_GB:
        return f"needs {DOWNLOAD_GB:.0f} GB of free disk for its model ({machine.disk_free_gb:.0f} GB free)"
    return None


def recommend(config, machine: Machine) -> None:
    """The deep male narrator from a voice file - the same narrator every
    page (a chapter measured 91-103 Hz per page, against 79-123 in the
    model's own voice). GPU headroom as measured on a 12 GB card (2.5 GiB);
    a smaller card keeps less, a bigger one less again - those two are not
    measured."""
    drama = config.tts.drama3
    drama.voice, drama.seed, drama.voice_file = "deep_male", 1, True
    drama.gpu_headroom_gb = 1.5 if machine.vram_gb < 10 else 2.5 if machine.vram_gb < 16 else 2.0
