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
fast" should not have to know which of those it is."""

from __future__ import annotations

from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.fields import set_field
from remanga.tui import ask_number, confirm, is_cancel


def _number(config: RemangaConfig, dotted: str, title: str, *, minimum: float,
            maximum: float, integer: bool = False, note: str = "") -> bool:
    """One numeric field, pre-filled with its current value. Returns False if
    the user backed out, so a screen asking several questions can stop at the
    first Esc instead of marching on through the rest."""
    current = config
    for part in dotted.split("."):
        current = getattr(current, part)
    value = ask_number(title, default=current, minimum=minimum, maximum=maximum,
                       integer=integer, note=note)
    if is_cancel(value):
        return False
    set_field(config, dotted, int(value) if integer else float(value))
    return True


def configure_pacing(config: RemangaConfig) -> None:
    """How fast the narration reads, and how long a panel is held after it.

    Both together because they are the same question in practice: a recap
    that feels rushed is fixed by either, and which one is right depends on
    whether the words or the gaps are what feels wrong."""
    if not _number(config, "tts.speed", "Narration speed (1.0 = the voice's natural pace)",
                   minimum=0.5, maximum=2.0,
                   note="applied by the model itself, not by stretching the audio afterwards"):
        return
    if not _number(config, "audio.pause_between_panels_ms", "Pause between panels, in milliseconds",
                   minimum=0, maximum=5000, integer=True,
                   note="silence held after each panel's narration before the next begins"):
        return
    console.print(
        f"[green]✓ Pacing:[/] {config.tts.speed}x speed, "
        f"{config.audio.pause_between_panels_ms}ms between panels"
    )


def configure_levels(config: RemangaConfig) -> None:
    """Voice-vs-music balance, and whether the master is normalized.

    Worth knowing while setting these: with loudness normalization on, the
    master is pulled to a fixed target afterwards, so raising the narration
    mostly pushes the MUSIC DOWN under it rather than making the file louder.
    That is usually what someone wants and almost never what they expect, so
    the screen says it."""
    if not _number(config, "tts.kokoro.volume_boost_db", "Narration gain, in dB (0 = untouched)",
                   minimum=-20.0, maximum=20.0,
                   note="baked into each panel's WAV as it is written; changing it does not "
                        "force a re-synthesis"):
        return
    if not _number(config, "audio.bgm_volume_db", "Background music gain, in dB",
                   minimum=-60.0, maximum=20.0,
                   note="negative sits the music under the narration"):
        return
    duck = confirm(
        "Duck the music under the narration (instead of one fixed level)?",
        default=config.audio.duck_music_under_narration,
    )
    if is_cancel(duck):
        return
    set_field(config, "audio.duck_music_under_narration", bool(duck))
    if duck:
        # Only asked when it is on: a depth and a ramp are meaningless
        # settings to be shown by a feature that is switched off.
        if not _number(config, "audio.duck_depth_db", "How far the music drops while speaking, in dB",
                       minimum=-30.0, maximum=0.0,
                       note="applied on top of the music gain above - with ducking on you can "
                            "usually afford to RAISE that, since the music now gets out of the way"):
            return
        if not _number(config, "audio.duck_fade_ms", "Ramp either side of a spoken passage, in ms",
                       minimum=0, maximum=2000, integer=True,
                       note="the dip starts this far before the first word and recovers this long "
                            "after the last"):
            return

    normalize = confirm(
        "Normalize the finished master to a fixed loudness (EBU R128)?",
        default=config.audio.enable_loudnorm,
    )
    if is_cancel(normalize):
        return
    set_field(config, "audio.enable_loudnorm", bool(normalize))
    console.print(
        f"[green]✓ Levels:[/] narration {config.tts.kokoro.volume_boost_db:+.1f}dB, "
        f"music {config.audio.bgm_volume_db:+.1f}dB"
        + (f" (ducking {config.audio.duck_depth_db:+.1f}dB under speech)"
           if config.audio.duck_music_under_narration else "")
        + f", loudness normalization {'on' if config.audio.enable_loudnorm else 'off'}"
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
    if not _number(config, "video.panel_padding_percent", "Padding around each panel, in percent",
                   minimum=0.0, maximum=45.0,
                   note="space left between the panel and the edge of the frame"):
        return
    adaptive = confirm("Adapt that padding to each panel's shape?",
                       default=config.video.auto_adaptive_padding)
    if is_cancel(adaptive):
        return
    set_field(config, "video.auto_adaptive_padding", bool(adaptive))

    if not _number(config, "video.blur_brightness", "Bokeh background brightness",
                   minimum=0.0, maximum=2.0,
                   note="only used when the canvas background is the blurred panel"):
        return
    if not _number(config, "video.panel_border_width", "Panel border width, in pixels (0 = none)",
                   minimum=0, maximum=64, integer=True):
        return
    console.print(
        f"[green]✓ Framing:[/] {config.video.panel_padding_percent:g}% padding"
        f"{' (adaptive)' if config.video.auto_adaptive_padding else ''}, "
        f"{config.video.panel_border_width}px border"
    )
