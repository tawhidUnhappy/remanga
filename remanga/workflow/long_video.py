"""One video of several chapters - chapter n to chapter m (user request,
2026-10-05), kept in video/long/ch<label>/ beside the chapters' own videos.

Two ways to make one, both ending on the same join:
- join: each chapter's video as it stands - rendered only where it is
  missing or stale for the settings now, narrated only where it never was;
- from source: every chapter remade from its pages, marks and
  narration.json first (remake_from_source), then joined.

The join takes each chapter's picture stream and mixed sound (not its
finished MP4, which may carry the intro), so the long video has the intro
once, in front. A chapter's sound is fitted to its picture's exact length,
so no chapter can pull the ones after it out of sync. The pictures are
stream-copied when every one was encoded alike, and re-encoded together
when not."""

from __future__ import annotations

from pathlib import Path

from remanga.chapters import chapter_sort_key
from remanga.config import RemangaConfig
from remanga.console import console, escape as _esc
from remanga.json_io import read_json_or, write_json
from remanga.paths import (
    get_audio_timing_path,
    get_long_video_dir,
    get_long_video_path,
    get_long_videos_dir,
    get_master_audio_path,
    get_project_dir,
    get_video_picture_path,
)
from remanga.workflow.chapters import local_chapters
from remanga.workflow.cleanup import delete_paths, inside

INFO = "long.json"


def long_label(project: str, chapters: list[str]) -> str:
    """The chapters as a short name: runs of chapters next to each other on
    disk become a range - 1-5, or 1-3+7 when 4 to 6 were left out."""
    order = local_chapters(project)
    position = {ch: i for i, ch in enumerate(order)}
    picked = sorted(set(chapters), key=lambda ch: (position.get(ch, len(order)), chapter_sort_key(ch)))
    runs: list[list[str]] = []
    for ch in picked:
        if runs and ch in position and runs[-1][-1] in position and position[ch] == position[runs[-1][-1]] + 1:
            runs[-1].append(ch)
        else:
            runs.append([ch])
    return "+".join(run[0] if len(run) == 1 else f"{run[0]}-{run[-1]}" for run in runs)


def ordered(project: str, chapters: list[str]) -> list[str]:
    order = local_chapters(project)
    return sorted(set(chapters), key=lambda ch: (order.index(ch) if ch in order else len(order),
                                                 chapter_sort_key(ch)))


def long_videos(project: str) -> list[dict]:
    """Every long video made for this project: its label, file, chapters and
    size - the newest first."""
    root = get_long_videos_dir(project)
    found = []
    for folder in sorted(root.glob("ch*"), key=lambda p: p.stat().st_mtime, reverse=True) if root.is_dir() else []:
        info = read_json_or(folder / INFO, {})
        label = info.get("label") or folder.name[2:]
        video = get_long_video_path(project, label, create=False)
        size = sum(p.stat().st_size for p in folder.rglob("*") if p.is_file())
        found.append({"label": label, "folder": folder, "video": video if video.exists() else None,
                      "chapters": info.get("chapters", []), "size": size})
    return found


def delete_long_video(project: str, label: str) -> list[Path]:
    """Deletes one long video's folder - only ever a folder inside
    video/long/ of this project - and video/long/ itself once it is empty.
    The chapters' own videos are untouched."""
    folder = get_long_video_dir(project, label, create=False)
    if not inside(folder, get_long_videos_dir(project)) or not inside(folder, get_project_dir(project)):
        raise ValueError(f"Refusing to delete {folder} - it isn't a long video of {project}.")
    return delete_paths([folder], project)


def prepare_chapter(project: str, chapter: str, config: RemangaConfig) -> None:
    """This chapter's picture and mixed sound, current for the settings now -
    reusing whatever already is: rendered only when missing or stale, mixed
    only when the mix is missing, narrated only when it never was."""
    from remanga.workflow.video import make_video, mix, render

    if not get_audio_timing_path(project, chapter, create=False).exists():
        console.print(f"[bold]Chapter {chapter}:[/] not narrated yet - making its video first")
        make_video(project, chapter, config)
        return
    if not get_master_audio_path(project, chapter, create=False).exists():
        mix(project, chapter, config)
    render(project, chapter, config)


def make_long_video(project: str, chapters: list[str], config: RemangaConfig, from_source: bool = False) -> Path:
    """One video of `chapters`, in reading order (see the module's note)."""
    from remanga.workflow.video import remake_from_source

    chapters = ordered(project, chapters)
    if len(chapters) < 2:
        raise ValueError("A long video needs two chapters or more.")
    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        if from_source:
            remake_from_source(project, chapter, config)
        else:
            prepare_chapter(project, chapter, config)
    return join_chapters(project, chapters, config)


def join_chapters(project: str, chapters: list[str], config: RemangaConfig) -> Path:
    """The chapters' pictures and sound, already made, one after another into
    one MP4 - with the intro once, in front."""
    from remanga.ffmpeg_io import run_ffmpeg
    from remanga.video import VideoRenderer
    from remanga.video.encoding import AUDIO_CODEC_ARGS, COLOR_TAG_ARGS, MUX_ARGS, picture_codec_args, stream_signature
    from remanga.video.intro import _duration, chosen_intro, intro_identity, join as join_intro, leader

    chapters = ordered(project, chapters)
    label = long_label(project, chapters)
    folder = get_long_video_dir(project, label)
    work = folder / "_work"
    work.mkdir(parents=True, exist_ok=True)
    final = get_long_video_path(project, label)

    missing = [ch for ch in chapters if not get_video_picture_path(project, ch, create=False).exists()
               or not get_master_audio_path(project, ch, create=False).exists()]
    if missing:
        raise FileNotFoundError(f"Chapter(s) {', '.join(missing)} have no video to join yet - make them first.")

    renderer = VideoRenderer(config.system, config.video)
    segments: list[Path] = []
    try:
        # 1. Each chapter's picture with its own sound, the sound padded or cut
        # to the picture's exact length.
        for chapter in chapters:
            picture = get_video_picture_path(project, chapter)
            seconds = _duration(picture)
            segment = work / f"chapter_{chapter}.mp4"
            result = run_ffmpeg(["ffmpeg", "-y", "-i", str(picture), "-i", str(get_master_audio_path(project, chapter)),
                                 "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-af", "apad",
                                 *AUDIO_CODEC_ARGS, "-t", f"{seconds:.3f}", str(segment)],
                                capture=True, show_progress=True, total_seconds=seconds,
                                description=f"Chapter {chapter}: sound")
            if result.returncode != 0:
                raise RuntimeError(f"Could not prepare chapter {chapter}:\n{result.stderr[-1500:]}")
            segments.append(segment)

        # 2. One after another: a stream copy when every picture was encoded
        # alike (the same settings and encoder), otherwise one re-encode.
        body = work / "body.part.mp4"
        signatures = {stream_signature(s) for s in segments}
        total = sum(_duration(s) for s in segments)
        console.print(f"[cyan]Joining {len(segments)} chapters[/] [dim]({total / 60:.1f} minutes)[/]")
        if len(signatures) == 1 and None not in signatures:
            listing = work / "segments.txt"
            listing.write_text("".join(f"file '{s.resolve().as_posix()}'\n" for s in segments), encoding="utf-8")
            result = run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                                 "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", *MUX_ARGS, str(body)], capture=True)
            listing.unlink(missing_ok=True)
        else:
            console.print("[dim](the chapters' pictures were encoded differently - joining by re-encoding)[/]")
            ffmpeg_bin, codec, use_gpu, _ = renderer.encoder()
            inputs = [arg for s in segments for arg in ("-i", str(s))]
            streams = "".join(f"[{i}:v][{i}:a]" for i in range(len(segments)))
            result = run_ffmpeg([ffmpeg_bin, "-y", *inputs, "-filter_complex",
                                 f"{streams}concat=n={len(segments)}:v=1:a=1[v][a]", "-map", "[v]", "-map", "[a]",
                                 *COLOR_TAG_ARGS, "-bf", "0",
                                 *picture_codec_args(codec, use_gpu, config.system.threads),
                                 *AUDIO_CODEC_ARGS, *MUX_ARGS, str(body)],
                                capture=True, show_progress=True, total_seconds=total,
                                description="Joining the chapters")
        if result.returncode != 0:
            body.unlink(missing_ok=True)
            raise RuntimeError(f"Could not join the chapters:\n{result.stderr[-1500:]}")

        # 3. The intro, once, in front.
        intro = chosen_intro(config.video)
        if intro is not None:
            joined = work / "joined.part.mp4"
            join_intro(renderer, leader(renderer, intro, body, work), body, joined)
            body.unlink(missing_ok=True)
            joined.replace(final)
            console.print(f"[cyan]Intro added:[/] {_esc(intro.name)}")
        else:
            body.replace(final)
    finally:
        for segment in segments:
            segment.unlink(missing_ok=True)
    # The intro's leader is cached here for the next join; with no intro the
    # folder is left empty, and goes.
    if not any(work.iterdir()):
        work.rmdir()
    write_json(folder / INFO, {"label": label, "chapters": chapters, "intro": intro_identity(config.video)})
    console.print(f"[bold green]✓ Long video of chapters {_esc(label)}:[/] {_esc(str(final))}")
    return final
