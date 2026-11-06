"""The `remanga` command line. With no command, the menus.

    remanga brief    WORDS...                   (a few words -> global/brief/brief_prompt.md for the LLM)
    remanga brief-from-reply [--reply FILE]     (its reply -> a manga found, its chapters downloaded, a new voice)
    remanga new      URL                         (MangaDex or comix.to; names the project after the manga)
    remanga download -p NAME [-c 1-5]           (no -c: shows the site's chapter list)
    remanga mark     -p NAME -c 1-5             (the Panel Marker web UI)
    remanga crop-pdf -p NAME -c 1-5             (the pages with MAGI's boxes, for the LLM with prompts/crop.md)
    remanga marks-from-reply -p NAME -c 1-5     (the LLM's crop_reply.txt made the panel marks; panels cut)
    remanga write    -p NAME -c 1               (write the narration yourself)
    remanga review   -p NAME -c 1               (flag what the LLM got wrong)
    remanga pdf      -p NAME -c 1-5
    remanga video    -p NAME -c 1-5 [--force | --remix]   (--remix: new music/sound, same narration)
    remanga long     -p NAME -c 1-5 [--from-source | --delete]   (one video of several chapters)
    remanga long     -p NAME                    (the long videos made so far)
    remanga upload   -p NAME                    (restamp every video's title, description, thumbnail)
    remanga upload-pdf -p NAME -c 1-3           (the panels and story for the LLM, with prompts/upload.md)
    remanga upload-from-reply -p NAME           (the LLM's upload_reply.txt made the titles, thumbnails, description)
    remanga chapters -p NAME
    remanga delete   -p NAME [--yes]            (the whole project, for good - asks you to type its name)
    remanga queue    [--run]                    (the job queue the menus fill; --run runs it)
    remanga voices                              (one line in every voice, to listen to)
    remanga plugins                             (what is installed: engines, layouts, sources, ...)
    remanga helper   [--set-key | --install]    (the Firefox helper for comix.to: install it for good)
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

    b = sub.add_parser("brief", help="Write the prompt file that has an LLM find a manga for what you describe and "
                                     "design a Drama 3 voice and chapter range for it")
    b.add_argument("reference", nargs="+", help='what you are after, e.g. "isaki, villain, yandere white hair waifu"')
    br = sub.add_parser("brief-from-reply", help="Use the LLM's brief reply (global/brief/brief_reply.txt): check "
                                                  "the manga on MangaDex, save the new voice, make the project, "
                                                  "download the chapters")
    br.add_argument("--reply", metavar="FILE", help="read the reply from this file instead")
    br.add_argument("--no-download", action="store_true", help="make the project and the voice, download nothing")
    sub.add_parser("interactive", help="the menus (the default)")
    n = sub.add_parser("new", help="Create a project from a MangaDex or comix.to link (or a MangaDex title) - named "
                                       "after the manga")
    n.add_argument("source", help="MangaDex URL, ID or a title to search; or a comix.to link (downloads "
                                   "through your Firefox)")
    d = with_project("download", "Download chapters from the manga's site (re-verifies ones already here); "
                                 "without -c, list its chapters", chapters=False)
    d.add_argument("--chapters", "-c", default=None,
                   help="a chapter (3), a range (1-5), several (1-5,8), 'new' (every chapter not downloaded) or "
                        "'all'; leave out to see the list")
    d.add_argument("--url", help="the manga's link (MangaDex URL/ID/title, or comix.to) - needed once per project, "
                                 "then remembered")
    d.add_argument("--force", action="store_true", help="delete the pages and download them again")
    with_project("mark", "Open the Panel Marker web UI for these chapters - MAGI v3 finds the panels, you fix "
                         "them, saving writes crops.json")
    with_project("crop-pdf", "Make each chapter's crop PDF - its pages with the panels MAGI v3 finds drawn and "
                             "numbered - to give to the LLM with prompts/crop.md")
    with_project("marks-from-reply", "Save the panel marks from the LLM's crop reply pasted into "
                                     "chapters/chapter_N/crop_reply.txt, then cut the panels")
    with_project("marks-from-panels", "Mark long-strip chapters from panels already cut (import_zip/NN/panels): "
                                      "each is found in the pages by its pixels, no browser needed")
    with_project("narration-from-zip", "Write narration.json from an older remanga's zip narration (import_zip/NN), "
                                      "checked against the pages and the cut panels first")
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
    so = with_project("sources", "The sites this manga is downloaded from, first = preferred: each chapter comes "
                                 "from the one that downloaded it, else the first that has its pages",
                      chapters=False)
    so.add_argument("--add", metavar="LINK", help="add the same manga on another site (a MangaDex or comix.to link)")
    so.add_argument("--remove", metavar="SOURCE", help="remove a source by name (mangadex, comix)")
    dp = with_project("delete", "Delete the whole project for good - pages, marks, narration, audio, videos - "
                                "and its jobs in the queue", chapters=False)
    dp.add_argument("--yes", action="store_true", help="don't ask (type the name) first")
    with_project("upload", "Write every finished video's title, description and thumbnail again from the "
                           "project's upload/ folder (after editing it)", chapters=False)
    with_project("upload-pdf", "Make the upload PDF - these chapters' largest panels, their colour pages and the "
                               "story - to give to the LLM with prompts/upload.md for three titles and thumbnails "
                               "and a description")
    with_project("upload-from-reply", "Write the upload set from the LLM's reply pasted into "
                                      "upload/upload_reply.txt, then stamp it beside every video", chapters=False)
    qp = sub.add_parser("queue", help="Show the job queue (filled from the menus: a chapter's Add to queue)")
    qp.add_argument("--run", action="store_true", help="run every job not done yet, one after another")
    sub.add_parser("voices", help="Read one line in each of the narrator engine's voices, into "
                                  "global/voice/samples/")
    sub.add_parser("plugins", help="List the plug-ins: narrator engines, tools, layouts, sources and jobs")
    hp = sub.add_parser("helper", help="The remanga helper extension for Firefox (comix.to downloads): its state, "
                                       "and installing it for good")
    hp.add_argument("--set-key", action="store_true", help="save your addons.mozilla.org API key (asked for)")
    hp.add_argument("--install", action="store_true",
                    help="have Mozilla sign the helper (private, unlisted) and open it in Firefox to install")
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
    if args.command == "helper":
        from remanga.plugins.browser.commands import helper_command

        helper_command(set_key=args.set_key, install=args.install)
        return
    if args.command == "voices":
        from remanga.config import RemangaConfig as _Config

        workflow.sample_voices(_Config.load())
        return
    if args.command == "brief":
        prompt = workflow.make_brief_prompt(" ".join(args.reference))
        console.print(f"[bold green]✓ Prompt:[/] {_esc(str(prompt.resolve()))}\n"
                      "Give that file to the LLM (one with web access to MangaDex works best), then paste its one "
                      f"JSON reply into {_esc(str(workflow.brief.brief_reply_path().resolve()))} and run:\n"
                      "  ./run.sh brief-from-reply")
        return
    if args.command == "brief-from-reply":
        from remanga.brief_plan import BriefReplyError

        try:
            workflow.print_brief_result(workflow.apply_brief(workflow.read_reply_text(args.reply),
                                                              RemangaConfig.load(),
                                                              download_chapters=not args.no_download))
        except BriefReplyError as error:
            err_console.print(f"[bold red]✗[/] {_esc(str(error))}")
            sys.exit(1)
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

    if args.command == "delete":
        size = workflow.project_footprint(args.project)
        console.print(f"[bold red]Delete {_esc(args.project)} for good?[/] {size['chapters']} chapter(s), "
                      f"{size['videos']} video(s), {size['files']} files, {size['bytes'] / 1e6:,.1f} MB.")
        if not args.yes and input(f"Type {args.project} to delete it: ").strip() != args.project:
            console.print("[yellow]Kept - nothing deleted.[/]")
            return
        console.print(f"[green]Deleted[/] {_esc(str(workflow.delete_project(args.project)))}")
        return

    config = RemangaConfig.load()
    if args.command == "sources":
        from remanga import sources

        if args.add:
            sources.add_source(args.project, args.add, config)
        if args.remove:
            sources.remove_source(args.project, args.remove)
        for i, (source, entry) in enumerate(sources.project_sources(args.project), start=1):
            link = entry["manga_url"] or entry["manga_id"]
            console.print(f"  {i}. {_esc(source.display_name):<26} [dim]{_esc(link)}[/]")
        return
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
    if args.command == "upload-from-reply":
        workflow.print_upload_result(workflow.upload_from_reply(args.project, config))
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
    if args.command == "marks-from-panels":
        done = [c for c in chapters if workflow.marks_from_panels(args.project, c)]
        console.print(f"{len(done)} of {len(chapters)} chapters marked.")
        return
    if args.command == "marks-from-reply":
        from remanga.crop_plan import CropReplyError

        done = []
        for chapter in chapters:
            console.print(f"\n[bold cyan]Chapter {chapter}[/]")
            try:
                workflow.print_reply_result(chapter, workflow.marks_from_reply(args.project, chapter, config))
                done.append(chapter)
            except (CropReplyError, FileNotFoundError) as error:
                err_console.print(f"[bold red]✗[/] {_esc(str(error))}")
        console.print(f"\n{len(done)} of {len(chapters)} chapters marked from their crop replies.")
        if len(done) < len(chapters):
            sys.exit(1)
        return
    if args.command == "narration-from-zip":
        from remanga.workflow.narration_import import import_chapter

        done = [c for c in chapters if import_chapter(args.project, c, config)]
        console.print(f"{len(done)} of {len(chapters)} chapters narrated.")
        return
    if args.command == "upload-pdf":
        workflow.print_upload_handoff(workflow.make_upload_pdf(args.project, chapters, config))
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
        elif args.command == "crop-pdf":
            workflow.print_crop_handoff(workflow.make_crop_pdf(args.project, chapter, config))
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
