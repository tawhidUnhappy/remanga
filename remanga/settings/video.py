"""Video output settings: resolution, canvas background, and whether to
prefer the GPU encoder. Thin screens over remanga.settings.presets' tables -
each one pre-highlights what's configured now, so Enter alone always means
"leave it as it is"."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.fields import set_field
from remanga.settings.presets import CUSTOM, background_choices, resolution_choices
from remanga.tui import ask_number, confirm, is_cancel, select


def configure_resolution(config: RemangaConfig) -> None:
    picked = select("Video resolution", resolution_choices(config),
                    default=(config.video.width, config.video.height),
                    note=f"rendered at {config.video.fps}fps")
    if is_cancel(picked):
        return
    if picked == CUSTOM:
        width = int(ask_number("Width in pixels", default=config.video.width, minimum=16, maximum=15360, integer=True))
        height = int(ask_number("Height in pixels", default=config.video.height, minimum=16, maximum=8640, integer=True))
    else:
        width, height = picked
    set_field(config, "video.width", width, save=False)
    set_field(config, "video.height", height)
    console.print(f"[green]✓ Resolution:[/] {width}x{height}")


def configure_background(config: RemangaConfig) -> None:
    picked = select("Canvas background", background_choices(config),
                    default=config.video.background_style,
                    note=f"solid uses background_color {config.video.background_color}")
    if is_cancel(picked):
        return
    set_field(config, "video.background_style", picked)
    console.print(f"[green]✓ Background style:[/] {picked}")


def configure_hardware(config: RemangaConfig) -> None:
    """GPU preference only - the codec names themselves stay in config.json
    rather than being asked about, since they're an ffmpeg build detail
    (video/render.py falls back on its own when the GPU encoder isn't
    actually usable)."""
    prefer = confirm(
        "Prefer GPU hardware encoding?",
        default=config.system.prefer_gpu,
        note=f"{config.system.gpu_codec} when available, falling back to {config.system.fallback_codec}",
    )
    set_field(config, "system.prefer_gpu", prefer)
    console.print(f"[green]✓ GPU encoding:[/] {'preferred' if prefer else 'off (CPU only)'}")
