"""The chapter menu: what can be done to the chosen chapters, offered only when
it applies, and what each choice does - a mixin of the chapters screen
(chapters.py is the table and its keys, chapter_work.py the work)."""

from __future__ import annotations

from textual import work

from remanga import workflow
from remanga.ui.dialogs import Choice, Confirm
from remanga.workflow.queue import add_jobs, jobs

BUILT_IN = ("download", "pdf", "video", "remix", "reaudio", "source")


class ChapterMenu:
    """The chapters screen's menu. Mixed in; `self` is the ChaptersScreen."""

    async def queue_chapters(self, project: str, chapters: list[str], on_disk: bool, narrated: bool,
                             marked: bool, title: str) -> None:
        """Adds a job per chapter to the queue - only what runs unattended,
        and only what applies to these chapters now."""
        wanted = ["download"] if not on_disk else (
            ["pdf", "video"] + (["remix", "reaudio"] if narrated else []) + (["source"] if marked else [])
            + ["download"])
        # Jobs a plug-in of your own adds come after the built-in ones.
        known = jobs()
        wanted = [a for a in wanted if a in known] + [a for a in known if on_disk and a not in BUILT_IN]
        action = await self.app.push_screen_wait(Choice(
            f"Queue for {title.lower()}", [(*known[a], a) for a in wanted],
            note="Marking and the narration passes need you at the browser, so they cannot be queued.",
            danger=["source"]))
        if action is None:
            return
        added = add_jobs(project, chapters, action)
        skipped = len(chapters) - added
        self.notify(f"Queued {known[action][0]} for {added} chapter(s)"
                    + (f" ({skipped} already waiting)" if skipped else "") + " - j opens the queue.")

    @work(exclusive=True)
    async def actions(self, chosen: list[dict]) -> None:
        project, config = self.project, self.config
        chapters = [row["chapter"] for row in chosen]
        on_disk = all(workflow.page_files(project, ch) for ch in chapters)
        some_on_disk = any(workflow.page_files(project, ch) for ch in chapters)
        title = f"Chapter {chapters[0]}" if len(chapters) == 1 else f"{len(chapters)} chapters"
        options = []
        narrated = False
        if not on_disk:
            options.append(("Download", "fetch the pages", "download"))
        else:
            options.append(("Mark panels", "open the Panel Marker in the browser - MAGI finds them, you "
                            "fix them", "mark"))
            options += [("Make PDF", "the panels, to give to the LLM with the prompt", "pdf"),
                        ("Write narration", "type it yourself instead, panel by panel, in the browser",
                         "write"),
                        ("Review narration", "go through what the LLM wrote and flag what is wrong",
                         "review"),
                        ]
            narrated = any(workflow.has_audio(project, ch) for ch in chapters)
            if narrated:
                # First, because it is what is wanted after almost any change: the
                # narration is the slow, costly part and nothing but a changed
                # narration.json needs it made again.
                options.append(("Rebuild video", "keeps the narration - remakes the music, intro and video "
                                "(about a minute)", "remix"))
            options.append(("Make video", "narrates the whole chapter from narration.json (the slow part), "
                            "then makes the video" + (" - replaces the narration there now" if narrated else ""),
                            "video"))
            if len(chapters) > 1 or any(set(v["chapters"]) & set(chapters)
                                        for v in workflow.long_videos(project)):
                span = workflow.long_label(project, chapters) if len(chapters) > 1 else chapters[0]
                options.append(("Long video...", f"one video of chapters {span} - join their videos, make it "
                                "all from source, or delete one made before", "long"))
            if any(workflow.has_marks(project, ch) for ch in chapters):
                options.append(("Remake from source", "deletes everything but the pages, panel marks and "
                                "narration.json, then makes it all again", "source"))
            if narrated:
                options.append(("Narrate again, no video", "replaces the narration with a new one and "
                                "keeps only that - no mix or video", "reaudio"))
            options += [("Check pages", "fix any missing or broken page", "download"),
                        ("Re-download", "delete the pages and fetch them all again", "redownload")]
        options.append(("Add to queue", "line it up to run later with other chapters, from any "
                        "project - j opens the queue", "queue"))
        if some_on_disk:
            options += [("Delete chosen...", "pick from a list what to delete - marks, narration, audio, "
                         "video, ...", "pick"),
                        ("Reset", "delete the cut panels, PDF, narration, audio and video - the marks and "
                         "pages stay", "reset"),
                        ("Delete", "delete everything, pages included", "delete")]
        note = ", ".join(chapters) if len(chapters) > 1 else (chosen[0].get("title") or "")
        action = await self.app.push_screen_wait(Choice(title, options, note=note, danger=["pick", "reset", "delete"]))
        if action is None:
            return
        if action == "queue":
            await self.queue_chapters(project, chapters, on_disk, narrated,
                             any(workflow.has_marks(project, ch) for ch in chapters), title)
        elif action == "download":
            await self.download(chapters)
        elif action == "mark":
            await self.mark(chapters, config)
        elif action in ("write", "review"):
            await self.narration_pass(action, chapters, config)
        elif action == "redownload":
            if await self.app.push_screen_wait(Confirm("Re-download", f"Delete the pages of {title.lower()} and "
                                                       f"download them again?", yes="Re-download")):
                await self.download(chapters, force=True)
        elif action == "pdf":
            await self.make_pdfs(chapters, config)
        elif action == "video":
            if narrated and not await self.app.push_screen_wait(Confirm(
                    "Make video", f"{title} already has a narration. Make video narrates it all again - the "
                    f"slow part. To keep the narration and only remake the music, intro and video, choose "
                    f"Rebuild video instead.", yes="Narrate again")):
                return
            await self.make_videos(chapters, config)
        elif action == "source":
            if await self.app.push_screen_wait(Confirm(
                    "Remake from source", f"Delete everything made for {title.lower()} - the cut panels, the "
                    f"PDF, the narration audio and the video - keeping only the pages, the panel marks and "
                    f"narration.json, then cut, narrate (the slow part) and make the video again?",
                    yes="Remake from source", danger=True)):
                await self.make_videos(chapters, config, from_source=True)
        elif action == "long":
            await self.long_video(chapters, config)
        elif action == "remix":
            await self.remix_videos(chapters, config)
        elif action == "reaudio":
            if await self.app.push_screen_wait(Confirm(
                    "Narrate again, no video", f"Throw away the narration of {title.lower()} and narrate it all "
                    f"again (the slow part)? Only the new narration is kept; Rebuild video then makes the video "
                    f"from it.", yes="Narrate again")):
                await self.make_videos(chapters, config, force=True, audio_only=True)
        elif action == "pick":
            await self.delete_chosen(chapters, title)
        elif action in ("reset", "delete"):
            what = ("everything, pages and marks included" if action == "delete"
                    else "the cut panels, PDF, pasted narration, audio and video")
            if not await self.app.push_screen_wait(Confirm(
                    action.capitalize(), f"Delete {what} for {title.lower()}? The pasted narration can't be "
                    f"recovered.", yes=action.capitalize(), danger=True)):
                return
            for chapter in chapters:
                workflow.reset_chapter(project, chapter, delete_pages=action == "delete")
        self.marks.clear()
        self.fetch(refresh=False)
