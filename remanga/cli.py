"""The `remanga` command line. With no command, the menus.

    remanga new      MANGADEX_URL                (names the project after the manga)
    remanga download -p NAME [-c 1-5]           (no -c: shows MangaDex's chapter list)
    remanga mark     -p NAME -c 1-5             (the Panel Marker web UI)
    remanga pdf      -p NAME -c 1-5
    remanga video    -p NAME -c 1-5 [--force]
    remanga chapters -p NAME
    remanga setup

Exit status: 0 done, 1 failed, 130 stopped with Ctrl+C."""

from __future__ import annotations

import argparse
import sys

from remanga.console import console, err_console, escape as _esc

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
    n = sub.add_parser("new", help="Create a project from a MangaDex URL, ID or title - named after the manga")
    n.add_argument("source", help="MangaDex URL, ID, or a title to search")
    d = with_project("download", "Download chapters from MangaDex (re-verifies ones already here); without -c, "
                                 "list MangaDex's chapters", chapters=False)
    d.add_argument("--chapters", "-c", default=None,
                   help="a chapter (3), a range (1-5), several (1-5,8), 'new' (every chapter not downloaded) or "
                        "'all'; leave out to see the list")
    d.add_argument("--url", help="MangaDex URL, ID or title - needed once per project, then remembered")
    d.add_argument("--force", action="store_true", help="delete the pages and download them again")
    with_project("mark", "Open the Panel Marker web UI for these chapters - MAGI v3 finds the panels, you fix "
                         "them, saving writes crops.json")
    with_project("pdf", "Make each chapter's PDF of panels to give to the LLM, with prompts/narration.md")
    v = with_project("video", "Make each chapter's video from the narration pasted into narration.json")
    v.add_argument("--force", action="store_true", help="narrate, mix and render again from scratch")
    with_project("chapters", "Show where each chapter is", chapters=False)
    sub.add_parser("setup", help="install Kokoro-82M and MAGI v3 (their environments and weights)")
    return parser


def _run(args: argparse.Namespace) -> None:
    from remanga import workflow
    from remanga.config import RemangaConfig

    if args.command in (None, "interactive"):
        from remanga.ui import run

        run()
        return
    if args.command == "setup":
        setup()
        return
    if args.command == "new":
        workflow.create_project(args.source, RemangaConfig.load())
        return

    config = RemangaConfig.load().for_project(args.project)
    if args.command == "chapters":
        chapters = workflow.local_chapters(args.project)
        if not chapters:
            console.print("[yellow]No chapters downloaded yet.[/]")
        for chapter in chapters:
            console.print(f"  chapter {chapter:>6}  {workflow.chapter_state(args.project, chapter)}")
        return
    if args.command == "download":
        listing = workflow.mangadex_chapters(args.project, config, args.url)
        if not args.chapters:
            workflow.print_chapter_list(listing)
            console.print("[dim]Download with -c: a chapter, a range (1-5), 'new' or 'all'.[/]")
            return
        if args.chapters.strip().lower() == "new":
            chapters = [entry["chapter"] for entry in listing if entry["status"] != "downloaded"]
        else:
            chapters = workflow.select_chapters(args.chapters, [entry["chapter"] for entry in listing])
        if not chapters:
            console.print("[green]Nothing to download - you have every chapter asked for.[/]")
            return
        workflow.download(args.project, chapters, config, url=args.url, force=args.force)
        return

    chapters = workflow.select_chapters(args.chapters, workflow.local_chapters(args.project))
    if not chapters:
        raise ValueError(f"No downloaded chapter matches '{args.chapters}'.")
    if args.command == "mark":
        workflow.mark(args.project, chapters, config)
        return

    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        if args.command == "pdf":
            workflow.print_handoff(workflow.make_pdf(args.project, chapter, config))
        else:
            workflow.make_video(args.project, chapter, config, force=args.force)


def setup() -> None:
    """The two models' environments and weights, ready before the first video:
    Kokoro-82M for the narration and MAGI v3 for finding panels."""
    from remanga.audio.synth import create_synthesizer
    from remanga.config import RemangaConfig
    from remanga.tool_envs import provision
    from remanga.webui.magi_assist import ensure_weights_downloaded

    failed = provision(["kokoro", "magi"], None)
    if "kokoro" in failed:
        raise RuntimeError("Installing Kokoro's environment failed - see the messages above.")
    config = RemangaConfig.load()
    create_synthesizer(config.tts, config.audio).model_manager.ensure_model()
    console.print("[bold green]✓ Kokoro-82M is installed and ready.[/]")
    if "magi" in failed:
        console.print("[yellow]MAGI v3's environment failed to install - the Panel Marker still works, with the "
                      "panels marked by hand.[/]")
        return
    ensure_weights_downloaded(config.marker)


def main() -> None:
    args = build_parser().parse_args()
    try:
        _run(args)
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
