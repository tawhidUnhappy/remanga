"""The measured voice-vs-music balance: which separation to aim for, and the
music gain that gives it, worked out from the narration actually synthesized
and the music file itself.

An action the Audio levels screen offers (levels.py) - it writes a plain
number into config.json and leaves."""

from __future__ import annotations

from remanga.audio.clips import clamp_boost
from remanga.audio.leveling import BALANCE_PRESETS, PRESET_BY_SEPARATION, read_levels
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.settings.assets import ASSET_BY_KEY, edit_asset
from remanga.settings.fields import set_field
from remanga.settings.files import is_valid_file
from remanga.settings.presets import CUSTOM
from remanga.tui import Choice, ask_number, confirm, is_cancel, select


def voice_gain_field(config: RemangaConfig) -> str:
    """Dotted path of the ACTIVE engine's narration gain.

    Resolved through the engine's own spec rather than spelled "tts.kokoro."
    into a string, for the same reason TTSConfig.engine_block is: a second
    engine should not need this screen edited to reach its volume knob."""
    return f"tts.{config.tts.spec.config_attr}.volume_boost_db"


def voice_gain_db(config: RemangaConfig) -> float:
    """The active engine's narration gain, as the mixer would read it."""
    return clamp_boost(getattr(config.tts.engine_block, "volume_boost_db", 0.0))


def music_is_usable(config: RemangaConfig) -> bool:
    return bool(config.audio.bgm_enabled and is_valid_file(config.audio.bgm_path))


def ensure_music(config: RemangaConfig) -> bool:
    """Music on and pointing at a real file, asking for one if it isn't.

    Every action on this screen that touches the balance needs both sides to
    exist, and "nothing happened" is a poor answer to someone who just asked
    for their levels to be corrected."""
    if music_is_usable(config):
        return True
    console.print(
        "[yellow]There is no background music to balance against[/] "
        f"[dim]({'disabled' if not config.audio.bgm_enabled else 'file not found'}).[/]"
    )
    if not confirm("Choose a background music file now?", default=True):
        return False
    edit_asset(config, ASSET_BY_KEY["bgm"])
    return music_is_usable(config)


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
    if not ensure_music(config):
        return
    if not _pick_balance(config):
        return
    _correct_music_level(config)
