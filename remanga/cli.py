from __future__ import annotations

import argparse
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from remanga.config import RemangaConfig, get_chapter_dir
from remanga.downloader import MangaDexDownloader
from remanga.cropper import CoordinateCropper
from remanga.audio import TTSEngine, AudioProcessor
from remanga.video import VideoRenderer

console = Console()


def display_status(project: str, chapter: str):
    chap_dir = get_chapter_dir(project, chapter)
    pages_count = len(list((chap_dir / "pages").glob("page_*.*"))) if (chap_dir / "pages").exists() else 0
    crops_exist = (chap_dir / "crops.json").exists()
    panels_count = len(list((chap_dir / "panels").glob("panel_*.*"))) if (chap_dir / "panels").exists() else 0
    narration_exist = (chap_dir / "narration.json").exists()
    audio_exist = (chap_dir / "master_audio.wav").exists()
    video_exist = (chap_dir / f"{project}_ch{chapter}_recap.mp4").exists()

    status_str = f"""
[bold cyan]Project:[/] {project} | [bold cyan]Chapter:[/] {chapter}
[bold]Workspace Directory:[/] {chap_dir.resolve()}

  1. Pages Downloaded   : {'[green]✓ Yes (' + str(pages_count) + ' pages)[/]' if pages_count > 0 else '[red]✗ Missing[/]'}
  2. Crop JSON          : {'[green]✓ Present (' + str(chap_dir / 'crops.json') + ')[/]' if crops_exist else '[yellow]✗ Missing (Place crops.json in folder)[/]'}
  3. Panels Cropped     : {'[green]✓ Yes (' + str(panels_count) + ' panels)[/]' if panels_count > 0 else '[red]✗ Missing[/]'}
  4. Narration JSON     : {'[green]✓ Present (' + str(chap_dir / 'narration.json') + ')[/]' if narration_exist else '[yellow]✗ Missing (Place narration.json in folder)[/]'}
  5. Master Audio       : {'[green]✓ Generated[/]' if audio_exist else '[red]✗ Not built[/]'}
  6. Final Recap Video  : {'[green]✓ Ready (' + str(chap_dir / f"{project}_ch{chapter}_recap.mp4") + ')[/]' if video_exist else '[red]✗ Not rendered[/]'}
"""
    console.print(Panel(status_str.strip(), title="[bold white]remanga Chapter Status[/]", border_style="blue"))


def main():
    parser = argparse.ArgumentParser(description="remanga: Lightweight Manga Recap Production Pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    p_dl = subparsers.add_parser("download", help="Download manga chapter from MangaDex")
    p_dl.add_argument("--url", "-u", required=True, help="Manga title or MangaDex URL/UUID")
    p_dl.add_argument("--chapter", "-c", required=True, help="Chapter number (e.g. 1 or 01)")
    p_dl.add_argument("--project", "-p", required=True, help="Project name")

    # crop
    p_crop = subparsers.add_parser("crop", help="Crop panels using coordinates in crops.json")
    p_crop.add_argument("--project", "-p", required=True, help="Project name")
    p_crop.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # tts
    p_tts = subparsers.add_parser("tts", help="Generate vocal audio from narration.json")
    p_tts.add_argument("--project", "-p", required=True, help="Project name")
    p_tts.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # mix
    p_mix = subparsers.add_parser("mix", help="Mix narration, apply edge fades, BGM, and normalize")
    p_mix.add_argument("--project", "-p", required=True, help="Project name")
    p_mix.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # render
    p_rnd = subparsers.add_parser("render", help="Render final recap MP4 video")
    p_rnd.add_argument("--project", "-p", required=True, help="Project name")
    p_rnd.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # status
    p_stat = subparsers.add_parser("status", help="Inspect chapter production status")
    p_stat.add_argument("--project", "-p", required=True, help="Project name")
    p_stat.add_argument("--chapter", "-c", required=True, help="Chapter number")

    args = parser.parse_args()
    config = RemangaConfig.load()

    try:
        if args.command == "download":
            dl = MangaDexDownloader(config.downloader)
            dl.download_chapter(args.url, args.chapter, args.project)
        elif args.command == "crop":
            cropper = CoordinateCropper(config.cropper)
            cropper.crop_chapter_from_json(args.project, args.chapter)
        elif args.command == "tts":
            tts = TTSEngine(config.tts, config.audio)
            tts.generate_narration_audio(args.project, args.chapter)
        elif args.command == "mix":
            mixer = AudioProcessor(config.audio)
            mixer.mix_master_audio(args.project, args.chapter)
        elif args.command == "render":
            renderer = VideoRenderer(config.system, config.video)
            renderer.render_video(args.project, args.chapter)
        elif args.command == "status":
            display_status(args.project, args.chapter)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()