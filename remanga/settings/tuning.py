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

from remanga.audio.clips import clamp_boost
from remanga.audio.leveling import BALANCE_PRESETS, PRESET_BY_SEPARATION, read_levels
from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.settings.assets import ASSET_BY_KEY, asset_status, edit_asset
from remanga.settings.fields import set_field
from remanga.settings.files import is_valid_file
from remanga.settings.presets import CUSTOM
from remanga.tui import Choice, ask_number, confirm, is_cancel, select


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


def voice_gain_field(config: RemangaConfig) -> str:
    """Dotted path of the ACTIVE engine's narration gain.

    Resolved through the engine's own spec rather than spelled "tts.kokoro."
    into a string, for the same reason TTSConfig.engine_block is: a second
    engine should not need this screen edited to reach its volume knob."""
    return f"tts.{config.tts.spec.config_attr}.volume_boost_db"


def voice_gain_db(config: RemangaConfig) -> float:
    """The active engine's narration gain, as the mixer would read it."""
    return clamp_boost(getattr(config.tts.engine_block, "volume_boost_db", 0.0))


def _music_is_usable(config: RemangaConfig) -> bool:
    return bool(config.audio.bgm_enabled and is_valid_file(config.audio.bgm_path))


def _ensure_music(config: RemangaConfig) -> bool:
    """Music on and pointing at a real file, asking for one if it isn't.

    Every action on this screen that touches the balance needs both sides to
    exist, and "nothing happened" is a poor answer to someone who just asked
    for their levels to be corrected."""
    if _music_is_usable(config):
        return True
    console.print(
        "[yellow]There is no background music to balance against[/] "
        f"[dim]({'disabled' if not config.audio.bgm_enabled else 'file not found'}).[/]"
    )
    if not confirm("Choose a background music file now?", default=True):
        return False
    edit_asset(config, ASSET_BY_KEY["bgm"])
    return _music_is_usable(config)


def _pick_balance(config: RemangaConfig) -> bool:
    """Which separation to aim for. False if the user backed out.

    The presets are the point of this screen: the number that matters is a
    separation in LU, which is not a thing anyone has intuition about, so it
    is offered as what it sounds like instead - and the recap default is the
    first row."""
    current = float(config.audio.bgm_target_below_narration_db)
    rows = [
        Choice(label=preset.label, hint=f"{preset.separation_db:g} LU under the voice",
               detail=preset.note, value=preset.separation_db,
               badge="current" if preset.separation_db == current else "")
        for preset in BALANCE_PRESETS
    ]
    if current not in PRESET_BY_SEPARATION:
        rows.insert(0, Choice(label="Keep current target", hint=f"{current:g} LU under the voice",
                              value=current, badge="current"))
    rows.append(Choice(label="Custom…", hint="enter a separation in LU", value=CUSTOM))

    picked = select("How loud should the music be?", rows, default=current,
                    note="LU below the narration - a bigger number means quieter music")
    if is_cancel(picked):
        return False
    if picked == CUSTOM:
        value = ask_number("Music this far under the narration, in LU", default=current,
                           minimum=0.0, maximum=40.0,
                           note="15-20 is broadcast practice for music under dialogue; "
                                "below 15 it starts masking consonants")
        if is_cancel(value):
            return False
        picked = float(value)
    set_field(config, "audio.bgm_target_below_narration_db", float(picked))
    return True


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
    console.print("[dim]Measuring narration and music (ITU-R BS.1770 integrated loudness)...[/]")
    reading = read_levels(
        audio.bgm_path, audio.bgm_target_below_narration_db, previous_gain_db,
        narration_boost_db=voice_gain_db(config),
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


def auto_balance(config: RemangaConfig) -> None:
    """Pick a balance, then measure both sides and apply it.

    An ACTION, not a mode: it writes a plain number into bgm_volume_db and
    leaves. Nothing recomputes behind anyone's back at mix time, and what
    ends up in config.json stays readable and editable - which is the whole
    reason the mix does not just work this out on every run."""
    if not _ensure_music(config):
        return
    if not _pick_balance(config):
        return
    _correct_music_level(config)


def _configure_voice_gain(config: RemangaConfig) -> None:
    if not _number(config, voice_gain_field(config), "Narration gain, in dB (0 = untouched)",
                   minimum=-20.0, maximum=20.0,
                   note="baked into each panel's WAV as it is written; changing it does not "
                        "force a re-synthesis"):
        return
    console.print(f"[green]✓ Narration gain:[/] {voice_gain_db(config):+.1f} dB")


def _configure_music_gain(config: RemangaConfig) -> None:
    """The music level by hand, for someone who would rather set it by ear.

    Kept alongside the automatic balance rather than replaced by it: the
    measured figure is a starting point, and the last dB of "is the bed too
    present under this particular track" is a judgement nothing can measure."""
    if not _ensure_music(config):
        return
    if not _number(config, "audio.bgm_volume_db", "Background music gain, in dB",
                   minimum=-60.0, maximum=20.0,
                   note="relative to the music file's own loudness - a value tuned for one "
                        "track will not suit a different one"):
        return
    console.print(f"[green]✓ Music gain:[/] {config.audio.bgm_volume_db:+.1f} dB")


def _configure_music_source(config: RemangaConfig) -> None:
    """Background music on, off, or pointed at a different file.

    Three separate rows rather than a yes/no, because "off" and "a different
    track" are both things someone opens this row to do, and a confirm can
    only offer one of them - answering No to "turn it off?" should not drop
    anyone into a file picker they did not ask for."""
    audio = config.audio
    known = is_valid_file(audio.bgm_path)
    if audio.bgm_enabled:
        rows = [
            Choice(label="Choose a different file",
                   hint=display_path(known, wrap=False) if known else "none set yet",
                   value="pick"),
            Choice(label="Turn background music off",
                   hint="the narration is mixed on its own", value="off"),
        ]
    else:
        rows = [Choice(label="Choose a music file", hint="turns background music on",
                       value="pick")]
        # Off, but a usable file is still configured: turning it back on is
        # the likely intent, and re-picking the same file would be busywork.
        if known:
            rows.insert(0, Choice(label="Turn background music back on",
                                  hint=display_path(known, wrap=False), value="on"))

    picked = select("Background music", rows, back_label="Back",
                    note="the bed mixed under every panel of every chapter")
    if is_cancel(picked):
        return
    if picked == "pick":
        edit_asset(config, ASSET_BY_KEY["bgm"])
    elif picked == "on":
        set_field(config, "audio.bgm_enabled", True)
        console.print(f"[bold green]✓ Background music on:[/] {display_path(known)}")
    else:
        set_field(config, "audio.bgm_enabled", False)
        console.print("[yellow]Background music off.[/] [dim]The file is remembered, so "
                      "turning it back on is one keystroke.[/]")


def _configure_loudnorm(config: RemangaConfig) -> None:
    normalize = confirm(
        "Normalize the finished master to a fixed loudness (EBU R128)?",
        default=config.audio.enable_loudnorm,
        note="-16 LUFS, what streaming platforms expect; off leaves the mix at its own level",
    )
    set_field(config, "audio.enable_loudnorm", bool(normalize))
    console.print(
        f"[green]✓ Loudness normalization:[/] {'on' if config.audio.enable_loudnorm else 'off'}"
    )


def levels_summary(config: RemangaConfig) -> str:
    """The Audio levels row as the settings menu shows it, unopened.

    Music off is said as "no music" rather than as a gain, because a gain
    printed next to music nobody is mixing reads as the state of something
    that is not happening."""
    audio = config.audio
    music = f"music {audio.bgm_volume_db:+.1f}dB" if _music_is_usable(config) else "no music"
    return (f"voice {voice_gain_db(config):+.1f}dB · {music}"
            f" · {'normalized' if audio.enable_loudnorm else 'not normalized'}")


def _level_rows(config: RemangaConfig) -> list[Choice]:
    """The Audio levels screen, with every current value on its row."""
    audio = config.audio
    target = float(audio.bgm_target_below_narration_db)
    preset = PRESET_BY_SEPARATION.get(target)
    _ok, music_badge, music_description = asset_status(config, ASSET_BY_KEY["bgm"])

    rows = [
        Choice(label="Balance voice and music automatically",
               hint=preset.label.lower() if preset else f"{target:g} LU under the voice",
               detail="measures your narration and your music, then sets the music to sit "
                      "under it by the amount you pick",
               value="auto"),
        Choice(label="Narration volume", hint=f"{voice_gain_db(config):+.1f} dB",
               detail="gain baked into each panel's clip as it is synthesized",
               value="voice"),
    ]
    if _music_is_usable(config):
        rows.append(Choice(label="Background music volume", hint=f"{audio.bgm_volume_db:+.1f} dB",
                           detail="relative to the music file's own loudness",
                           value="music"))
    rows += [
        Choice(label="Background music", hint=music_description, badge=music_badge,
               detail="the bed mixed under every panel - choose a file, or turn it off",
               value="source"),
        Choice(label="Loudness normalization", hint="on" if audio.enable_loudnorm else "off",
               detail="pulls the finished master to a fixed -16 LUFS",
               value="loudnorm"),
    ]
    return rows


_LEVEL_ACTIONS = {
    "auto": auto_balance,
    "voice": _configure_voice_gain,
    "music": _configure_music_gain,
    "source": _configure_music_source,
    "loudnorm": _configure_loudnorm,
}


def configure_levels(config: RemangaConfig) -> None:
    """Voice-vs-music balance, as a menu rather than a fixed walkthrough.

    A menu because these are independent knobs, and the thing someone came
    here to change is rarely all of them: "the music is too loud" and
    "let me hear this without music" are different one-row answers, and
    asking every question in order to reach either is what made the old
    screen tedious enough to skip.

    Worth knowing while setting these, and why the screen says it: with
    loudness normalization on, the master is pulled to a fixed target
    afterwards, so raising the narration mostly pushes the MUSIC DOWN under
    it rather than making the file louder. That is usually what someone
    wants and almost never what they expect."""
    while True:
        picked = select(
            "Audio levels", _level_rows(config),
            note="with normalization on, raising the voice pushes the music down under it "
                 "rather than making the finished file louder",
            back_label="Back",
        )
        if is_cancel(picked):
            return
        _LEVEL_ACTIONS[picked](config)


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
