"""The settings screen's Narration and Sound rows: what each offers and how it
changes the config. The screen itself is settings.py."""

from __future__ import annotations

from typing import TYPE_CHECKING

from remanga.audio.voice_chain import COMPRESSORS
from remanga.config import RemangaConfig
from remanga.config.presets import PRESETS_DIR, load_presets, preset_named
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
# Bigger than any chapter: plan_batches caps it at the engine's longest take.
WHOLE_CHAPTER = 999.0

NARRATION_TAKES = ((0.0, "one take per panel - the voice restarts at every panel"),
                   (0.5, "about 30 seconds - closest to a cloned voice, most restarts"),
                   (1.0, "about a minute - the longest a cloned voice still sounds like its recording"),
                   (2.0, "about 2 minutes - a scene or two per take"),
                   (3.0, "about 3 minutes - fewer seams; preset and Kokoro voices only"),
                   (5.0, "about 5 minutes - fewest seams, most to redo if one line changes"),
                   (WHOLE_CHAPTER, "the whole chapter in one take - no seams at all; Kokoro only, "
                                   "other engines stop at their own longest"))


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


def take_length_label(minutes: float) -> str:
    if not minutes:
        return "one per panel"
    return "the whole chapter" if minutes >= WHOLE_CHAPTER else f"about {minutes:g} min"


async def change_narration_takes(screen: SettingsScreen, config: RemangaConfig) -> None:
    current = config.audio.batch_target_minutes if config.audio.batch_narration else 0.0
    minutes = await screen.app.push_screen_wait(Choice(
        "Narration take length",
        [(take_length_label(m), hint, m) for m, hint in NARRATION_TAKES],
        current=current,
        note="How much of the chapter the narrator reads without stopping. A panel read on its own "
             "is a performance of its own, so the tone resets at every panel - reading straight "
             "through a scene is what keeps one voice across it. Where each panel falls inside a "
             "take is found by listening to it afterwards, so the pictures are still cut to the "
             "words. A voice cloned from a recording drifts off it after about a minute, so it is "
             "held to a minute whatever is picked here. A preset voice or Kokoro has nothing to "
             "drift from and may go up to five minutes; past that a Qwen take can lose the thread "
             "(nine minutes at once once did). Kokoro has neither problem and can read the whole "
             "chapter as one take. A take is the unit that gets made again, so a "
             "longer one costs more to redo when one panel's line changes."))
    if minutes is not None:
        config.audio.batch_narration = minutes > 0
        if minutes > 0:
            config.audio.batch_target_minutes = minutes


COMPRESSOR_HINTS = (("off", "the voice as the engine made it"),
                    ("gentle", "takes the edge off the loudest words"),
                    ("medium", "thick and close to the mic - recommended"),
                    ("strong", "flat and in your face, radio-promo style"))


BASS_BOOSTS = ((0.0, "off"), (2.0, "a little warmth"), (3.0, "radio-narrator chest - recommended"),
               (5.0, "deep"), (7.0, "booming - can muddy on big speakers"))


LOUDNESS_TARGETS = ((-14.0, "YouTube's level - recommended"), (-16.0, "a little quieter - podcasts, Apple"),
                    (-13.0, "a little louder - TikTok and Shorts"), (None, "off - the mix as it comes"))


def compressor_label(name: str) -> str:
    return name if name in COMPRESSORS else "off"


def bass_label(db: float) -> str:
    return f"+{db:g} dB at 150 Hz" if db > 0 else "off"


def loudness_label(audio) -> str:
    return f"{audio.loudness_target_lufs:g} LUFS" if audio.enable_loudnorm else "off"


async def change_compressor(screen: SettingsScreen, config: RemangaConfig) -> None:
    picked = await screen.app.push_screen_wait(Choice(
        "Compressor", [(name, hint, name) for name, hint in COMPRESSOR_HINTS],
        current=compressor_label(config.audio.voice_compressor),
        note="Squashes the peaks and lifts the quiet parts, so the whole voice sounds thick, powerful "
             "and close to the microphone. The voice's overall level is kept - this changes its "
             "character, not its loudness. Changing it re-mixes the chapter; nothing is narrated again."))
    if picked:
        config.audio.voice_compressor = picked


async def change_bass_boost(screen: SettingsScreen, config: RemangaConfig) -> None:
    current = config.audio.voice_bass_boost_db
    options = [(bass_label(db), hint, db) for db, hint in BASS_BOOSTS]
    if all(current != db for db, _ in BASS_BOOSTS):
        options.append((bass_label(current), "your custom boost", current))
    options.append(("Custom...", "type your own number of dB", "custom"))
    note = ("A low shelf at 150 Hz (the 100-200 Hz chest of a voice) for that deep radio-narrator "
            "resonance; rumble under 60 Hz is cut rather than boosted with it. Changing it re-mixes the "
            "chapter; nothing is narrated again.")
    db = await screen.app.push_screen_wait(Choice("Bass boost", options, current=current, note=note))
    if db == "custom":
        db = await screen.app.push_screen_wait(Ask(
            "Bass boost", "Boost in dB (0 is off, up to 12)", value=f"{current:g}",
            check=number_check(0, 12), note=note))
    if db is not None:
        config.audio.voice_bass_boost_db = float(db)


async def change_limiter(screen: SettingsScreen, config: RemangaConfig) -> None:
    picked = await screen.app.push_screen_wait(Choice(
        "Limiter", [("on", "peaks are held under -1 dB, so the mix reaches its loudness - recommended", True),
                    ("off", "nothing holds the peaks; a mix that would clip is left quieter instead", False)],
        current=config.audio.voice_limiter,
        note="A ceiling on the finished mix's peaks, so the loudness pass can bring it up to standard "
             "without distorting. Changing it re-mixes the chapter."))
    if picked is not None:
        config.audio.voice_limiter = picked


async def change_loudness(screen: SettingsScreen, config: RemangaConfig) -> None:
    audio = config.audio
    current = audio.loudness_target_lufs if audio.enable_loudnorm else None
    options = [(f"{lufs:g} LUFS" if lufs is not None else "off", hint, lufs if lufs is not None else "off")
               for lufs, hint in LOUDNESS_TARGETS]
    if current is not None and all(current != lufs for lufs, _ in LOUDNESS_TARGETS):
        options.insert(-1, (f"{current:g} LUFS", "your custom level", current))
    options.insert(-1, ("Custom...", "type your own LUFS", "custom"))
    note = ("Normalizes the finished mix to a standard loudness, the way YouTube measures it: a "
            "quieter video is not turned up and sounds weak next to others. One gain for the whole "
            "track - the limiter holds the few peaks it would push over. Changing it re-mixes the chapter.")
    picked = await screen.app.push_screen_wait(Choice(
        "Loudness", options, current=current if current is not None else "off", note=note))
    if picked == "custom":
        picked = await screen.app.push_screen_wait(Ask(
            "Loudness", "Target in LUFS (-30 to -8)", value=f"{audio.loudness_target_lufs:g}",
            check=number_check(-30, -8), note=note))
    if picked == "off":
        audio.enable_loudnorm = False
    elif picked is not None:
        audio.enable_loudnorm, audio.loudness_target_lufs = True, float(picked)


def preset_label(config: RemangaConfig) -> str:
    preset = preset_named(config.narration_preset)
    return preset.name if preset else "none"


async def change_preset(screen: SettingsScreen, config: RemangaConfig) -> None:
    options = [(preset.name, preset.description, key) for key, preset in load_presets().items()]
    options.append(("No preset", "set every narration row yourself", ""))
    current = config.narration_preset if preset_named(config.narration_preset) else ""
    picked = await screen.app.push_screen_wait(Choice(
        "Narration preset", options, current=current,
        note=f"A preset fixes the narration settings it names - engine, speed, take length, compressor, "
             f"bass, limiter, loudness - and locks those rows while it is picked. Each preset is a JSON "
             f"file in {PRESETS_DIR}/; copy one to make your own (README.md there lists the keys). "
             f"No preset unlocks every row, starting from the values in use now. A preset that changes "
             f"the engine or speed narrates chapters again; the rest only re-mixes."))
    if picked is not None:
        config.narration_preset = picked
        config.apply_preset()


def lock_preset_rows(rows: list, config: RemangaConfig) -> None:
    """Rows whose settings the picked preset fixes: shown with their value,
    but opening one only says where the value comes from."""
    preset = preset_named(config.narration_preset)
    if preset is None:
        return
    fixed = preset.fixed_keys(config)

    async def locked(screen: SettingsScreen, _config: RemangaConfig) -> None:
        screen.notify(f"Set by the narration preset '{preset.name}'. Pick another preset, or No preset, "
                      f"under Narration preset to change it.", timeout=7)

    for row in rows:
        if row.keys and any(key in fixed for key in row.keys):
            row.value, row.change = f"{row.value}  (preset)", locked
