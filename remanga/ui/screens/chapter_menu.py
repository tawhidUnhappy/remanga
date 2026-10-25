"""The chapter menu: what can be done to the chosen chapters, offered only when
it applies, and what each choice does - a mixin of the chapters screen
(chapters.py is the table and its keys, chapter_work.py the work)."""

from __future__ import annotations

from textual import work

from remanga import workflow
from remanga.store import versions as store_versions
from remanga.ui.dialogs import Choice, Confirm, Result
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
            if some_on_disk:
                options.append(("Check narration", "the downloaded ones' narration.json against their panels "
                                "and narrated audio - lists each mismatch, makes nothing", "check"))
        else:
            marked = any(workflow.has_marks(project, ch) for ch in chapters)
            options.append(("Mark panels", "open the marker in the browser - it finds them, you fix them; "
                            "only the marks are saved", "mark"))
            if marked:
                options += [("Remark panels", "throw the saved marks away and mark again - every panel is "
                             "proposed afresh", "remark"),
                            ("Create panels", "cut the marked panels out of the pages", "panels")]
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
            options.append(("Check narration", "every picked chapter's narration.json against its panels and "
                            "its narrated audio - lists each mismatch, makes nothing", "check"))
            if any(workflow.has_marks(project, ch) for ch in chapters):
                options.append(("Remake from source", "deletes everything but the pages, panel marks and "
                                "narration.json, then makes it all again", "source"))
            if narrated:
                options.append(("Narrate again, no video", "replaces the narration with a new one and "
                                "keeps only that - no mix or video", "reaudio"))
            if len(chapters) == 1:
                checked = workflow.page_check(project, chapters[0])
                options.append(("Page check " + checked["mark"], "how its pages were checked: every page there, "
                                "whole, and as many as the site says", "pagecheck"))
            options += [("Check pages", "fix any missing or broken page", "download"),
                        ("Re-download", "delete the pages and fetch them all again", "redownload")]
        if narrated:
            options.append(("Make video fresh", "everything made again from scratch - no take or video reused "
                            "from before - and kept as a new version beside the others; says at the end how it "
                            "compares with what was made before", "fresh"))
        if len(chapters) == 1:
            kept = store_versions.versions(project, chapters[0])
            if kept:
                options.append((f"Versions ({len(kept)})", "every video made of this chapter and what it was "
                                "made with - bring one back, nothing made again, or delete one", "versions"))
        options.append(("Add to queue", "line it up to run later with other chapters, from any "
                        "project - j opens the queue", "queue"))
        if some_on_disk:
            options += [("Delete chosen...", "pick from a list what to delete - marks, narration, audio, "
                         "video, ...", "pick"),
                        ("Reset", "delete the cut panels, PDF, narration, audio and video - the marks and "
                         "pages stay", "reset"),
                        ("Delete", "delete everything, pages included", "delete")]
        note = ", ".join(chapters) if len(chapters) > 1 else (chosen[0].get("title") or "")
        action = await self.app.push_screen_wait(Choice(title, options, note=note,
                                                        danger=["remark", "pick", "reset", "delete"]))
        if action is None:
            return
        if action == "versions":
            from remanga.ui.screens.versions import VersionsScreen

            await self.app.push_screen_wait(VersionsScreen(project, chapters[0], self.path))
        elif action == "queue":
            await self.queue_chapters(project, chapters, on_disk, narrated,
                             any(workflow.has_marks(project, ch) for ch in chapters), title)
        elif action == "download":
            await self.download(chapters)
        elif action == "pagecheck":
            checked = workflow.page_check(project, chapters[0])
            await self.app.push_screen_wait(Result(
                self.path, f"{title}: page check", [*checked["lines"], "",
                "Check pages checks them all again on disk (and fetches anything missing or broken)."],
                ok=checked["mark"] == "✓"))
        elif action == "mark":
            await self.mark(chapters, config)
        elif action == "remark":
            if await self.app.push_screen_wait(Confirm(
                    "Remark panels", f"Delete the panel marks of {title.lower()} (and the panels cut from them) "
                    f"and mark again from scratch? The marker proposes every panel afresh.",
                    yes="Remark", danger=True)):
                await self.mark(chapters, config, again=True)
        elif action == "panels":
            await self.create_panels(chapters, config)
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
                    "Make video", f"{title} already has a narration. Make video makes it all again from "
                    f"narration.json - but every take and video made before with the same text and settings "
                    f"comes back from the store instead of being made again, and what is there now is kept as "
                    f"a version (Versions). To only remake the music, intro and video, choose Rebuild video.",
                    yes="Make video")):
                return
            await self.make_videos(chapters, config)
        elif action == "fresh":
            if await self.app.push_screen_wait(Confirm(
                    "Make video fresh", f"Make {title.lower()} all again from scratch - narrated, mixed and "
                    f"rendered anew, nothing reused (the slow part, every time)? Nothing is replaced: it becomes "
                    f"a new version, and the ones made before stay in Versions.", yes="Make it fresh")):
                await self.make_videos(chapters, config, fresh=True)
        elif action == "source":
            if await self.app.push_screen_wait(Confirm(
                    "Remake from source", f"Delete everything made for {title.lower()} - the cut panels, the "
                    f"PDF, the narration audio and the video - keeping only the pages, the panel marks and "
                    f"narration.json, then cut, narrate (the slow part) and make the video again?",
                    yes="Remake from source", danger=True)):
                await self.make_videos(chapters, config, from_source=True)
        elif action == "long":
            await self.long_video(chapters, config)
        elif action == "check":
            await self.check_chapters(chapters, config)
        elif action == "remix":
            await self.remix_videos(chapters, config)
        elif action == "reaudio":
            if await self.app.push_screen_wait(Confirm(
                    "Narrate again, no video", f"Narrate {title.lower()} all again from scratch (the slow "
                    f"part) - not reusing any take made before? What is there now is kept as a version "
                    f"(Versions); Rebuild video then makes the video from the new narration.",
                    yes="Narrate again")):
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
