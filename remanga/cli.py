from __future__ import annotations

import argparse
import signal
import sys
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig, get_chapter_dir, get_chapter_status, load_project_metadata
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.models import ModelManager
from remanga.pipeline import run_interactive_pipeline
from remanga.video import VideoRenderer

console = Console()


def graceful_sigint_handler(signum, frame):
    """Handle Ctrl+C gracefully without traceback noise."""
    console.print("\n\n[bold yellow]👋 Production paused. You can resume at any time![/]")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_sigint_handler)


def display_status(project: str, chapter: str):
    st = get_chapter_status(project, chapter)
    meta = load_project_metadata(project)
    saved_url = meta.get("manga_url") or meta.get("manga_id", "Not set")

    config = RemangaConfig.load()
    voice_path = Path(config.tts.spk_audio_prompt).expanduser() if config.tts.spk_audio_prompt else None
    voice_status = f"[green]Configured ({voice_path})[/]" if (voice_path and voice_path.exists()) else f"[yellow]Not set / Missing ({voice_path})[/]"

    bgm_path = Path(config.audio.bgm_path).expanduser() if config.audio.bgm_path else None
    bgm_status = f"[green]Enabled ({bgm_path})[/]" if (config.audio.bgm_enabled and bgm_path and bgm_path.exists()) else "[dim]Disabled / None[/]"

    status_str = f"""
[bold cyan]Project:[/] {project} | [bold cyan]Chapter:[/] {chapter}
[bold cyan]Saved Manga Source:[/] {saved_url}
[bold]Workspace Directory:[/] {st['chap_dir'].resolve()}
[bold]Reference Voice Audio:[/] {voice_status}
[bold]Background Music:[/] {bgm_status}

  1. Pages Downloaded    : {'[green]✓ Yes (' + str(st['pages_count']) + ' pages)[/]' if st['pages_count'] > 0 else '[red]✗ Missing[/]'}
  2. Pages ZIP Archive   : {'[green]✓ Ready (' + str(st['chap_dir'] / 'pages.zip') + ')[/]' if st['pages_zip_exist'] else '[dim yellow]✗ Not generated[/]'}
  3. Crop Instructions   : {'[green]✓ Present (' + str(st['chap_dir'] / 'crops.json') + ')[/]' if st['crops_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
  4. Panels Cropped      : {'[green]✓ Yes (' + str(st['panels_count']) + ' panels)[/]' if st['panels_count'] > 0 else '[red]✗ Missing[/]'}
  5. Panel Contact Sheets: {'[green]✓ Yes (' + str(st['sheets_count']) + ' sheets)[/]' if st['sheets_count'] > 0 else '[dim yellow]✗ Not generated[/]'}
  6. Sheets ZIP Archive  : {'[green]✓ Ready (' + str(st['chap_dir'] / 'sheets.zip') + ')[/]' if st['sheets_zip_exist'] else '[dim yellow]✗ Not generated[/]'}
  7. Narration Script    : {'[green]✓ Present (' + str(st['chap_dir'] / 'narration.json') + ')[/]' if st['narration_exist'] else '[yellow]✗ Missing/Empty placeholder[/]'}
  8. Master Audio Track  : {'[green]✓ Generated (IndexTTS-2.5)[/]' if st['master_audio_exist'] else '[red]✗ Not built (' + str(st['audio_clips_count']) + '/' + str(st['total_narration_entries']) + ' clips)[/]'}
  9. Final Recap Video   : {'[green]✓ Ready (' + str(st['video_path']) + ')[/]' if st['video_exist'] else '[red]✗ Not rendered[/]'}
"""
    console.print(Panel(status_str.strip(), title="[bold white]remanga Chapter Production Status[/]", border_style="blue"))


def main():
    parser = argparse.ArgumentParser(description="remanga: Lightweight, Self-Contained Manga Recap Production Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # interactive wizard
    subparsers.add_parser("interactive", help="Start interactive step-by-step production wizard")

    # setup models
    subparsers.add_parser("setup-models", help="Verify and download model weights with SHA-256 verification")

    # download
    p_dl = subparsers.add_parser("download", help="Download manga chapter from MangaDex")
    p_dl.add_argument("--project", "-p", required=True, help="Project name")
    p_dl.add_argument("--chapter", "-c", required=True, help="Chapter number (e.g. 1 or 01)")
    p_dl.add_argument("--url", "-u", required=False, default=None, help="Manga title or MangaDex URL/UUID (optional if saved)")

    # crop
    p_crop = subparsers.add_parser("crop", help="Crop panels using coordinates in crops.json and package sheets.zip")
    p_crop.add_argument("--project", "-p", required=True, help="Project name")
    p_crop.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_crop.add_argument("--force", "-f", action="store_true", help="Force re-cropping even if panels exist")

    # tts
    p_tts = subparsers.add_parser("tts", help="Generate vocal audio via IndexTTS-2.5 from narration.json")
    p_tts.add_argument("--project", "-p", required=True, help="Project name")
    p_tts.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_tts.add_argument("--voice", "-v", required=False, default=None, help="Override reference speaker WAV path")
    p_tts.add_argument("--force", "-f", action="store_true", help="Force re-synthesis of all panels")

    # mix
    p_mix = subparsers.add_parser("mix", help="Mix narration, apply edge fades, BGM, and normalize")
    p_mix.add_argument("--project", "-p", required=True, help="Project name")
    p_mix.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_mix.add_argument("--bgm", "-b", required=False, default=None, help="Override background music audio path")

    # render
    p_rnd = subparsers.add_parser("render", help="Render final recap MP4 video")
    p_rnd.add_argument("--project", "-p", required=True, help="Project name")
    p_rnd.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_rnd.add_argument("--force", "-f", action="store_true", help="Force re-rendering video")

    # status
    p_stat = subparsers.add_parser("status", help="Inspect chapter production status")
    p_stat.add_argument("--project", "-p", required=True, help="Project name")
    p_stat.add_argument("--chapter", "-c", required=True, help="Chapter number")

    args = parser.parse_args()
    config = RemangaConfig.load()

    try:
        if args.command in ("interactive", None):
            run_interactive_pipeline()
        elif args.command == "setup-models":
            mgr = ModelManager(config.tts.model_dir, config.tts.hf_repo_id)
            mgr.ensure_model()
        elif args.command == "download":
            dl = MangaDexDownloader(config.downloader)
            dl.download_chapter(args.url, args.chapter, args.project)
        elif args.command == "crop":
            cropper = CoordinateCropper(config.cropper)
            cropper.crop_chapter_from_json(args.project, args.chapter, force=args.force)
        elif args.command == "tts":
            tts = TTSEngine(config.tts, config.audio)
            tts.generate_narration_audio(args.project, args.chapter, voice_override=args.voice, interactive=True, force=args.force)
        elif args.command == "mix":
            mixer = AudioProcessor(config.audio)
            mixer.mix_master_audio(args.project, args.chapter, bgm_override=args.bgm, interactive=True)
        elif args.command == "render":
            renderer = VideoRenderer(config.system, config.video)
            renderer.render_video(args.project, args.chapter, force=args.force)
        elif args.command == "status":
            display_status(args.project, args.chapter)
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()