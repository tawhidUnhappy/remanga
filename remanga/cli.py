"""The `remanga` command line. With no command, the menus.

    remanga new      MANGADEX_URL                (names the project after the manga)
    remanga download -p NAME [-c 1-5]           (no -c: shows MangaDex's chapter list)
    remanga mark     -p NAME -c 1-5             (the Panel Marker web UI)
    remanga write    -p NAME -c 1               (write the narration yourself)
    remanga review   -p NAME -c 1               (flag what the LLM got wrong)
    remanga pdf      -p NAME -c 1-5
    remanga video    -p NAME -c 1-5 [--force | --remix]   (--remix: new music/sound, same narration)
    remanga long     -p NAME -c 1-5 [--from-source | --delete]   (one video of several chapters)
    remanga long     -p NAME                    (the long videos made so far)
    remanga upload   -p NAME                    (restamp every video's title, description, thumbnail)
    remanga chapters -p NAME
    remanga queue    [--run]                    (the job queue the menus fill; --run runs it)
    remanga voices                              (one line in every voice, to listen to)
    remanga plugins                             (what is installed: engines, layouts, sources, ...)
    remanga setup    [--tool kokoro]            (a tool plug-in's own setup: environment + weights)

Exit status: 0 done, 1 failed, 130 stopped with Ctrl+C."""

from __future__ import annotations

import argparse
import sys

from remanga.cli_commands import run_queue, setup, show_plugins, show_queue
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
    with_project("write", "Write the narration yourself, panel by panel, in the browser")
    with_project("review", "Go through a chapter's narration in the browser and flag what is wrong")
    with_project("pdf", "Make each chapter's PDF of panels to give to the LLM, with prompts/narration.md")
    v = with_project("video", "Make each chapter's video from the narration pasted into narration.json")
    v.add_argument("--force", action="store_true", help="narrate, mix and render again from scratch")
    v.add_argument("--remix", action="store_true",
                   help="keep the narration clips; only mix and render again (after a music or sound change)")
    v.add_argument("--from-source", action="store_true",
                   help="delete everything but the pages, panel marks and narration.json, then make it all again")
    v.add_argument("--audio-only", action="store_true",
                   help="narrate, mix and render as usual, then keep only the raw narration clips")
    lv = with_project("long", "One video of several chapters: their videos joined, the intro once in front; "
                              "without -c, list the long videos made", chapters=False)
    lv.add_argument("--chapters", "-c", default=None, help="a range (1-5), several (1-5,8), or 'all'")
    lv.add_argument("--from-source", action="store_true",
                    help="remake every chapter from its pages, panel marks and narration.json first, then join")
    lv.add_argument("--delete", action="store_true", help="delete the long video of these chapters")
    with_project("chapters", "Show where each chapter is", chapters=False)
    with_project("upload", "Write every finished video's title, description and thumbnail again from the "
                           "project's upload/ folder (after editing it)", chapters=False)
    qp = sub.add_parser("queue", help="Show the job queue (filled from the menus: a chapter's Add to queue)")
    qp.add_argument("--run", action="store_true", help="run every job not done yet, one after another")
    sub.add_parser("voices", help="Read one line in each of the narrator engine's voices, into "
                                  "global/voice/samples/")
    sub.add_parser("plugins", help="List the plug-ins: narrator engines, tools, layouts, sources and jobs")
    su = sub.add_parser("setup", help="run tool plug-ins' setup (environment + weights); default: the chosen "
                                      "narrator and MAGI v3")
    su.add_argument("--tool", action="append", default=[], help="only this tool (repeatable): see `plugins`")
    return parser


def _run(args: argparse.Namespace) -> None:
    from remanga import workflow
    from remanga.config import RemangaConfig

    if args.command in (None, "interactive"):
        from remanga.ui import run

        run()
        return
    if args.command == "setup":
        setup(args.tool or None)
        return
    if args.command == "plugins":
        show_plugins()
        return
    if args.command == "voices":
        from remanga.config import RemangaConfig as _Config

        workflow.sample_voices(_Config.load())
        return
    if args.command == "new":
        workflow.create_project(args.source, RemangaConfig.load())
        return
    if args.command == "queue":
        if args.run:
            run_queue(RemangaConfig.load())
        else:
            show_queue()
        return

    config = RemangaConfig.load()
    if args.command == "chapters":
        chapters = workflow.local_chapters(args.project)
        if not chapters:
            console.print("[yellow]No chapters downloaded yet.[/]")
        for chapter in chapters:
            console.print(f"  chapter {chapter:>6}  {workflow.chapter_state(args.project, chapter)}")
        return
    if args.command == "upload":
        for path in workflow.stamp_all(args.project):
            console.print(f"  {_esc(str(path))}")
        return
    if args.command == "long" and not args.chapters:
        made = workflow.long_videos(args.project)
        if not made:
            console.print("[yellow]No long videos yet - make one with -c 1-5.[/]")
        for video in made:
            console.print(f"  ch{_esc(video['label']):<12} {_esc(str(video['video'] or '(no finished video)'))}")
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
    if args.command == "long":
        if args.delete:
            label = workflow.long_label(args.project, chapters)
            removed = workflow.delete_long_video(args.project, label)
            console.print(f"Deleted the long video of chapters {_esc(label)}" if removed
                          else f"[yellow]There is no long video of chapters {_esc(label)}.[/]")
        else:
            workflow.make_long_video(args.project, chapters, config, from_source=args.from_source)
        return
    if args.command in ("write", "review"):
        step = workflow.write_narration if args.command == "write" else workflow.review_narration
        for chapter in chapters:
            step(args.project, chapter, config)
        return

    for chapter in chapters:
        console.print(f"\n[bold cyan]Chapter {chapter}[/]")
        if args.command == "pdf":
            workflow.print_handoff(workflow.make_pdf(args.project, chapter, config))
        elif getattr(args, "from_source", False):
            workflow.remake_from_source(args.project, chapter, config)
        elif getattr(args, "remix", False):
            workflow.remix_video(args.project, chapter, config)
        else:
            workflow.make_video(args.project, chapter, config, force=args.force,
                                audio_only=getattr(args, "audio_only", False))


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
