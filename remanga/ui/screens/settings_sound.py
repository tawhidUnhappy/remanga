"""The settings screen's Sound rows - the volume, the music, how loud the
music plays and the pause between its plays - and how each changes the
config. The screen itself is settings.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.ui.dialogs import Ask, Choice, number_check

if TYPE_CHECKING:
    from remanga.ui.screens.settings import SettingsScreen


MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")


MUSIC_LEVELS = ((14.0, "balanced - music clearly part of it"), (18.0, "subtle - a quiet bed, recommended"),
                (20.0, "barely there - adds a mood, never in the way"))


# Reference points for typing a level, loudest music first.
MUSIC_LADDER = ((8.0, "loud - fights the words, hard to follow"), (12.0, "energetic - clearly felt"),
                (14.0, "balanced - clearly part of it"), (18.0, "subtle - a quiet bed, recommended"),
                (20.0, "barely there - adds a mood, never in the way"), (24.0, "almost silent - lost on a phone"))


async def change_music(screen: SettingsScreen, config: RemangaConfig) -> None:
    folder = GLOBAL_DIR / "bgm"
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXTS) if folder.exists() else []
    current = config.audio.bgm_path if config.audio.bgm_enabled else "off"
    picked = await screen.app.push_screen_wait(Choice(
        "Background music", [("No music", "", "off")] + [(p.name, "", str(p)) for p in files],
        current=current, note=f"Put music files in {folder}/"))
    if picked == "off":
        config.audio.bgm_enabled = False
    elif picked:
        config.audio.bgm_path, config.audio.bgm_enabled = picked, True


def music_guide(current: float) -> str:
    """What a music level number means, in plain words, with the level in use marked."""
    lines = ["The number is how much QUIETER the music's loud parts are than the narrator's",
             "voice, in loudness units (LU, the same scale as dB). Bigger number = quieter music.", ""]
    for lu, text in MUSIC_LADDER:
        lines.append(f"  {lu:>4g}   {text}{'   <- now' if abs(lu - current) < 1e-9 else ''}")
    if all(abs(lu - current) > 1e-9 for lu, _ in MUSIC_LADDER):
        lines.append(f"  {current:>4g}   <- now")
    lines += ["", "About 10 LU more sounds half as loud. Every song is measured by its loud parts,",
              "so the same number holds whichever music file is chosen - a loud chorus included."]
    return "\n".join(lines)


async def change_music_level(screen: SettingsScreen, config: RemangaConfig) -> None:
    audio = config.audio
    options = [(f"{lu:g} LU quieter than the voice", hint, lu) for lu, hint in MUSIC_LEVELS]
    # A level typed in before is kept and offered again, beside the presets.
    custom = audio.bgm_custom_lu
    if custom is not None and all(custom != lu for lu, _ in MUSIC_LEVELS):
        options.append((f"{custom:g} LU quieter than the voice", "your custom level", custom))
    options.append(("Custom...", "type your own number - it's saved for next time", "custom"))
    level = await screen.app.push_screen_wait(Choice(
        "Music volume", options, current=audio.bgm_below_voice_lu,
        note="How much quieter the music plays than the narrator. Bigger number = quieter music."))
    if level == "custom":
        typed = await screen.app.push_screen_wait(Ask(
            "Music volume", "How much quieter than the voice? (a number from 3 to 30)",
            value=f"{custom if custom is not None else audio.bgm_below_voice_lu:g}",
            check=number_check(3, 30), note=music_guide(audio.bgm_below_voice_lu)))
        if typed is None:
            return
        level = audio.bgm_custom_lu = float(typed)
    if level is not None:
        audio.bgm_below_voice_lu = level


LOOP_GAPS = ((0.0, "none - the end crossfades straight into the start"), (1.0, "a short breath"),
             (2.0, "a natural pause, recommended"), (4.0, "a clear rest, like a playlist"))


def loop_gap_label(seconds: float) -> str:
    return f"{seconds:g} s pause between plays" if seconds > 0 else "no pause (crossfade)"


async def change_loop_gap(screen: SettingsScreen, config: RemangaConfig) -> None:
    audio = config.audio
    options = [(loop_gap_label(s), hint, s) for s, hint in LOOP_GAPS]
    if all(audio.bgm_loop_gap_s != s for s, _ in LOOP_GAPS):
        options.append((loop_gap_label(audio.bgm_loop_gap_s), "your custom pause", audio.bgm_loop_gap_s))
    options.append(("Custom...", "type your own number of seconds", "custom"))
    note = ("When a chapter is longer than the song, the song plays again. With a pause, it fades out, "
            "goes quiet for this long, then starts again from its beginning. Changing it re-mixes the "
            "chapter; nothing is narrated again.")
    picked = await screen.app.push_screen_wait(Choice("Music loop pause", options,
                                                      current=audio.bgm_loop_gap_s, note=note))
    if picked == "custom":
        picked = await screen.app.push_screen_wait(Ask(
            "Music loop pause", "Seconds of quiet between plays (0 to 10)", value=f"{audio.bgm_loop_gap_s:g}",
            check=number_check(0, 10), note=note))
    if picked is not None:
        audio.bgm_loop_gap_s = float(picked)


VOLUMES = ((-14.0, "YouTube's level - recommended"), (-16.0, "a little quieter - podcasts, Apple"),
           (-13.0, "a little louder - TikTok and Shorts"))


async def change_volume(screen: SettingsScreen, config: RemangaConfig) -> None:
    audio = config.audio
    options = [(f"{lufs:g} LUFS", hint, lufs) for lufs, hint in VOLUMES]
    if all(audio.volume_lufs != lufs for lufs, _ in VOLUMES):
        options.append((f"{audio.volume_lufs:g} LUFS", "your custom level", audio.volume_lufs))
    options.append(("Custom...", "type your own LUFS", "custom"))
    note = ("How loud the finished chapter is: measured, then one gain for the whole track, so the voice "
            "itself is not changed. Closer to 0 is louder. Changing it re-mixes the chapter; nothing is "
            "narrated again.")
    picked = await screen.app.push_screen_wait(Choice("Volume", options, current=audio.volume_lufs, note=note))
    if picked == "custom":
        picked = await screen.app.push_screen_wait(Ask(
            "Volume", "Loudness in LUFS (-30 to -8)", value=f"{audio.volume_lufs:g}",
            check=number_check(-30, -8), note=note))
    if picked is not None:
        audio.volume_lufs = float(picked)
