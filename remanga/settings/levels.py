"""The Audio levels screen: how loud the narration is, how loud the music sits
under it, and whether the finished master is normalized.

A menu of independent knobs where tuning.py's screens are walkthroughs -
configure_levels says why this one isn't. The measured auto-balance it offers
is balance.py."""

from __future__ import annotations

from remanga.audio.leveling import PRESET_BY_SEPARATION
from remanga.config import RemangaConfig
from remanga.console import console, display_path
from remanga.settings.assets import ASSET_BY_KEY, asset_status, edit_asset
from remanga.settings.balance import auto_balance, ensure_music, music_is_usable, voice_gain_db, voice_gain_field
from remanga.settings.field_prompts import ask_field_number
from remanga.settings.fields import set_field
from remanga.settings.files import is_valid_file
from remanga.tui import Choice, confirm, is_cancel, select


def _configure_voice_gain(config: RemangaConfig) -> None:
    if not ask_field_number(config, voice_gain_field(config), "Narration gain, in dB (0 = untouched)",
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
    if not ensure_music(config):
        return
    if not ask_field_number(config, "audio.bgm_volume_db", "Background music gain, in dB",
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
    music = f"music {audio.bgm_volume_db:+.1f}dB" if music_is_usable(config) else "no music"
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
    if music_is_usable(config):
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
