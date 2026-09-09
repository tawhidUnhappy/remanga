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

from remanga.audio.leveling import read_levels
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


def _correct_music_level(config: RemangaConfig) -> None:
    """Measures both sides and writes the gain that separates them properly.

    Reports what it measured and what it changed, rather than just applying
    it: the number it writes is one a person may well want to nudge
    afterwards, and they can only do that if they know where it came from."""
    audio = config.audio
    # Captured before anything is written: `audio` is a live reference into
    # the config, so reading it after set_field would report the NEW value as
    # the old one - which is exactly the sort of quietly-wrong report this
    # function exists to replace.
    previous_gain_db = audio.bgm_volume_db
    reading = read_levels(
        audio.bgm_path, audio.sample_rate,
        audio.bgm_target_below_narration_db, previous_gain_db,
    )
    if reading is None:
        console.print(
            f"[yellow]Can't measure - background music file not readable:[/] "
            f"{audio.bgm_path or '(not set)'}"
        )
        return

    source = (
        f"{reading.clips_measured} synthesized clip(s)" if reading.clips_measured
        else "the typical level for this engine (nothing synthesized yet)"
    )
    console.print(
        f"[dim]Narration {reading.narration_lufs:.1f} LUFS, from {source}.\n"
        f"Music {reading.bgm_lufs:.1f} LUFS at its own level; "
        f"currently sitting {reading.current_separation_db:.1f} LU below the narration.[/]"
    )
    if reading.suggested_gain_db == previous_gain_db:
        console.print(
            f"[green]✓ Already correct:[/] {previous_gain_db:+.1f} dB gives the "
            f"{audio.bgm_target_below_narration_db:.0f} LU separation you asked for."
        )
        return

    set_field(config, "audio.bgm_volume_db", reading.suggested_gain_db)
    console.print(
        f"[bold green]✓ Music gain:[/] {reading.suggested_gain_db:+.1f} dB "
        f"[dim](was {previous_gain_db:+.1f}) - puts the bed "
        f"{audio.bgm_target_below_narration_db:.0f} LU under the narration.[/]"
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
    # An ACTION, not a mode: it measures, writes a plain number into
    # bgm_volume_db, and leaves. Nothing recomputes behind anyone's back at
    # mix time, and what ends up in config.json stays readable and editable.
    if confirm("Measure your narration and music, and correct the music level?",
               default=True):
        _correct_music_level(config)
    elif not _number(config, "audio.bgm_volume_db", "Background music gain, in dB",
                     minimum=-60.0, maximum=20.0,
                     note="relative to the music file's own loudness - a value tuned for one "
                          "track will not suit a different one"):
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
        f"music {config.audio.bgm_volume_db:+.1f}dB, "
        f"loudness normalization {'on' if config.audio.enable_loudnorm else 'off'}"
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
