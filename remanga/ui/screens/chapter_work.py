"""What the chapter menu actually does: download, mark the panels, make the
PDF, make the video - each shown as a task and ending on a result.

A mixin rather than free functions: every one of these runs AS the chapters
screen (it pushes the task and result screens and reloads the table
afterwards), and mixing them in keeps that without passing the screen
around."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rich.text import Text

from remanga import workflow
from remanga.config import RemangaConfig
from remanga.humanize import fmt_size
from remanga.paths import get_log_path
from remanga.ui.dialogs import Checklist, Confirm, Result
from remanga.ui.screens.common import _short
from remanga.ui.tasks import Step, TaskOutcome, TaskScreen

# What remanga cannot rebuild on its own: the pages need MangaDex (a download),
# the marks and the narration are the user's (and the LLM's) work.
UNREBUILDABLE = ("pages", "marks", "crop_reply", "narration", "review")


class ChapterWork:
    """The chapters screen's other half: the steps behind its menu."""

    async def run_task(self, title: str, steps: list[Step], log: Path) -> TaskOutcome:
        return await self.app.push_screen_wait(TaskScreen(self.path, title, steps, log))

    async def show(self, title: str, lines: list, **kwargs: Any) -> None:
        await self.app.push_screen_wait(Result(self.path, title, lines, **kwargs))

    async def download(self, chapters: list[str], force: bool = False) -> None:
        project, config, log = self.project, self.config, get_log_path(self.project)
        outcome = await self.run_task(
            f"Downloading {len(chapters)} chapter(s)",
            [Step(f"Chapter {ch}", lambda ch=ch: workflow.download(project, [ch], config, force=force))
             for ch in chapters], log)
        if outcome.ok:
            await self.show("Downloaded", [f"Chapter(s) {', '.join(chapters)} - every page checked."], ok=True, log=log)
        else:
            await self.show("Download stopped" if outcome.stopped else "Download failed", [outcome.error],
                            ok=False, log=log)

    async def mark(self, chapters: list[str], config: RemangaConfig, again: bool = False) -> None:
        """The browser does the work; the task screen just waits for it. Only
        the marks are saved - Create panels cuts them. `again` is Remark: the
        saved marks go first and every panel is proposed afresh."""
        project, log = self.project, get_log_path(self.project)
        step = workflow.remark if again else workflow.mark
        outcome = await self.run_task(
            f"{'Remarking' if again else 'Marking'} {len(chapters)} chapter(s)",
            [Step("Marker (waiting for the browser)", lambda: step(project, chapters, config))], log)
        if outcome.ok:
            marked = [ch for ch in chapters if workflow.has_marks(project, ch)]
            await self.show("Panels marked", [f"Chapter(s) {', '.join(marked) or '-'} have their panels marked.",
                                              "", Text("Then Create panels for the chapter.", style="dim")],
                            ok=True, log=log)
        else:
            await self.show("Marking stopped" if outcome.stopped else "Marking failed", [outcome.error],
                            ok=False, log=log)

    async def narration_pass(self, which: str, chapters: list[str], config: RemangaConfig) -> None:
        """The browser passes over the narration: writing it, or reviewing it.
        One chapter at a time - each is its own tab and its own file."""
        project = self.project
        writing = which == "write"
        title = "Writing the narration" if writing else "Reviewing the narration"
        step = workflow.write_narration if writing else workflow.review_narration
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(
                f"Chapter {chapter}: {title.lower()}",
                [Step("Waiting for the browser", lambda ch=chapter: step(project, ch, config))], log)
            if not outcome.ok:
                await self.show(f"{title} {'stopped' if outcome.stopped else 'failed'}", [outcome.error],
                                ok=False, log=log)
                return
            written = _short(outcome.results[0])
            lines: list[str | Text] = [f"Chapter {chapter}: {written}"]
            if writing:
                lines += ["", Text("Then Make video for the chapter.", style="dim")]
            else:
                lines += ["", Text("Give that file to the LLM with prompts/narration_review.md, and paste the "
                                   "new reply into narration.json.", style="dim")]
            await self.show("Narration saved" if writing else "Review saved", lines, ok=True, log=log,
                            copy=[written])

    async def create_panels(self, chapters: list[str], config: RemangaConfig) -> None:
        """Cuts the marked panels out - its own step, after marking."""
        project, log = self.project, get_log_path(self.project)
        outcome = await self.run_task(
            f"Creating panels for {len(chapters)} chapter(s)",
            [Step(f"Chapter {ch}", lambda ch=ch: workflow.cut_panels(project, ch, config, force=True))
             for ch in chapters], log)
        if outcome.ok:
            lines: list[str | Text] = [f"Chapter {ch}: {len(cut)} panel(s)"
                                       for ch, cut in zip(chapters, outcome.results, strict=True)]
            await self.show("Panels created", [*lines, "", Text("Then Make PDF for the chapter.", style="dim")],
                            ok=True, log=log)
        else:
            await self.show("Creating panels stopped" if outcome.stopped else "Creating panels failed",
                            [outcome.error], ok=False, log=log)

    async def make_crop_pdfs(self, chapters: list[str], config: RemangaConfig) -> None:
        """The crop PDF of each chapter - MAGI first where a chapter has no marks
        yet - and what to give the LLM and where its reply goes."""
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: crop PDF", [
                Step("Find the panels and draw the pages",
                     lambda ch=chapter: workflow.make_crop_pdf(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: crop PDF {'stopped' if outcome.stopped else 'failed'}",
                                [outcome.error], ok=False, log=log)
                return
            result = outcome.results[0]
            files = [_short(result.prompt), *[_short(p) for p in result.parts]]
            lines: list[str | Text] = [
                Text(f"Boxes: {result.found_by}.", style="dim"), "",
                Text("Give the LLM these files:", style="bold"), *[f"  {f}" for f in files], "",
                Text("Paste its whole reply into:", style="bold"), f"  {_short(result.reply)}", "",
                Text("Then pick the chapter and Use crop reply.", style="dim"),
            ]
            await self.show(f"Chapter {chapter}: crop PDF ready", lines, ok=True, log=log,
                            copy=[*files, _short(result.reply)])

    async def use_crop_replies(self, chapters: list[str], config: RemangaConfig) -> None:
        """Each chapter's pasted crop reply made its panel marks, the panels cut.
        A reply that does not check out changes nothing and says what to paste
        back to the LLM."""
        from remanga.crop_plan import CropReplyError

        def use(chapter: str):
            try:
                return workflow.marks_from_reply(self.project, chapter, config)
            except CropReplyError as error:
                return error

        project = self.project
        for chapter in chapters:
            if not workflow.has_crop_reply(project, chapter):
                continue
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: crop reply", [
                Step("Check the reply, save the marks, cut the panels", lambda ch=chapter: use(ch)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: crop reply {'stopped' if outcome.stopped else 'failed'}",
                                [outcome.error], ok=False, log=log)
                return
            result = outcome.results[0]
            if isinstance(result, CropReplyError):
                reply = _short(workflow.crop_reply_path(project, chapter))
                lines = [Text("Nothing was changed.", style="bold"), "",
                         *[Text(f"✗ {e}", style="red") for e in result.errors or [str(result)]]]
                if result.fix_request:
                    lines += ["", Text("Paste this into the same chat:", style="bold"),
                              f"  {_short(result.fix_request)}",
                              Text("then paste the new reply over:", style="bold"), f"  {reply}", "",
                              Text("and Use crop reply again.", style="dim")]
                await self.show(f"Chapter {chapter}: crop reply has problems", lines, ok=False, log=log,
                                copy=[_short(result.fix_request), reply] if result.fix_request else [reply])
                return
            lines = [Text(f"{len(result.changed)} change(s), {result.panels} panel(s) cut.", style="bold"),
                     *[f"  {line}" for line in result.changed]]
            lines += [Text(f"The LLM noted: {line}", style="yellow") for line in result.problems]
            lines += ["", Text("Look the marks over in Mark panels if you like, then Make PDF.", style="dim")]
            await self.show(f"Chapter {chapter}: panel marks saved from the crop reply", lines, ok=True,
                            warnings=result.warnings + result.report, log=log)

    async def make_upload_pdf(self, chapters: list[str], config: RemangaConfig) -> None:
        """The upload PDF of these chapters, and what to give the LLM."""
        project, log = self.project, get_log_path(self.project)
        outcome = await self.run_task("Upload PDF", [
            Step("Pick the panels, gather the story, build the PDF",
                 lambda: workflow.make_upload_pdf(project, chapters, config)),
        ], log)
        if not outcome.ok:
            await self.show(f"Upload PDF {'stopped' if outcome.stopped else 'failed'}", [outcome.error], ok=False,
                            log=log)
            return
        result = outcome.results[0]
        files = [_short(result.prompt), *[_short(p) for p in result.parts]]
        lines: list[str | Text] = [
            Text(f"{result.offered} images from chapter(s) {', '.join(result.chapters)}.", style="dim"), "",
            Text("Give the LLM these files:", style="bold"), *[f"  {f}" for f in files], "",
            Text("Paste its whole reply into:", style="bold"), f"  {_short(result.reply)}", "",
            Text("Then pick any chapter and Use upload reply.", style="dim"),
        ]
        warnings = [] if result.credits_known else [
            "Who made the manga is not known (its site does not say) - the description leaves the credits out."]
        await self.show("Upload PDF ready", lines, ok=True, log=log, warnings=warnings,
                        copy=[*files, _short(result.reply)])

    async def use_upload_reply(self, config: RemangaConfig) -> None:
        """The pasted upload reply made the titles, thumbnails and description,
        and every finished video is stamped with them. A reply that does not
        check out changes nothing and says what to paste back to the LLM."""
        from remanga.upload_plan import UploadReplyError

        def use():
            try:
                return workflow.upload_from_reply(self.project, config)
            except UploadReplyError as error:
                return error

        log = get_log_path(self.project)
        outcome = await self.run_task("Upload reply", [
            Step("Check the reply, lay out the thumbnails, stamp the videos", use)], log)
        if not outcome.ok:
            await self.show(f"Upload reply {'stopped' if outcome.stopped else 'failed'}", [outcome.error], ok=False,
                            log=log)
            return
        result = outcome.results[0]
        if isinstance(result, UploadReplyError):
            lines = [Text("Nothing was changed.", style="bold"), "",
                     *[Text(f"✗ {e}", style="red") for e in result.errors or [str(result)]]]
            if result.fix_request:
                lines += ["", Text("Paste this into the same chat:", style="bold"), f"  {_short(result.fix_request)}",
                          Text("then paste the new reply over upload/upload_reply.txt and Use upload reply again.",
                               style="dim")]
            await self.show("Upload reply has problems", lines, ok=False, log=log,
                            copy=[_short(result.fix_request)] if result.fix_request else [])
            return
        lines = [Text(f"{len(result.titles)} title/thumbnail pair(s) and the description.", style="bold"),
                 *[f"  {letter}: {title}" for letter, title in result.titles.items()], "",
                 Text("Look at the previews:", style="bold"), *[f"  {_short(p)}" for p in result.previews]]
        lines += [Text(f"The LLM noted: {line}", style="yellow") for line in result.problems]
        lines += ["", Text(f"Stamped beside the videos ({len(result.stamped)} files)." if result.stamped
                           else "No finished video yet - each is stamped as it is made.", style="dim")]
        await self.show("Upload set made", lines, ok=True, warnings=result.warnings, log=log,
                        copy=[_short(p) for p in result.previews])

    async def make_pdfs(self, chapters: list[str], config: RemangaConfig) -> None:
        project = self.project
        for chapter in chapters:
            log = get_log_path(project, chapter)
            outcome = await self.run_task(f"Chapter {chapter}: PDF", [
                Step("Cut the panels and build their PDF",
                     lambda ch=chapter: workflow.make_pdf(project, ch, config)),
            ], log)
            if not outcome.ok:
                await self.show(f"Chapter {chapter}: PDF {'stopped' if outcome.stopped else 'failed'}",
                                [outcome.error], ok=False, log=log)
                return
            result = outcome.results[0]
            files = [_short(result.prompt), *[_short(p) for p in result.parts]]
            lines: list[str | Text] = [
                Text("Give the LLM these files:", style="bold"), *[f"  {f}" for f in files], "",
                Text("Paste its whole reply into:", style="bold"), f"  {_short(result.narration)}", "",
                Text("Then pick the chapter and Make video.", style="dim"),
            ]
            if result.story_from:
                lines[:0] = [Text(f"Story so far carried from chapter {result.story_from}.", style="dim"), ""]
            await self.show(f"Chapter {chapter}: PDF ready", lines, ok=True, warnings=result.warnings(), log=log,
                            copy=[*files, _short(result.narration)])

    async def delete_chosen(self, chapters: list[str], title: str) -> None:
        """A checklist of what these chapters have on disk, with sizes; what
        is ticked is deleted after one more question. Red rows are the ones
        remanga cannot make again by itself."""
        project = self.project
        items = workflow.deletable_items(project, chapters)
        if not items:
            self.notify(f"{title} has nothing on disk to delete.")
            return
        rows = []
        for item, size, having in items:
            where = f"  · {having} of {len(chapters)}" if len(chapters) > 1 else ""
            rows.append((item.label, fmt_size(size), item.hint + where, item.key))
        picked = await self.app.push_screen_wait(Checklist(
            f"Delete from {title.lower()}", rows, danger=UNREBUILDABLE,
            note="Tick what to delete: Enter or Space ticks the highlighted row, a ticks all, d deletes. "
                 "Red = remanga can't make it again by itself."))
        if not picked:
            return
        labels = [label for label, _, _, key in rows if key in picked]
        lost = [label for label, _, _, key in rows if key in picked and key in UNREBUILDABLE]
        message = f"Delete {', '.join(labels)} for {title.lower()}?"
        if lost:
            message += f" {', '.join(lost)} can't be made again by remanga."
        if not await self.app.push_screen_wait(Confirm("Delete chosen", message, yes="Delete", danger=True)):
            return
        removed = [path for chapter in chapters for path in workflow.delete_items(project, chapter, picked)]
        self.notify(f"Deleted {', '.join(labels)} ({len(removed)} file(s) and folder(s)).")


