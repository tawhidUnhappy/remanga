"""The settings that change how a recap sounds and looks, rather than what
it is made of.

These all existed already - as fields in config.json that only a text editor
could reach. That is a poor place for them, because they are exactly the
settings whose right value is found by listening to a chapter and adjusting:
narration pace, the gap between panels, how loud the voice sits over the
music. A knob you have to hand-edit JSON to turn is a knob nobody turns.

Grouped by the question being asked rather than by which config block the
answer happens to live in - "pacing" spans tts and audio, "levels" spans the
engine's own gain and the music's, and a user thinking "the narration is too
fast" should not have to know which of those it is. Levels is a menu of its
own rather than a walkthrough, so it lives in levels.py."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.field_prompts import ask_field_number
from remanga.settings.fields import set_field
from remanga.tui import confirm, is_cancel


def configure_pacing(config: RemangaConfig) -> None:
    """How fast the narration reads, and how long a panel is held after it.

    Both together because they are the same question in practice: a recap
    that feels rushed is fixed by either, and which one is right depends on
    whether the words or the gaps are what feels wrong."""
    if not ask_field_number(config, "tts.speed", "Narration speed (1.0 = the voice's natural pace)",
                            minimum=0.5, maximum=2.0,
                            note="Kokoro applies it in the model; Chatterbox has no rate control, "
                                 "so its clips are time-stretched instead"):
        return
    if not ask_field_number(config, "audio.pause_between_panels_ms", "Pause between panels, in milliseconds",
                            minimum=0, maximum=5000, integer=True,
                            note="silence held after each panel's narration before the next begins"):
        return
    console.print(
        f"[green]✓ Pacing:[/] {config.tts.speed}x speed, "
        f"{config.audio.pause_between_panels_ms}ms between panels"
    )


def configure_panel_detection(config: RemangaConfig) -> None:
    """What happens to a page between downloading it and narrating it.

    Every one of these is a cleanup pass that is normally right and
    occasionally wrong on an unusual layout - a splash page, a spread, art
    that bleeds to the edge. Being able to turn one off without editing JSON
    is the difference between diagnosing a bad crop in a minute and giving up
    on the chapter."""
    magi = confirm("Use MAGI v3 to detect panels automatically?",
                   default=config.marker.magi_enabled)
    if is_cancel(magi):
        return
    set_field(config, "marker.magi_enabled", bool(magi))

    snap = confirm("Snap panel edges to the page's gutters?", default=config.cropper.snap_to_gutters)
    if is_cancel(snap):
        return
    set_field(config, "cropper.snap_to_gutters", bool(snap))

    trim = confirm("Trim leftover blank margin off each panel?",
                   default=config.cropper.trim_panel_whitespace)
    if is_cancel(trim):
        return
    set_field(config, "cropper.trim_panel_whitespace", bool(trim))

    dedupe = confirm("Drop duplicate panels?", default=config.cropper.dedupe_duplicate_panels)
    if is_cancel(dedupe):
        return
    set_field(config, "cropper.dedupe_duplicate_panels", bool(dedupe))

    on = [name for name, flag in (
        ("MAGI", config.marker.magi_enabled), ("gutter-snap", config.cropper.snap_to_gutters),
        ("trim", config.cropper.trim_panel_whitespace),
        ("dedupe", config.cropper.dedupe_duplicate_panels),
    ) if flag]
    console.print(f"[green]✓ Panel detection:[/] {', '.join(on) if on else 'all passes off'}")


def configure_framing(config: RemangaConfig) -> None:
    """How each panel sits inside the video frame."""
    if not ask_field_number(config, "video.panel_padding_percent", "Padding around each panel, in percent",
                            minimum=0.0, maximum=45.0,
                            note="space left between the panel and the edge of the frame"):
        return
    adaptive = confirm("Adapt that padding to each panel's shape?",
                       default=config.video.auto_adaptive_padding)
    if is_cancel(adaptive):
        return
    set_field(config, "video.auto_adaptive_padding", bool(adaptive))

    if not ask_field_number(config, "video.blur_brightness", "Bokeh background brightness",
                            minimum=0.0, maximum=2.0,
                            note="only used when the canvas background is the blurred panel"):
        return
    if not ask_field_number(config, "video.panel_border_width", "Panel border width, in pixels (0 = none)",
                            minimum=0, maximum=64, integer=True):
        return
    console.print(
        f"[green]✓ Framing:[/] {config.video.panel_padding_percent:g}% padding"
        f"{' (adaptive)' if config.video.auto_adaptive_padding else ''}, "
        f"{config.video.panel_border_width}px border"
    )
