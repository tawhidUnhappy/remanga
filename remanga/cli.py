from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from remanga.config import RemangaConfig, get_chapter_dir, load_project_metadata
from remanga.downloader import MangaDexDownloader
from remanga.cropper import CoordinateCropper
from remanga.audio import TTSEngine, AudioProcessor
from remanga.video import VideoRenderer

console = Console()


def graceful_sigint_handler(signum, frame):
    """Handle Ctrl+C gracefully without traceback noise."""
    console.print("\n\n[bold yellow]👋 Production paused. You can resume at any time![/]")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_sigint_handler)


def display_status(project: str, chapter: str):
    chap_dir = get_chapter_dir(project, chapter)
    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url") or meta.get("manga_id", "Not set")

    pages_count = len(list((chap_dir / "pages").glob("page_*.*"))) if (chap_dir / "pages").exists() else 0
    pages_zip_exist = (chap_dir / "pages.zip").exists()
    crops_exist = (chap_dir / "crops.json").exists() and (chap_dir / "crops.json").stat().st_size > 0
    panels_count = len(list((chap_dir / "panels").glob("panel_*.*"))) if (chap_dir / "panels").exists() else 0
    sheets_count = len(list((chap_dir / "sheets").glob("sheet_*.*"))) if (chap_dir / "sheets").exists() else 0
    sheets_zip_exist = (chap_dir / "sheets.zip").exists()
    narration_exist = (chap_dir / "narration.json").exists() and (chap_dir / "narration.json").stat().st_size > 0
    audio_exist = (chap_dir / "master_audio.wav").exists()
    video_exist = (chap_dir / f"{project}_ch{chapter}_recap.mp4").exists()

    config = RemangaConfig.load()
    voice_path = Path(config.tts.spk_audio_prompt)
    voice_status = f"[green]Configured ({voice_path})[/]" if voice_path.exists() else f"[yellow]Not found ({voice_path})[/]"

    status_str = f"""
[bold cyan]Project:[/] {project} | [bold cyan]Chapter:[/] {chapter}
[bold cyan]Saved Manga Source:[/] {saved_url}
[bold]Workspace Directory:[/] {chap_dir.resolve()}
[bold]Reference Voice Audio:[/] {voice_status}

  1. Pages Downloaded    : {'[green]✓ Yes (' + str(pages_count) + ' pages)[/]' if pages_count > 0 else '[red]✗ Missing[/]'}
  2. Pages ZIP Archive   : {'[green]✓ Ready (' + str(chap_dir / 'pages.zip') + ')[/]' if pages_zip_exist else '[dim yellow]✗ Not generated[/]'}
  3. Crop Instructions   : {'[green]✓ Present (' + str(chap_dir / 'crops.json') + ')[/]' if crops_exist else '[yellow]✗ Missing/Empty placeholder[/]'}
  4. Panels Cropped      : {'[green]✓ Yes (' + str(panels_count) + ' panels)[/]' if panels_count > 0 else '[red]✗ Missing[/]'}
  5. Panel Contact Sheets: {'[green]✓ Yes (' + str(sheets_count) + ' sheets)[/]' if sheets_count > 0 else '[dim yellow]✗ Not generated[/]'}
  6. Sheets ZIP Archive  : {'[green]✓ Ready (' + str(chap_dir / 'sheets.zip') + ')[/]' if sheets_zip_exist else '[dim yellow]✗ Not generated[/]'}
  7. Narration Script    : {'[green]✓ Present (' + str(chap_dir / 'narration.json') + ')[/]' if narration_exist else '[yellow]✗ Missing/Empty placeholder[/]'}
  8. Master Audio Track  : {'[green]✓ Generated (IndexTTS-2.5)[/]' if audio_exist else '[red]✗ Not built[/]'}
  9. Final Recap Video   : {'[green]✓ Ready (' + str(chap_dir / f"{project}_ch{chapter}_recap.mp4") + ')[/]' if video_exist else '[red]✗ Not rendered[/]'}
"""
    console.print(Panel(status_str.strip(), title="[bold white]remanga Chapter Production Status[/]", border_style="blue"))


def main():
    parser = argparse.ArgumentParser(description="remanga: Lightweight Manga Recap Production Pipeline powered by IndexTTS-2.5")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # download
    p_dl = subparsers.add_parser("download", help="Download manga chapter from MangaDex")
    p_dl.add_argument("--project", "-p", required=True, help="Project name")
    p_dl.add_argument("--chapter", "-c", required=True, help="Chapter number (e.g. 1 or 01)")
    p_dl.add_argument("--url", "-u", required=False, default=None, help="Manga title or MangaDex URL/UUID (optional if saved)")

    # crop
    p_crop = subparsers.add_parser("crop", help="Crop panels using coordinates in crops.json and package sheets.zip")
    p_crop.add_argument("--project", "-p", required=True, help="Project name")
    p_crop.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # tts
    p_tts = subparsers.add_parser("tts", help="Generate vocal audio via IndexTTS-2.5 from narration.json")
    p_tts.add_argument("--project", "-p", required=True, help="Project name")
    p_tts.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_tts.add_argument("--voice", "-v", required=False, default=None, help="Override reference speaker WAV path")

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
            tts.generate_narration_audio(args.project, args.chapter, voice_override=args.voice)
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