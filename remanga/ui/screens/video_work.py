"""The chapter menu's video work: narrating and making a chapter's video, or
rebuilding it from the narration already there - shown as a task and ending
on a result. Mixed into the chapters screen; run_task and show come from
chapter_work.py's ChapterWork."""

from __future__ import annotations

from typing import Any

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.humanize import fmt_size
from remanga.paths import get_audio_dir, get_log_path, get_long_video_log_path
from remanga.ui.dialogs import Checklist, Choice, Confirm
from remanga.ui.screens.common import _short
from remanga.ui.tasks import Step
from remanga.workflow.long_video import ordered

UNREBUILDABLE = ("pages", "marks", "narration", "review")


class VideoWork:
    async def remix_videos(self, chapters: list[str], config: RemangaConfig) -> None:
        """A new mix and render from the narration already on disk."""
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: rebuilding the video (narration kept)", [
                Step("Mix the kept narration with the music, render, add the intro",
                     lambda ch=chapter: workflow.remix_video(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: remix {'stopped' if outcome.stopped else 'failed'}",
                                outcome.error.splitlines(), ok=False, log=log)
                return
            video = _short(outcome.results[-1])
            await self.show(f"Chapter {chapter}: video ready", [video], ok=True, log=log, copy=[video])

    async def make_videos(self, chapters: list[str], config: RemangaConfig, force: bool = False,
                         audio_only: bool = False, from_source: bool = False) -> None:
        project = self.project
        verb = ("remaking from source" if from_source else "narrating again" if audio_only
                else "narrating and making the video" if force else "video")
        for chapter in chapters:
            log = get_log_path(project, chapter)
            found: dict[str, Any] = {}

            def check(ch: str = chapter, found: dict = found) -> list:
                found["panels"], found["warnings"] = workflow.check_narration(project, ch)
                found["warnings"] += workflow.quality_warnings(project, ch, config, found["panels"])
                return found["panels"]

            steps = []
            if from_source:
                # Everything derived goes; the pages, marks and narration.json stay.
                steps += [Step("Delete all but the pages, panel marks and narration.json",
                               lambda ch=chapter: workflow.drop_derived(project, ch)),
                          Step("Cut the panels from the marks",
                               lambda ch=chapter: workflow.cut_panels(project, ch, config, force=True))]
            steps += [
                Step("Check the narration", check),
                Step(f"Narrate the panels ({config.tts.spec.display_name})",
                     lambda ch=chapter, found=found: workflow.narrate(project, ch, found["panels"], config, force)),
                Step("Mix with the music", lambda ch=chapter: workflow.mix(project, ch, config, force)),
                Step("Render the video", lambda ch=chapter: workflow.render(project, ch, config, force)),
            ]
            if audio_only:
                # Mixing and rendering run anyway - it's how a changed voice
                # or narration is proven good end to end - but only the raw
                # clips are worth keeping afterwards; the mix and the render
                # come back later from them (Rebuild video) rather
                # than sitting on disk twice.
                steps.append(Step("Keep the new narration, delete the test mix and video",
                                  lambda ch=chapter: workflow.drop_mix_and_video(project, ch)))
            outcome = await self.run_task(f"Chapter {chapter}: {verb}", steps, log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: {'audio' if audio_only else 'video'} "
                                f"{'stopped' if outcome.stopped else 'failed'}",
                                outcome.error.splitlines(), ok=False, log=log)
                return
            if audio_only:
                audio_dir = _short(get_audio_dir(project, chapter))
                await self.show(f"Chapter {chapter}: narration ready", [audio_dir], ok=True,
                                warnings=found.get("warnings", []), log=log, copy=[audio_dir])
            else:
                video = _short(outcome.results[-1])
                await self.show(f"Chapter {chapter}: video ready", [video], ok=True,
                                warnings=found.get("warnings", []), log=log, copy=[video])

    async def long_video(self, chapters: list[str], config: RemangaConfig) -> None:
        """One video of the picked chapters: join their videos, make it all
        from source, or delete long videos already made (workflow/long_video.py)."""
        project = self.project
        chapters = ordered(project, chapters)
        made = [v for v in workflow.long_videos(project) if set(v["chapters"]) & set(chapters)]
        options = []
        if len(chapters) > 1:
            label = workflow.long_label(project, chapters)
            options += [("Join chapter videos", "each chapter's video as it is now, one after another, the intro "
                         "once in front - a chapter with no video yet is made first", "join"),
                        ("Make from source", "every chapter remade from its pages, marks and narration.json (the "
                         "slow part), then joined", "source")]
        if made:
            options.append(("Delete long videos...", "pick which long video(s) with these chapters to delete - "
                            "the chapters' own videos stay", "delete"))
        if not options:
            self.notify("Pick two chapters or more (space) for a long video.")
            return
        note = (f"One video of chapters {label}." if len(chapters) > 1 else f"Chapter {chapters[0]}.")
        if made:
            note += " Made already: " + ", ".join(f"ch{v['label']}" for v in made) + "."
        action = await self.app.push_screen_wait(Choice("Long video", options, note=note,
                                                        danger=["source", "delete"]))
        if action is None:
            return
        if action == "delete":
            rows = [(f"Chapters {v['label']}", fmt_size(v["size"]),
                     _short(v["video"]) if v["video"] else "no finished video in it", v["label"]) for v in made]
            picked = await self.app.push_screen_wait(Checklist(
                "Delete long videos", rows,
                note="Tick what to delete: Enter or Space ticks the highlighted row, a ticks all, d deletes. "
                     "Only the long video goes - every chapter keeps its own."))
            if not picked or not await self.app.push_screen_wait(Confirm(
                    "Delete long videos", f"Delete the long video(s) of chapters {', '.join(picked)}?",
                    yes="Delete", danger=True)):
                return
            for picked_label in picked:
                workflow.delete_long_video(project, picked_label)
            self.notify(f"Deleted the long video(s) of chapters {', '.join(picked)}.")
            return
        from_source = action == "source"
        if from_source and not await self.app.push_screen_wait(Confirm(
                "Make from source", f"Delete everything made for chapters {label} - the cut panels, the PDF, the "
                f"narration audio and the videos - keeping only the pages, the panel marks and narration.json, "
                f"then cut, narrate (the slow part) and make each video again, and join them?",
                yes="Make from source", danger=True)):
            return
        prepare = workflow.remake_from_source if from_source else workflow.prepare_chapter
        steps = [Step(f"Chapter {ch}: {'remake from source' if from_source else 'video, made only if needed'}",
                      lambda ch=ch: prepare(project, ch, config)) for ch in chapters]
        steps.append(Step(f"Join chapters {label} into one video",
                          lambda: workflow.join_chapters(project, chapters, config)))
        log = get_long_video_log_path(project, label)
        outcome = await self.run_task(f"Chapters {label}: one long video", steps, log)
        if not outcome.ok:
            await self.show(f"Chapters {label}: long video {'stopped' if outcome.stopped else 'failed'}",
                            outcome.error.splitlines(), ok=False, log=log)
            return
        video = _short(outcome.results[-1])
        await self.show(f"Chapters {label}: long video ready", [video], ok=True, log=log, copy=[video])
