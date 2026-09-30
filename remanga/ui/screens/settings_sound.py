"""The settings screen's Narration and Sound rows: what each offers and how it
changes the config. The screen itself is settings.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remanga.config import RemangaConfig
from remanga.paths import GLOBAL_DIR
from remanga.ui.dialogs import Ask, Choice, number_check

if TYPE_CHECKING:
    from remanga.ui.screens.settings import SettingsScreen


MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")


EDGE_FADES = ((0, "off - clips start and stop at the sample"),
              (15, "barely there - just enough to stop a click"),
              (35, "recommended"),
              (80, "softer - the end of each line eases out"),
              (150, "soft - noticeable on a line that ends abruptly"))


PANEL_GAPS = ((0, "continuous - recommended; the trimmed margins still leave about 50 ms"),
              (120, "a beat between panels"),
              (250, "a breath between panels"),
              (350, "unhurried"),
              (600, "slow, with room to look at the panel"))


MUSIC_LEVELS = ((12.0, "energetic - music clearly felt"), (14.0, "balanced - recommended"),
                (18.0, "subtle - a quiet bed"))


# Reference points for typing a level, loudest music first.
MUSIC_LADDER = ((8.0, "loud - fights the words, hard to follow"), (12.0, "energetic - clearly felt"),
                (14.0, "balanced - recommended"), (18.0, "subtle - a quiet bed"),
                (24.0, "barely there - felt more than heard"))


# How much of a chapter the narrator reads in one go. 0 is a take per panel;
# anything else is that many minutes of narration read straight through. One
# row rather than a switch and a number, because "off" is just the shortest
# take there is.
NARRATION_TAKES = ((0.0, "one take per panel - the voice restarts at every panel"),
                   (0.5, "about 30 seconds - closest to a cloned voice, most restarts"),
                   (1.0, "about a minute - one voice all through, and still the reference's"))


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
    lines = ["The number is how much QUIETER the music is than the narrator's voice,",
             "in loudness units (LU, the same scale as dB). Bigger number = quieter music.", ""]
    for lu, text in MUSIC_LADDER:
        lines.append(f"  {lu:>4g}   {text}{'   <- now' if abs(lu - current) < 1e-9 else ''}")
    if all(abs(lu - current) > 1e-9 for lu, _ in MUSIC_LADDER):
        lines.append(f"  {current:>4g}   <- now")
    lines += ["", "About 10 LU more sounds half as loud. Every song is measured, so the same",
              "number sits at the same level whichever music file is chosen."]
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
        "Music level", options, current=audio.bgm_below_voice_lu,
        note="How much quieter the music plays than the narrator. Bigger number = quieter music."))
    if level == "custom":
        typed = await screen.app.push_screen_wait(Ask(
            "Music level", "How much quieter than the voice? (a number from 3 to 30)",
            value=f"{custom if custom is not None else audio.bgm_below_voice_lu:g}",
            check=number_check(3, 30), note=music_guide(audio.bgm_below_voice_lu)))
        if typed is None:
            return
        level = audio.bgm_custom_lu = float(typed)
    if level is not None:
        audio.bgm_below_voice_lu = level


async def change_panel_gap(screen: SettingsScreen, config: RemangaConfig) -> None:
    gap = await screen.app.push_screen_wait(Choice(
        "Pause between panels", [(f"{ms} ms" if ms else "continuous", hint, ms) for ms, hint in PANEL_GAPS],
        current=config.audio.pause_between_panels_ms,
        note="The silence between one panel's narration and the next, and now the whole of it: the "
             "uneven lead-in the narrator leaves on each clip is trimmed back to an even margin, so "
             "this is the gap you actually hear. Changing it lays the chapter out again from the "
             "clips already on disk - nothing is narrated again, but the chapter is mixed and "
             "rendered again."))
    if gap is not None:
        config.audio.pause_between_panels_ms = gap


async def change_edge_fade(screen: SettingsScreen, config: RemangaConfig) -> None:
    fade = await screen.app.push_screen_wait(Choice(
        "Fade at line edges", [(f"{ms} ms" if ms else "off", hint, ms) for ms, hint in EDGE_FADES],
        current=config.audio.edge_fade_ms,
        note="How each panel's clip starts and stops. The start is only ever faded over the silence "
             "the clip already has, so the first word is never ramped; the end may ease out through "
             "the last of the speech, which is what stops a line sounding cut off. Changing this "
             "re-mixes the chapter - it does not narrate it again."))
    if fade is not None:
        config.audio.edge_fade_ms = fade


async def change_narration_takes(screen: SettingsScreen, config: RemangaConfig) -> None:
    current = config.audio.batch_target_minutes if config.audio.batch_narration else 0.0
    minutes = await screen.app.push_screen_wait(Choice(
        "Narration take length",
        [(f"about {m:g} min" if m else "one per panel", hint, m) for m, hint in NARRATION_TAKES],
        current=current,
        note="How much of the chapter the narrator reads without stopping. A panel read on its own "
             "is a performance of its own, so the tone resets at every panel - reading straight "
             "through a scene is what keeps one voice across it. Where each panel falls inside a "
             "take is found by listening to it afterwards, so the pictures are still cut to the "
             "words. Longer is not better past a point: a cloned voice holds its reference for "
             "about a minute and then drifts off it, measurably, and asked for nine minutes at "
             "once the narrator lost the thread entirely. A minute is the most that has held "
             "both the thread and the voice."))
    if minutes is not None:
        config.audio.batch_narration = minutes > 0
        if minutes > 0:
            config.audio.batch_target_minutes = minutes
