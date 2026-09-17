"""The `remanga` command line. With no command, the menus.

    remanga download -p NAME -c 1-5 [--url MANGADEX_URL]
    remanga pdf      -p NAME -c 1-5
    remanga video    -p NAME -c 1-5 [--force]
    remanga chapters -p NAME
    remanga setup

Exit status: 0 done, 1 failed, 130 stopped with Ctrl+C."""

from __future__ import annotations

import argparse
import sys

from remanga.console import console, err_console, escape as _esc
from remanga.tui import PromptExit

EXIT_INTERRUPTED = 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="remanga", description=__doc__.splitlines()[0],
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    def with_project(name: str, help_text: str, chapters: bool = True) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_text, description=help_text)
        p.add_argument("--project", "-p", required=True, help="project name (projects/<name>/)")
        if chapters:
            p.add_argument("--chapters", "-c", default="all",
                           help="a chapter (3), a range (1-5), several (1-5,8), or 'all' (default)")
        return p

    sub.add_parser("interactive", help="the menus (the default)")
    d = with_project("download", "Download chapters from MangaDex (re-verifies ones already here)")
    d.add_argument("--url", help="MangaDex URL, ID or title - needed once per project, then remembered")
    d.add_argument("--force", action="store_true", help="delete the pages and download them again")
    with_project("pdf", "Make each chapter's PDF of pages to give to the LLM, with prompts/narration.md")
    v = with_project("video", "Make each chapter's video from the narration pasted into narration.json")
    v.add_argument("--force", action="store_true", help="narrate, mix and render again from scratch")
    with_project("chapters", "Show where each chapter is", chapters=False)
    sub.add_parser("setup", help="install Kokoro-82M (its environment and weights)")
    return parser


def _run(args: argparse.Namespace) -> None:
    from remanga import workflow
    from remanga.config import RemangaConfig

    if args.command in (None, "interactive"):
        from remanga.wizard import run_wizard

        run_wizard()
        return
    if args.command == "setup":
        setup()
        return

    config = RemangaConfig.load().for_project(args.project)
    if args.command == "chapters":
        from remanga.wizard import show_chapters

        show_chapters(args.project)
        return
    if args.command == "download":
        available = [entry["chapter"] for entry in workflow.mangadex_chapters(args.project, config, args.url)]
        chapters = workflow.select_chapters(args.chapters, available)
        workflow.download(args.project, chapters, config, url=args.url, force=args.force)
        return

    chapters = workflow.select_chapters(args.chapters, workflow.local_chapters(args.project))
    if not chapters:
        raise ValueError(f"No downloaded chapter matches '{args.chapters}'.")
    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        if args.command == "pdf":
            workflow.make_pdf(args.project, chapter, config)
        else:
            workflow.make_video(args.project, chapter, config, force=args.force)


def setup() -> None:
    """Kokoro's environment and weights, ready before the first video."""
    from remanga.audio.synth import create_synthesizer
    from remanga.config import RemangaConfig
    from remanga.tool_envs import provision

    if provision(["kokoro"], None):
        raise RuntimeError("Installing Kokoro's environment failed - see the messages above.")
    config = RemangaConfig.load()
    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    console.print("[bold green]✓ Kokoro-82M is installed and ready.[/]")


def main() -> None:
    args = build_parser().parse_args()
    try:
        _run(args)
    except PromptExit:
        console.print("\n[dim]Bye.[/]")
    except KeyboardInterrupt:
        err_console.print("\n[yellow]Stopped. Run it again to carry on where it left off.[/]")
        sys.exit(EXIT_INTERRUPTED)
    except EOFError:
        err_console.print("\n[yellow]Input ended before the prompt was answered - stopping here.[/]")
        sys.exit(1)
    except Exception as error:
        err_console.print(f"[bold red]Error:[/] {_esc(str(error))}")
        sys.exit(1)


if __name__ == "__main__":
    main()
