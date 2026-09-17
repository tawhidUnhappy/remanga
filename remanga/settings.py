"""The settings screen: the narrator's voice and speed, the background music,
the video size, and the PDF size cap. Everything else is in config.json.

Opened from inside a project, a change is saved for that project (project.json);
from the project list, for every project (config.json) - see config/root.py."""

from __future__ import annotations

from pathlib import Path

from remanga.config import RemangaConfig
from remanga.config.kokoro_voices import KOKORO_VOICES
from remanga.console import console
from remanga.paths import GLOBAL_DIR
from remanga.tui import Choice, ask_number, is_cancel, select

MUSIC_EXTS = (".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac")
RESOLUTIONS = ((1920, 1080, "1080p widescreen"), (1280, 720, "720p widescreen"), (1080, 1920, "1080p vertical"))
_MUSIC_OFF = "__off__"
MUSIC_LEVELS = ((12.0, "energetic - music clearly felt"), (14.0, "balanced - recommended"),
                (18.0, "subtle - a quiet bed"))


def _music_files() -> list[Path]:
    folder = GLOBAL_DIR / "bgm"
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in MUSIC_EXTS) if folder.exists() else []


def summary(config: RemangaConfig) -> dict[str, str]:
    audio = config.audio
    return {
        "voice": f"{config.tts.voice_label} · speed {config.tts.speed:g}x",
        "music": f"{Path(audio.bgm_path).name}, {audio.bgm_below_voice_lu:g} LU under the voice"
        if audio.bgm_enabled and audio.bgm_path else "off",
        "video": f"{config.video.width}x{config.video.height}",
        "pdf": f"at most {config.pdf.max_mb:g}MB per file",
    }


def run_settings(config: RemangaConfig) -> None:
    scope = f"saved for {config.project}" if config.project else "saved for every project"
    while True:
        now = summary(config)
        picked = select("Settings", [
            Choice("Narrator voice", hint=now["voice"], value="voice"),
            Choice("Background music", hint=now["music"], value="music"),
            Choice("Video size", hint=now["video"], value="video"),
            Choice("PDF size cap", hint=now["pdf"], value="pdf"),
        ], note=scope, back_label="Back")
        if is_cancel(picked):
            return
        {"voice": _voice, "music": _music, "video": _video, "pdf": _pdf}[picked](config)


def _voice(config: RemangaConfig) -> None:
    rows = [Choice(v.label, hint=f"grade {v.grade} · {v.accent}", value=v.name) for v in KOKORO_VOICES]
    voice = select("Narrator voice", rows, default=config.tts.voice,
                   note="Kokoro-82M's voices, best graded first", back_label="Back")
    if is_cancel(voice):
        return
    speed = ask_number("Speaking speed", default=config.tts.speed, minimum=0.5, maximum=2.0,
                       note="1.0 is normal")
    config.tts.voice, config.tts.speed = voice, float(speed)
    config.save()
    console.print(f"[green]✓ Voice:[/] {config.tts.voice_label}, speed {config.tts.speed:g}x "
                  f"[dim](chapters already narrated in another voice are narrated again)[/]")


def _music(config: RemangaConfig) -> None:
    files = _music_files()
    rows = [Choice("No music", value=_MUSIC_OFF)]
    rows += [Choice(p.name, hint=str(p.parent), value=str(p)) for p in files]
    current = config.audio.bgm_path if config.audio.bgm_enabled else _MUSIC_OFF
    picked = select("Background music", rows, default=current,
                    note=f"put music files in {GLOBAL_DIR / 'bgm'}/", back_label="Back")
    if is_cancel(picked):
        return
    if picked == _MUSIC_OFF:
        config.audio.bgm_enabled = False
    else:
        level = select("How present should the music be?", [
            Choice(f"{lu:g} LU under the voice", hint=hint, value=lu) for lu, hint in MUSIC_LEVELS
        ], default=config.audio.bgm_below_voice_lu, back_label="Back",
            note="measured per track and chapter, so any music file sits at the same level")
        if is_cancel(level):
            return
        config.audio.bgm_path, config.audio.bgm_enabled = picked, True
        config.audio.bgm_below_voice_lu = float(level)
    config.save()
    console.print(f"[green]✓ Music:[/] {summary(config)['music']}")


def _video(config: RemangaConfig) -> None:
    rows = [Choice(f"{w}x{h}", hint=label, value=(w, h)) for w, h, label in RESOLUTIONS]
    picked = select("Video size", rows, default=(config.video.width, config.video.height), back_label="Back")
    if is_cancel(picked):
        return
    config.video.width, config.video.height = picked
    config.save()
    console.print(f"[green]✓ Video:[/] {summary(config)['video']}")


def _pdf(config: RemangaConfig) -> None:
    cap = ask_number("Largest PDF file, in MB", default=config.pdf.max_mb, minimum=1, maximum=2000,
                     note="a chapter bigger than this is split into pages_1.pdf, pages_2.pdf, ...")
    config.pdf.max_mb = float(cap)
    config.save()
    console.print(f"[green]✓ PDF:[/] {summary(config)['pdf']}")
