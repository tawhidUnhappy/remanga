from __future__ import annotations

import argparse
import signal
import sys

from rich.prompt import Confirm

from remanga import reset
from remanga.audio import AudioProcessor, TTSEngine
from remanga.config import RemangaConfig
from remanga.console import console
from remanga.cropper import CoordinateCropper
from remanga.downloader import MangaDexDownloader
from remanga.full_recap import FullRecapCompiler, chapter_sort_key
from remanga.models import ModelManager
from remanga.setup_wizard import run_setup_wizard
from remanga.status import render_status_panel
from remanga.video import VideoRenderer
from remanga.webui import launch_and_wait as launch_panel_marker
from remanga.wizard import run_interactive_pipeline


def graceful_sigint_handler(signum, frame):
    """Handle Ctrl+C gracefully without traceback noise."""
    console.print("\n\n[bold yellow]👋 Production paused. You can resume at any time![/]")
    sys.exit(0)


signal.signal(signal.SIGINT, graceful_sigint_handler)


def main():
    parser = argparse.ArgumentParser(description="remanga: Lightweight, Self-Contained Manga Recap Production Pipeline")
    subparsers = parser.add_subparsers(dest="command")

    # interactive wizard
    subparsers.add_parser("interactive", help="Start interactive step-by-step production wizard")

    # setup configuration
    subparsers.add_parser("setup-config", help="Walkthrough configuration setup (voice, BGM, resolution, vision format, blur)")

    # setup models
    subparsers.add_parser("setup-models", help="Verify and download model weights with SHA-256 verification")

    # download
    p_dl = subparsers.add_parser("download", help="Download manga chapter from MangaDex")
    p_dl.add_argument("--project", "-p", required=True, help="Project name")
    p_dl.add_argument("--chapter", "-c", required=True, help="Chapter number (e.g. 1 or 01)")
    p_dl.add_argument("--url", "-u", required=False, default=None, help="Manga title or MangaDex URL/UUID (optional if saved)")

    # mark
    p_mark = subparsers.add_parser("mark", help="Launch the Panel Marker web UI to mark panels (writes crops.json)")
    p_mark.add_argument("--project", "-p", required=True, help="Project name")
    p_mark.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # crop
    p_crop = subparsers.add_parser("crop", help="Crop panels using coordinates in crops.json and package sheets.zip or panels.zip")
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

    # full-recap
    p_full = subparsers.add_parser(
        "full-recap",
        help="Compile every chapter of a project into ONE continuous recap video "
             "(single BGM pass, single loudnorm pass - no per-chapter restarts/joins)",
    )
    p_full.add_argument("--project", "-p", required=True, help="Project name")
    p_full.add_argument(
        "--chapters", "-c", required=False, default=None,
        help="Comma-separated chapter numbers to include, in any order (default: every chapter found, in order)",
    )
    p_full.add_argument("--force", "-f", action="store_true", help="Force a full recompile even if already compiled")

    # status
    p_stat = subparsers.add_parser("status", help="Inspect chapter production status")
    p_stat.add_argument("--project", "-p", required=True, help="Project name")
    p_stat.add_argument("--chapter", "-c", required=True, help="Chapter number")

    # restart
    p_restart = subparsers.add_parser("restart", help="Wipe a chapter back to just its downloaded pages so it can be reprocessed from scratch")
    p_restart.add_argument("--project", "-p", required=True, help="Project name")
    p_restart.add_argument("--chapter", "-c", required=True, help="Chapter number")
    p_restart.add_argument("--force", "-f", action="store_true", help="Skip the confirmation prompt")
    p_restart.add_argument(
        "--mode", "-m", choices=["hard", "marks_only", "remark", "soft"], default="hard",
        help="hard (default): keep only downloaded pages. marks_only: also keep crops.json, "
             "narration.json still gets wiped/emptied. remark: same deletion as marks_only, then "
             "reopens the Panel Marker web UI (pre-loaded with the kept marks) so you can adjust "
             "them. soft: also keep crops.json, panels/, and narration.json.",
    )
    p_restart.add_argument("--no-reverify", action="store_true", help="Skip re-checking/re-fetching downloaded pages afterward")

    args = parser.parse_args()
    config = RemangaConfig.load()

    try:
        if args.command in ("interactive", None):
            run_interactive_pipeline()
        elif args.command == "setup-config":
            run_setup_wizard(config)
        elif args.command == "setup-models":
            mgr = ModelManager(config.tts.model_dir, config.tts.hf_repo_id)
            mgr.ensure_model()
            from remanga.webui.magi_assist import ensure_weights_downloaded
            ensure_weights_downloaded(config.marker)
        elif args.command == "download":
            dl = MangaDexDownloader(config.downloader)
            dl.download_chapter(args.url, args.chapter, args.project)
        elif args.command == "mark":
            launch_panel_marker(args.project, args.chapter, config.marker)
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
        elif args.command == "full-recap":
            chapters = None
            if args.chapters:
                chapters = sorted({c.strip() for c in args.chapters.split(",") if c.strip()}, key=chapter_sort_key)
            compiler = FullRecapCompiler(config)
            compiler.compile_full_manga(args.project, force=args.force, chapters=chapters)
        elif args.command == "status":
            console.print(render_status_panel(args.project, args.chapter))
        elif args.command == "restart":
            # "remark" isn't a real reset.py mode - it deletes exactly like
            # marks_only, then additionally reopens the Panel Marker below.
            deletion_mode = "marks_only" if args.mode == "remark" else args.mode
            candidates = reset.restart_candidates(args.project, args.chapter, mode=deletion_mode)
            kind = {"hard": "Restart", "marks_only": "Marks-only restart", "remark": "Re-mark restart", "soft": "Soft restart"}[args.mode]
            kept = {
                "hard": "downloaded pages",
                "marks_only": "downloaded pages and crops.json (narration.json gets emptied, not kept)",
                "remark": "downloaded pages and crops.json (narration.json gets emptied, not kept)",
                "soft": "downloaded pages, crops.json, panels/, and narration.json",
            }[args.mode]
            if not candidates:
                console.print(f"[dim]Nothing to delete for a {kind.lower()} - everything it would keep is already all that's here.[/]")
            else:
                console.print(f"[bold red]{kind}: the following will be permanently deleted:[/]")
                for c in candidates:
                    console.print(f"  [dim]- {c}[/]")
                console.print(f"[dim]Kept: {kept}.[/]")
                if args.force or Confirm.ask(
                    f"[bold red]Confirm: permanently delete these {len(candidates)} item(s) for Chapter {args.chapter}? This cannot be undone.[/]",
                    default=False,
                ):
                    reset.restart_chapter(args.project, args.chapter, mode=deletion_mode, reverify_downloads=not args.no_reverify)
                    console.print(f"[bold green]✓ Chapter {args.chapter} {kind.lower()} complete. Downloaded pages kept — ready to reprocess.[/]")
                    if args.mode == "remark":
                        console.print("[yellow]Reopening the Panel Marker - your existing marks are pre-loaded (MAGI won't touch them).[/]")
                        launch_panel_marker(args.project, args.chapter, config.marker)
                        console.print(f"[bold green]✓ Marks for Chapter {args.chapter} updated and saved.[/]")
                else:
                    console.print("[dim]Restart cancelled.[/]")
    except Exception as e:
        console.print(f"[bold red]Error:[/] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
