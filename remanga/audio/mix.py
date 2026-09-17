"""A chapter's master track: every page's narration clip with the pause after
it, background music under the whole of it, normalized.

Skipped when master_audio.wav already matches: the synthesized audio
(audio_timing.json, rewritten only when its content changes) and every mix
setting are fingerprinted, so a plain re-run doesn't re-mix - and in turn
doesn't make the render think the sound changed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from remanga.audio.join import join_segments
from remanga.audio.master import load_bgm, page_segments, under_narration, write_master
from remanga.config import AudioConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json, read_json_or, write_json
from remanga.paths import get_audio_dir, get_audio_timing_path, get_master_audio_path


def _bgm_file(config: AudioConfig) -> Path | None:
    if not config.bgm_enabled:
        return None
    path = Path(str(config.bgm_path or "")).expanduser()
    if path.is_file():
        return path
    console.print(f"[yellow]Background music is on, but '{_esc(str(config.bgm_path))}' isn't a file - mixing "
                  f"without music.[/]")
    return None


def _fingerprint(timing_path: Path, config: AudioConfig, bgm: Path | None) -> dict[str, Any]:
    bgm_stat = bgm.stat() if bgm else None
    return {
        "timing_mtime": timing_path.stat().st_mtime,
        "bgm": [str(bgm), bgm_stat.st_size, int(bgm_stat.st_mtime)] if bgm_stat else None,
        "bgm_volume_db": config.bgm_volume_db,
        "sample_rate": config.sample_rate,
        "enable_loudnorm": config.enable_loudnorm,
    }


def mix_master_audio(project_name: str, chapter_num: str, config: AudioConfig, force: bool = False) -> Path:
    timing_path = get_audio_timing_path(project_name, chapter_num)
    if not timing_path.exists():
        raise FileNotFoundError(f"No narration audio for chapter {chapter_num} yet: {timing_path}")
    master = get_master_audio_path(project_name, chapter_num)
    fingerprint_path = master.with_name("master_audio_fingerprint.json")
    bgm = _bgm_file(config)

    fingerprint = _fingerprint(timing_path, config, bgm)
    if (not force and master.exists() and master.stat().st_size > 1000
            and read_json_or(fingerprint_path, None) == fingerprint):
        console.print(f"[dim]✓ Chapter {chapter_num}'s audio mix is already up to date.[/]")
        return master

    console.print(f"[cyan]Mixing chapter {chapter_num}'s audio...[/]")
    audio_dir = get_audio_dir(project_name, chapter_num)
    segments = []
    for page in read_json(timing_path).get("pages", []):
        segments.extend(page_segments(audio_dir, page, config.sample_rate))
    track = join_segments(segments).set_channels(2).set_frame_rate(config.sample_rate)

    if bgm:
        console.print(f"[cyan]Adding background music:[/] {_esc(str(bgm))}")
        track = under_narration(track, load_bgm(bgm, config.sample_rate), config.bgm_volume_db)

    raw = master.with_name("master_audio_raw.wav")
    track.export(raw, format="wav")
    write_master(raw, master, config.sample_rate, normalize=config.enable_loudnorm,
                 announcement="Normalizing loudness (EBU R128)...", on_failure="the un-normalized mix")
    write_json(fingerprint_path, _fingerprint(timing_path, config, bgm))
    console.print(f"[bold green]✓ Audio mixed:[/] {_esc(str(master))}")
    return master
